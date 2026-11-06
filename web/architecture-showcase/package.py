"""Package only the isolated presentation and its approved output artifacts."""
from pathlib import Path
import zipfile

here = Path(__file__).resolve().parent
out = here.parent.parent / 'output/playwright/architecture-showcase-v2'
archive = out / 'STL-architecture-v2-local-20261106.zip'
prefix = 'STL-architecture-v2/'
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
    z.write(out / 'video/STL-architecture-v2-1080p.webm', prefix + 'STL-architecture-v2-1080p.webm')
    z.writestr(prefix + '开始使用.txt', '''STL 架构演示 v2 · 2026-11-06

本包用于内部汇报，包含架构与管理路径，请勿发布到公网。

动态网页：电脑安装 Node 后，在本目录打开终端，执行 node serve.mjs。
然后打开 http://127.0.0.1:5196/ 。无需 npm 安装、后端服务、联网字体或数据库。
F 全屏，← → 推进，空格播放/暂停，R 重播当前阶段，1–6 切幕，Esc 关闭详情。
默认打开使用演示。3 条流程共 14 步，可拖动进度条定位。
点击模块查看内部结构与来源。右上角可导出当前 4K PNG。

没有 Node 时：直接播放 STL-architecture-v2-1080p.webm，或将 PPT-pictures 中的 PNG 插入幻灯片。
视频为约111秒无旁白操作录屏，分辨率1920×1080。9幅PNG均为3840×2160。

架构状态是一份有日期的工作区快照。公开页渲染观察不等于全部业务验收。
自动目录的样本验证来自项目记录，本展示未重新运行其样本。
'''.encode('utf-8-sig'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(n.startswith(prefix) and '..' not in Path(n).parts for n in z.namelist())
print(f'Packaged and checked {archive.name} ({archive.stat().st_size:,} bytes)')
