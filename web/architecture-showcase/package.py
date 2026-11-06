"""Package only the isolated presentation and its approved output artifacts."""
from pathlib import Path
import zipfile, tarfile, hashlib, json, sys

here = Path(__file__).resolve().parent
out = here.parent.parent / 'output/playwright/architecture-showcase-v5'
if '--public' in sys.argv:
    archive = out / 'STL-architecture-v5-public-20261107.tar.gz'
    files = [p for p in (here / 'dist-public').rglob('*') if p.is_file()]
    assert all(not p.is_symlink() and p.suffix not in {'.csv', '.tsx', '.py', '.map'} for p in files)
    assert not json.loads((here/'dist-public/architecture.json').read_text())['sources']
    files += [here/name for name in ['serve.mjs', 'compose.public.yaml', 'Dockerfile.public', '.dockerignore']]
    manifest = {p.relative_to(here).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with tarfile.open(archive, 'w:gz') as t:
        for p in files:
            t.add(p, arcname=p.relative_to(here).as_posix())
    (out/'public-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Public package: {archive.name}, {len(files)} files, {archive.stat().st_size:,} bytes')
    sys.exit(0)
archive = out / 'STL-architecture-v5-local-20261107.zip'
prefix = 'STL-architecture-v5/'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in (here / 'dist').rglob('*'):
        if f.is_file():
            z.write(f, prefix + 'dist/' + f.relative_to(here / 'dist').as_posix())
    z.write(here / 'serve.mjs', prefix + 'serve.mjs')
    z.write(here / 'evidence-index.csv', prefix + 'evidence-index.csv')
    z.write(here / 'README.md', prefix + 'README.md')
    z.write(here / 'DOMAIN_SETUP.md', prefix + 'DOMAIN_SETUP.md')
    for f in here.iterdir():
        if f.is_file() and f.name != '.gitignore':
            z.write(f, prefix + 'source/' + f.name)
    z.writestr(prefix + 'start.cmd', '@echo off\r\ncd /d "%~dp0"\r\nnode serve.mjs 5196\r\npause\r\n')
    for f in (out / '4k').glob('*.png'):
        z.write(f, prefix + 'PPT-pictures/' + f.name)
    z.write(out / 'video/STL-architecture-v5-1080p.webm', prefix + 'STL-architecture-v5-1080p.webm')
    z.writestr(prefix + '开始使用.txt', '''STL 架构演示 v5 · 2026-11-07

本包包含内部架构与管理路径，仅供内部汇报。

启动网页：
1. 在电脑上安装 Node。
2. 双击 start.cmd。
3. 打开 http://127.0.0.1:5196/ 。
网页可离线运行，无需安装 npm 依赖。
F 切换全屏，← → 切换步骤，空格暂停或恢复自动切换。
R 重播当前阶段，1–5 切换场景，Esc 关闭详情。
默认从总览自动开始，5 幕和 3 条流程循环展示。点击页面延长当前步骤的停留。
点击模块查看内部结构与来源。右上角可导出当前 4K PNG。

未安装 Node 时，可直接播放 STL-architecture-v5-1080p.webm。
PPT-pictures 中的 14 张 PNG 均为 3840×2160，可插入幻灯片。
视频约 5 分钟，分辨率为 1920×1080，无旁白。

架构内容记录核对时的实现状态。页面可以显示，不代表业务已通过验收。
自动目录的样本结果来自已有项目记录，本展示未重跑样本。
'''.encode('utf-8-sig'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(n.startswith(prefix) and '..' not in Path(n).parts for n in z.namelist())
print(f'Packaged and checked {archive.name} ({archive.stat().st_size:,} bytes)')
