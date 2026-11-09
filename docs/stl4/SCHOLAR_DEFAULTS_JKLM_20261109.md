# 2026-11-09 学者默认背景 J/K/L/M 接入

## 用户决定与状态

- 用户同时采纳 J 冷白纸层、K 银灰岩层、L 月白薄片、M 玄灰裂光。无肖像学者自动分配其中一款，长姓名自动排版。A 暖纸淡彩继续为已选肖像方向，不加遮罩。
- B：默认背景及长姓名适配已实现，局部组件检查通过；NAS/公网运行验收与发布未执行。
- D：四款设计选择已明确，不再作为待选方案。早期六款、D/E/F、G/H/I 仅留作历史。
- C：管理端 AI 风格转换为可选后续能力。本轮用户询问实现方式，没有新增服务、配置图像 API、发起批量生成或修改媒体资料。

## 交付行为

1. 按公开学者链接的 slug 做稳定散列分配，四款均会使用。同一学者在首页、目录、详情、主题/理论关联、策划文章、观点检索、时间线与欢迎演示使用同一分配逻辑；刷新和列表顺序不会重抽。没有新增数据库字段或持久化写入。链接标识改变可能重新分配。
2. 姓名为真实文字，不烧录进图片。初始字号考虑中文与拉丁字符宽度，优先在间隔号/连字符处分组换行；字体完成加载或容器改变时测量可用区域并缩小，保留完整文字、不加省略号。60px 及以下图标位仅显示抽象背景，由相邻的学者姓名承担读名，辅助技术仍可读完整姓名。
3. M 使用浅字，其余三款深字。沿用完整矩形，没有遮罩、渐隐或虚构人物肖像。默认图不会覆盖已选肖像；媒体用途限制继续经 MediaPlacement 执行。
4. 四张批准 PNG 保留在 output/design/scholar-directions-20261109/r3；正式前端素材仅做 WebP 编码和640/1280两种分辨率转换，位于 web/public/images/scholars。640px 每张 7,916–31,916 字节。SOURCES.json 记录来源与转换。
5. 清除旧通用灰底半圆人形。相关肖像区域去除强制灰度，确保以后上传 A 淡彩肖像保留色彩。新目录共用 ScholarImage 同步 contain 和 picture 高度约束；原图片文件及数据保持。

## 实现位置与契约

- web/lib/default-scholar-portrait.ts：身份规范化、稳定分配、初始字号。
- web/components/default-scholar-portrait.tsx 与同名 CSS module：共享背景、姓名适配、既有尺寸的回退包装。
- ui.tsx、responsive-portrait-image.tsx 与 public/scholar-shared.tsx：两条现有学者组件链共用默认图。
- 首页策划、策划关联、子学科/理论代表人物及用法比较、时间线、观点检索、欢迎演示接入同一回退组件。
- 无 API/数据模型/队列/权限变更。无肖像和当前展示用途未获允许时使用默认图；未知作者继续使用原未知状态，不凭空命名。

## A 肖像的现有能力与建议

A 参考图是先前通过内置 ImageGen 对周雪光真实照片做风格转换的结果，不是 CSS 滤镜。原照片与 A 样图仍在 output/design/scholar-directions-20261109；没有批量修改人物照片。

已核对的管理端链：

- web/components/admin/media/scholar-portrait-panel.tsx：更换肖像进入媒体工作区；选择和清除保存编辑草稿，原图保留。
- web/components/admin/media/media-workspace.tsx、media-crop.tsx：上传/复用图片、裁切、旋转、预览、保存。
- api/catalog/services/media.py 的 build_rendition：Pillow 旋转、裁切、焦点适配、缩放及 WebP 编码。未传裁切参数的 portrait 派生图默认4:5；不能将缺失的原始身体部分补回，也不生成绘画风格。
- api/catalog/scholar_media_views.py、services/scholar_media.py：学者图片选择进入既有编辑版本，公开图片按发布版本读取。

当前链没有图像模型编辑调用。可行的后续按钮应为“生成 A 风格草稿”：选原图 → 固定风格参考与提示词 → 支持图像编辑的服务生成候选 → 原图/候选对照 → 采用到既有媒体草稿并按原发布流程处理。需要另接服务、凭据、异步任务及失败重试，不能把现有裁切按钮称为 AI 生成。

建议先由 AI 按 A 参考统一处理一批，再用现有管理端选用。若未来新增频繁，再接生成草稿。质量检查主要针对人物相似度、年龄、五官、眼镜和发型，以及构图、留白与风格一致性；不承诺全自动无误。存储/发布流程可以复用，无需重建媒体库。统一风格不依生卒状态分别转灰度。

## 实际验证与限制

- web 下 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`：最终退出0。
- web 下 `node --experimental-strip-types --test tests/default-scholar-portrait.test.mjs`：2项通过，覆盖编码/Unicode/带查询或末尾斜线链接一致性、四款均可分配及渲染顺序不影响结果。
- 本轮源码 `git diff --check`：退出0，仅既有 CRLF→LF 提示。
- 局部组件预览 http://127.0.0.1:18776/。由真实 DefaultScholarPortrait、ScholarImage、MediaPlacement 和相关 CSS 组件构成；示例姓名用于排版检查，不写入业务数据。
- 1440px 桌面：17个可见默认图；390px 手机：18个可见默认图（另一个按用途限制切换）。最终检查图片全部加载、姓名适配通过、无页面水平溢出。窄幅、方形、横卡、详情图及三个小图标位已实际查看。
- 证据 output/design/scholar-directions-20261109/implemented/{desktop.jpg,mobile.jpg,mobile-related.jpg,desktop-check.json,mobile-check.json}。预览用 esbuild 独立包装，最初缺少 Next 环境常量的预览错误已修正；不是完整网站构建或正式 E2E。
- 未运行全站正式验收、未接生产数据库、未修改人物媒体、未推送部署。局部结果不代表 NAS/公网运行已验收。
