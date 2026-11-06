"""Package only the isolated presentation and its approved output artifacts."""
from pathlib import Path
import zipfile

here = Path(__file__).resolve().parent
out = here.parent.parent / 'output/playwright/architecture-showcase-v3'
archive = out / 'STL-architecture-v3-local-20261106.zip'
prefix = 'STL-architecture-v3/'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in (here / 'dist').rglob('*'):
        if f.is_file():
            z.write(f, prefix + 'dist/' + f.relative_to(here / 'dist').as_posix())
    z.write(here / 'serve.mjs', prefix + 'serve.mjs')
    z.write(here / 'evidence-index.csv', prefix + 'evidence-index.csv')
    z.write(here / 'README.md', prefix + 'README.md')
    for f in here.iterdir():
        if f.is_file() and f.name != '.gitignore':
            z.write(f, prefix + 'source/' + f.name)
    z.writestr(prefix + 'start.cmd', '@echo off\r\ncd /d "%~dp0"\r\nnode serve.mjs 5196\r\npause\r\n')
    for f in (out / '4k').glob('*.png'):
        z.write(f, prefix + 'PPT-pictures/' + f.name)
    z.write(out / 'video/STL-architecture-v3-1080p.webm', prefix + 'STL-architecture-v3-1080p.webm')
    z.writestr(prefix + '开始使用.txt', '''STL 架构演示 v3 · 2026-11-06

本包包含内部架构与管理路径，仅供内部汇报。

启动网页：
1. 在电脑上安装 Node。
2. 双击 start.cmd。
3. 打开 http://127.0.0.1:5196/ 。
网页可离线运行，无需安装 npm 依赖。
F 切换全屏，← → 切换步骤，空格播放或暂停。
R 重播当前阶段，1–5 切换场景，Esc 关闭详情。
默认打开使用演示。3 条流程共 38 步，可拖动进度条定位。
点击模块查看内部结构与来源。右上角可导出当前 4K PNG。

未安装 Node 时，可直接播放 STL-architecture-v3-1080p.webm。
PPT-pictures 中的 11 张 PNG 均为 3840×2160，可插入幻灯片。
视频约 3 分钟，分辨率为 1920×1080，无旁白。

架构内容记录核对时的实现状态。页面可以显示，不代表业务已通过验收。
自动目录的样本结果来自已有项目记录，本展示未重跑样本。
'''.encode('utf-8-sig'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(n.startswith(prefix) and '..' not in Path(n).parts for n in z.namelist())
print(f'Packaged and checked {archive.name} ({archive.stat().st_size:,} bytes)')
