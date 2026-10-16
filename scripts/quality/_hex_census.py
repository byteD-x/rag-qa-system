import re, pathlib, collections
root = pathlib.Path('apps/web/src')
files = [p for p in root.rglob('*.vue') if '.test.' not in p.name]
prop_pat = re.compile(r'([a-z-]+)\s*:\s*([^;{}]*#[0-9a-fA-F]{3,8}[^;{}]*)')
by_color = collections.defaultdict(list)
for p in files:
    t = p.read_text(encoding='utf-8', errors='replace')
    for m in prop_pat.finditer(t):
        prop = m.group(1)
        val = ' '.join(m.group(2).split())
        for hexv in re.findall(r'#[0-9a-fA-F]{3,8}', val):
            line = t.count('\n', 0, m.start()) + 1
            by_color[hexv.lower()].append((str(p.relative_to(root)), line, prop, val[:70]))
print('=== .vue 内硬编码颜色的属性分布 ===')
for c in sorted(by_color, key=lambda k: -len(by_color[k])):
    props = collections.Counter(x[2] for x in by_color[c])
    print(f'{c:10} {len(by_color[c]):3} 处  {dict(props)}')
print()
print('=== 逐条（仅 background/border/fill/stroke 属性）===')
for c in sorted(by_color):
    rows = [x for x in by_color[c] if x[2] in ('background','background-color','border','border-color','border-top','border-left','border-right','border-bottom','fill','stroke','box-shadow','outline')]
    if not rows: continue
    print(f'-- {c}')
    for f, line, prop, val in rows:
        print(f'    {f}:{line}  {prop}: {val}')
