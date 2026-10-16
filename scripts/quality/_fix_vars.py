import pathlib, sys
root = pathlib.Path('apps/web/src')
files = [p for p in root.rglob('*') if p.suffix in ('.vue','.ts','.css') and '.test.' not in p.name]

REPL = [
    ('var(--blue-400)', 'var(--blue-500)', 10),
    ('var(--blue-200)', 'var(--blue-500)', 1),
    ('var(--blue-100)', 'var(--blue-50)', 2),
    ('var(--green-400)', 'var(--el-color-success)', 2),
    ('var(--orange-400)', 'var(--el-color-warning)', 1),
    ('var(--red-400)', 'var(--el-color-danger)', 3),
    ('var(--red-500)', 'var(--el-color-danger)', 3),
    ('var(--red-600)', 'var(--el-color-danger)', 1),
    ('var(--color-primary)', 'var(--blue-600)', 1),
    ('var(--bg-body)', 'var(--bg-page)', 2),
    ('var(--success-color, #67c23a)', 'var(--el-color-success)', 5),
    ('var(--danger-color, #f56c6c)', 'var(--el-color-danger)', 4),
    ('var(--warning-color, #e6a23c)', 'var(--el-color-warning)', 4),
    ('var(--warning-bg, #fdf6ec)', 'var(--el-color-warning-light-9)', 1),
]

texts = {p: p.read_text(encoding='utf-8') for p in files}
ok = True
for old, new, want in REPL:
    got = sum(t.count(old) for t in texts.values())
    flag = 'OK ' if got == want else '!! '
    if got != want:
        ok = False
    print(f'{flag}{old:38} -> {new:32} 实际 {got} / 预期 {want}')
if not ok:
    print('\n计数不符，未写入。')
    sys.exit(1)
for old, new, _ in REPL:
    for p in files:
        if old in texts[p]:
            texts[p] = texts[p].replace(old, new)
for p, t in texts.items():
    p.write_text(t, encoding='utf-8')
print('\n已写入', len(texts), '个文件')
