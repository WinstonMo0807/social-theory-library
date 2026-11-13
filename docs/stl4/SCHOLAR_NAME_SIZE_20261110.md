# 学者卡片姓名字号修正 2026-11-10

用户指出上一轮肖像排版更新后姓名显得过小，延续本对话学者界面公网发布授权修正字号。不是重新生成肖像。

## 原因与修改

公网2040px浏览器读取的实际字号：推荐姓名20px；全部学者姓名15px，而研究方向为17px。肖像面积增大后，旧姓名小字规则使视觉层级更加失衡。首页1200px以下还存在16px覆盖。

仅修改两份CSS：`web/components/public/scholar.module.css`与`web/styles/features/home/home-stl4.css`。替换已有字号声明，不添加新的布局、组件或依赖。

- 全部学者和首页桌面姓名24px，推荐与独立目录22px；首页中等屏宽22px，手机统一20px。
- 使用rem并以当前正文可读字号为下限；保留完整姓名换行，长姓名不使用缩小字号或截断。
- 首页自动聚焦与后台编排聚焦共用规则。原A肖像、JKLM默认图、图框和交互保持。

## 验证

- 本地2040px：推荐22px、全部24px，所有姓名无横向溢出；390px全部19个推荐/列表姓名20px且无溢出，页面宽375px。
- 首页自动聚焦390px为20px，1024px为22px，后台编排同为22px；所有被检查姓名无溢出。已查看实际屏幕。
- 两份CSS git diff --check通过，隔离Vinext正式构建退出0。逐文件核对app/components/lib/styles/scripts只包含这两份CSS的变化，基线为已发布scholar-layout-r1。
- 公网2040px实测推荐22px、全部学者24px，全部16个姓名无溢出；390px实测16个姓名全部20px、无溢出、内容375px。首页5个姓名全部24px且无溢出。没有运行全站正式验收。

## 发布与恢复

候选`social-theory-library-web:4.0.0-20261110-scholar-name-size-r1`。既有部署脚本限定Web镜像变化、保存完整恢复配置与准确旧镜像，失败仅回滚Web。旧镜像scholar-layout-r1，ID`sha256:c126d0d807a3294c71d50d66094802cfb72e62397c0a03fb926654343eb2aba2`。不修改API、媒体或数据库，保护其他容器身份和启动时间。

构建、源差异及发布证据在`tmp/scholar-name-size-20261110/`。原有暂存及其他工作区修改保持。

2026-11-10 02:03:41（北京时间）完成正式Web-only发布。镜像`social-theory-library-web:4.0.0-20261110-scholar-name-size-r1`，ID`sha256:6d73eb4bb04dc8af05a5c66e8b9e5506ecae534dbf814d9251063d8f413457b4`，容器`37db8247c82c`。1860文件哈希一致，runtime-config不变，四入口200，其他容器身份和启动时间保持。

恢复目录`/volume2/library/stl-releases/20261110-scholar-name-size-r1/web-recovery`；活动Compose命令保存在原20261107-r1/public入口，追加仅Web镜像覆盖。未执行回滚、数据库迁移或媒体写入。

实际公网截图`output/design/scholar-name-size-20261110/public-desktop.png`与`public-home.png`；桌面、手机、首页字号度量和部署回执在上述tmp目录。本轮D：请求范围已实现并上线定向核验，不代表全站验收。
