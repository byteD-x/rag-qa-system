import re, pathlib, collections
root = pathlib.Path('apps/web/src')
files = [p for p in root.rglob('*') if p.suffix in ('.vue','.css') and '.test.' not in p.name]
pat = re.compile(r'(background(?:-color)?\s*:\s*[^;]*(?:#(?:fff|ffffff|f0f7ff|fff5f5|fdf6ec|f5f7fa|f7fafc|fafcff|eff6ff|e8f0ff|ffffffcc)\b|rgba\(\s*255\s*,\s*255\s*,\s*255)[^;]*;)', re.I)
hits = collections.defaultdict(list)
for p in files:
    t = p.read_text(encoding='utf-8', errors='replace')
    for m in pat.finditer(t):
        line = t.count('\n', 0, m.start()) + 1
        hits[str(p.relative_to(root))].append((line, ' '.join(m.group(1).split())))
print('=== 硬编码浅色底（暗色模式会失效）===')
total = 0
for f in sorted(hits):
    print(f'{f}  ({len(hits[f])})')
    for line, txt in hits[f]:
        print(f'    {line}: {txt}')
        total += 1
print('合计', total)
