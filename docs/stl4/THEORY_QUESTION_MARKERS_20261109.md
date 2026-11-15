# 理论流派问题标记修复 2026-11-09

用户截图中的三个问号来自两套理论详情组件写死的 `?` 装饰字符，非编码损坏。改为01、02、03序号，正文研究问题及原文不变；使用小号等宽数字，保持18px图标列与自然换行。

仅修改两个TSX及共用CSS。基于实际semantic-status-r1源构建隔离候选，保留语义检索修复；没有混入另一对话尚未部署的JKLM肖像变更。两文件ESLint零错误（六条既有警告），正式构建退出0。

Web-only正式切换到theory-markers-r1。全部1847文件SHA256读回一致；原运行配置、其他容器身份与启动时间保持，/home、/admin、/theories均200。恢复点保留旧Web inspect、完整配置与运行命令，失败分支自动回退；未改数据库、OCR、模型，不在NAS构建或完整compose up。浏览器实际视觉核验继续。

证据 tmp/curation-public-cleanup-20261109/verification.json；NAS /volume2/library/stl-releases/20261109-theory-markers-r1/web-recovery。
