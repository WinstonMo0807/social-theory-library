# STL 加载与阅读组件候选

本地独立设计预览；未接入正式页面，未获采用，不调用书库 API。

在此目录运行 `python -m http.server 18884 --bind 127.0.0.1`，打开 http://127.0.0.1:18884/ 。Logo 与九类场景由原生 SVG/CSS/JS 实现，不需要安装依赖。

四种 Logo 动效可以代入场景；D/E/F 切换布局；四个状态按钮模拟首次加载、更新、失败和完成。示例记录与任务计数不是生产数据。减少动效与暂停控制可独立使用。

`brand.svg` 是仓库品牌 SVG 的原样副本，SHA-256 为 `415f849fb95bfc00e0e4508d8bbe3b99de9f4867bd614f5b5dc2801dcc0e6b57`。

五张 Image Gen 参考图为本机设计产物，保存在 `output/design/reader-loading-system-20261112/`，本地预览也有同名副本。尚未选定的图不加入此 Git 检查点；复制 `loading-d.png`、`loading-e.png`、`loading-f.png`、`reader-b.png`、`reader-c.png` 到当前目录即可浏览完整参考区。图内文字仅示意，不能作为书目证据或功能完成证据。

`audit_loading.py` 从项目根目录扫描前端加载位置和样式，重新生成 output 内的 CSV/JSON。静态候选不是缺陷清单或运行验收结果。

详细定位、未提交改动边界与后续验收见 `docs/stl4/READER_LOADING_DESIGN_20261112.md`。
