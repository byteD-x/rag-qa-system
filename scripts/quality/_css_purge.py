"""一次性清理脚本（dry-run 默认）：删除扫描器确认的死规则行区间。

用法:
  python scripts/quality/_css_purge.py            # dry-run，只打印计划
  python scripts/quality/_css_purge.py --apply    # 实际写入

安全措施:
  - 删除前记录每个文件的 {} 括号平衡，删除后必须保持平衡，否则中止不写
  - 若某个 at-rule（@media 等）块内所有内容都在删除区间内，则连同块头与块尾一起删除
  - 只按显式行号删除，不做任何模式替换
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'scripts' / 'quality' / '_dead-css-report.json'
APPLY = '--apply' in sys.argv


def load_ranges():
    data = json.loads(REPORT.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        data = [data]
    per_file = {}
    for item in data:
        f = 'apps/web/src/' + item['File']
        lo, hi = (int(x) for x in item['Range'].split('-'))
        per_file.setdefault(f, []).append((lo, hi))
    return per_file


def merge(ranges):
    out = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return [list(r) for r in out]


def brace_balance(lines):
    depth = 0
    inside_comment = False
    for line in lines:
        i = 0
        while i < len(line):
            if inside_comment:
                j = line.find('*/', i)
                if j == -1:
                    break
                inside_comment = False
                i = j + 2
                continue
            j = line.find('/*', i)
            if j == -1:
                j = len(line)
            seg = line[i:j]
            depth += seg.count('{') - seg.count('}')
            if j == len(line):
                break
            inside_comment = True
            i = j + 2
    return depth


def at_rule_blocks(lines):
    """返回 [(head_idx, close_idx, '@media ...')]（0-based，仅顶层/嵌套的 {} 容器）。"""
    blocks = []
    stack = []
    inside_comment = False
    for idx, line in enumerate(lines):
        i = 0
        pending = []
        while i < len(line):
            if inside_comment:
                j = line.find('*/', i)
                if j == -1:
                    break
                inside_comment = False
                i = j + 2
                continue
            j = line.find('/*', i)
            if j == -1:
                j = len(line)
            pending.append(line[i:j])
            if j == len(line):
                break
            inside_comment = True
            i = j + 2
        seg = ''.join(pending)
        # 记录本行 '{' 之前的文本片段，用于识别 at-rule 头
        for ch_i, ch in enumerate(seg):
            if ch == '{':
                stack.append(idx)
            elif ch == '}':
                if not stack:
                    continue
                head = stack.pop()
                if line_head_is_at_rule(lines, head, ch_i):
                    blocks.append((head, idx))
    return blocks


def line_head_is_at_rule(lines, head_idx, _):
    text = lines[head_idx].strip()
    return text.startswith('@')


def nonblank_in(lines, lo, hi):
    """1-based 闭区间的非空行号集合。"""
    return {i for i in range(lo, hi + 1) if lines[i - 1].strip()}


def main():
    per_file = load_ranges()
    total_deleted = 0
    plans = {}
    for rel, ranges in per_file.items():
        path = ROOT / rel
        lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
        merged = merge(ranges)

        before = brace_balance(lines)
        covered = set()
        for lo, hi in merged:
            covered |= nonblank_in(lines, lo, hi)

        # 折叠“将被清空”的 at-rule 块
        for head, close in at_rule_blocks(lines):
            head_line = head + 1
            close_line = close + 1
            if head_line in covered or close_line in covered:
                continue
            inner = nonblank_in(lines, head_line, close_line) - {head_line, close_line}
            if inner and inner <= covered:
                merged = merge(merged + [[head_line, close_line]])
                covered |= nonblank_in(lines, head_line, close_line)

        keep = []
        deleted = 0
        for i, line in enumerate(lines, start=1):
            if any(lo <= i <= hi for lo, hi in merged):
                deleted += 1
            else:
                keep.append(line)

        after = brace_balance(keep)
        ok = (before == after == 0)
        plans[rel] = (merged, deleted, before, after, ok)
        total_deleted += deleted
        print(f'--- {rel}: 删除 {deleted} 行  括号 {before} -> {after}  {"OK" if ok else "**不平衡**"}')
        for lo, hi in merged:
            print(f'      {lo}-{hi}')

    print(f'\n合计删除 {total_deleted} 行')
    if not all(p[4] for p in plans.values()):
        print('中止：存在括号不平衡，未写入任何文件。')
        return 1

    if APPLY:
        for rel, (merged, deleted, _, _, _) in plans.items():
            path = ROOT / rel
            lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
            keep = [l for i, l in enumerate(lines, start=1)
                    if not any(lo <= i <= hi for lo, hi in merged)]
            path.write_text(''.join(keep), encoding='utf-8')
            print(f'已写入 {rel}')
    else:
        print('（dry-run，未写入。加 --apply 生效）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
