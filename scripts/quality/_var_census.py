import re, pathlib, collections
root = pathlib.Path('apps/web/src')
files = [p for p in root.rglob('*') if p.suffix in ('.vue','.ts','.css') and '.test.' not in p.name]
refs = collections.defaultdict(list)
defs = set()
for p in files:
    t = p.read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r'var\(\s*(--[A-Za-z0-9_-]+)', t):
        line = t.count('\n', 0, m.start()) + 1
        refs[m.group(1)].append(f'{p.relative_to(root)}:{line}')
    for m in re.finditer(r'(--[A-Za-z0-9_-]+)\s*:', t):
        defs.add(m.group(1))
    for m in re.finditer(r"setProperty\(\s*['\"](--[A-Za-z0-9_-]+)['\"]", t):
        defs.add(m.group(1))
missing = {k: v for k, v in refs.items() if k not in defs and not k.startswith('--el-')}
print('=== 引用但从未定义（排除 --el-*）===')
for k in sorted(missing, key=lambda x: -len(missing[x])):
    print(f'{k}  引用于 {len(missing[k])} 处')
    for loc in missing[k][:14]:
        print('    ', loc)
print()
print('=== --el-* 引用但非 Element Plus 全局定义 ===')
el = {k: v for k, v in refs.items() if k.startswith('--el-') and k not in defs}
for k in sorted(el):
    print(f'{k}: {len(el[k])} 处 -> {el[k][0]}')
