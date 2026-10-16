#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第一轮设计审计报告 -> 结构化台账。

从 ``docs/design-audit/round1/*.md`` 的 Markdown 表格中机械抽取：
  - 提案（动作 / 位置 / 用户收益 / 代价与风险）
  - 动效发现（严重度 / 类别 / 位置 / 发现 / 修复方向）
  - 元素清单标签计数（必要 / 可删 / 可合并 / 可下沉）
  - 「完成该任务的必要步骤」条数

用法（仓库根目录）::

    python scripts/design-audit/build_round1_ledger.py

输出：``docs/design-audit/round2/ledger.json``，并把摘要打印到 stdout。
只做文本解析，不读取任何源码，不修改任何源码。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROUND1_DIR = Path("docs/design-audit/round1")
OUT_PATH = Path("docs/design-audit/round2/ledger.json")

HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
NUMBERED_RE = re.compile(r"^\s*(\d+)\.\s+\S")
SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")
PIPE_PLACEHOLDER = "\x00PIPE\x00"

TAG_ORDER = ("可删", "可合并", "可下沉", "必要")
TAG_TO_KEY = {
    "必要": "necessary",
    "可删": "deletable",
    "可合并": "mergeable",
    "可下沉": "sinkable",
}


def split_table_row(line: str) -> list[str]:
    """按未被转义的 ``|`` 切分表格行，返回去掉首尾空单元的单元格列表。"""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    protected = stripped.replace("\\|", PIPE_PLACEHOLDER)
    cells = [c.replace(PIPE_PLACEHOLDER, "|").strip() for c in protected.split("|")]
    # 去掉 Markdown 表格首尾的空单元
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(SEPARATOR_CELL_RE.match(c) for c in cells)


def collect_sections(text: str) -> list[tuple[int, str, str]]:
    """把文档切成 (标题层级, 标题, 正文) 列表；只按 ## / ### 标题切分。"""
    sections: list[tuple[int, str, str]] = []
    current: list | None = None
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            if current is not None:
                sections.append((current[0], current[1], "\n".join(current[2])))
            current = [len(match.group(1)), match.group(2), []]
        elif current is not None:
            current[2].append(line)
    if current is not None:
        sections.append((current[0], current[1], "\n".join(current[2])))
    return sections


def find_section(sections: list[tuple[int, str, str]], prefix: str, level: int | None = None) -> str | None:
    """返回标题以 prefix 开头的小节正文，并**并入紧随其后的、层级更深的子小节**。

    18/19/20-platform-*.md 把「完成该任务的必要步骤」「元素清单」的内容放在 ``###``
    子小节里，只取本级正文会得到空字符串（会漏掉这 3 份报告的步骤数与元素计数）。
    """
    for index, (found_level, title, body) in enumerate(sections):
        if not title.startswith(prefix):
            continue
        if level is not None and found_level != level:
            continue
        parts = [body]
        for later_level, _later_title, later_body in sections[index + 1 :]:
            if later_level > found_level:
                parts.append(later_body)
            else:
                break
        return "\n".join(parts)
    return None


def parse_proposals(body: str | None) -> list[dict]:
    if not body:
        return []
    proposals: list[dict] = []
    for line in body.splitlines():
        cells = split_table_row(line)
        if len(cells) < 2 or is_separator_row(cells):
            continue
        if cells[0] == "动作":
            continue
        proposals.append(
            {
                "action": cells[0],
                "target": cells[1],
                "gain": cells[2] if len(cells) > 2 else "",
                "cost_risk": cells[3] if len(cells) > 3 else "",
            }
        )
    return proposals


def parse_motion(body: str | None) -> list[dict]:
    if not body:
        return []
    findings: list[dict] = []
    for line in body.splitlines():
        cells = split_table_row(line)
        if len(cells) < 4 or is_separator_row(cells):
            continue
        if cells[0] == "严重度":
            continue
        findings.append(
            {
                "severity": cells[0],
                "category": cells[1],
                "location": cells[2],
                "finding": cells[3],
                "fix": cells[4] if len(cells) > 4 else "",
            }
        )
    return findings


def parse_elements(body: str | None) -> dict:
    counts = Counter()
    raw_tags = Counter()
    unmapped: list[str] = []
    if not body:
        return {
            "necessary": 0,
            "deletable": 0,
            "mergeable": 0,
            "sinkable": 0,
            "rows": 0,
            "raw_tags": {},
            "unmapped": [],
        }
    for line in body.splitlines():
        cells = split_table_row(line)
        if len(cells) < 3 or is_separator_row(cells):
            continue
        if cells[0] == "元素":
            continue
        tag = cells[2]
        raw_tags[tag] += 1
        matched = next((t for t in TAG_ORDER if tag.startswith(t)), None)
        if matched:
            counts[TAG_TO_KEY[matched]] += 1
        else:
            unmapped.append(tag)
    return {
        "necessary": counts["necessary"],
        "deletable": counts["deletable"],
        "mergeable": counts["mergeable"],
        "sinkable": counts["sinkable"],
        "rows": sum(raw_tags.values()),
        "raw_tags": dict(raw_tags),
        "unmapped": unmapped,
    }


def parse_steps(body: str | None) -> int:
    if not body:
        return 0
    return len([line for line in body.splitlines() if NUMBERED_RE.match(line)])


def parse_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    sections = collect_sections(text)
    title_line = text.splitlines()[0].lstrip("# ").strip()
    return {
        "report": path.stem,
        "title": title_line,
        "task_steps": parse_steps(find_section(sections, "完成该任务的必要步骤")),
        "elements": parse_elements(find_section(sections, "元素清单")),
        "proposals": parse_proposals(find_section(sections, "提案")),
        "motion_findings": parse_motion(find_section(sections, "动效发现")),
    }


def main() -> int:
    reports = sorted(
        p for p in ROUND1_DIR.glob("*.md") if p.name != "00-index.md"
    )
    ledger = {
        "source": "docs/design-audit/round1/*.md",
        "report_count": len(reports),
        "reports": [parse_report(p) for p in reports],
    }

    action_totals: Counter = Counter()
    severity_totals: Counter = Counter()
    element_totals: Counter = Counter()
    for report in ledger["reports"]:
        action_totals.update(p["action"] for p in report["proposals"])
        severity_totals.update(m["severity"] for m in report["motion_findings"])
        for key in ("necessary", "deletable", "mergeable", "sinkable"):
            element_totals[key] += report["elements"][key]

    ledger["totals"] = {
        "proposals": sum(action_totals.values()),
        "proposals_by_action": dict(action_totals),
        "motion_findings": sum(severity_totals.values()),
        "motion_by_severity": dict(severity_totals),
        "elements": dict(element_totals),
        "task_steps": sum(r["task_steps"] for r in ledger["reports"]),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"reports: {ledger['report_count']}")
    print(f"proposals: {ledger['totals']['proposals']} -> {ledger['totals']['proposals_by_action']}")
    print(f"motion:    {ledger['totals']['motion_findings']} -> {ledger['totals']['motion_by_severity']}")
    print(f"elements:  {ledger['totals']['elements']}")
    print("per-report proposals / motion / steps:")
    for report in ledger["reports"]:
        print(
            f"  {report['report']:<20} proposals={len(report['proposals'])} "
            f"motion={len(report['motion_findings'])} steps={report['task_steps']}"
        )
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
