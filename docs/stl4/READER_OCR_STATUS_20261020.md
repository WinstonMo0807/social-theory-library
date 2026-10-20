# PDF40 阅读器 OCR 状态补齐

日期2026-10-20。前置并读检查点0b6c010、Reader检查点a5898aa。已实际查看唯一final-r2 PDF物理40的状态原图。本单元补该页之前明确保留的真实处理进度/暂停/继续缺口；源码接入不等于正式验收通过。

## 界面与真实状态

阅读工具增加文字识别与处理状态，原处理中提示也可打开同一原生Dialog。展示精确文件对应任务、实际完成页/任务目标页、真实百分比、当前阶段用时、等待当前页保存的暂停状态、心跳过期及错误。未知指标不补零或虚构估计；整份文件页数与任务选定页数分开。纸白/灰/砂金沿MASTER_SPEC。

缩略图只复制现有Reader已完成渲染的当前PDF画布到内存小画布，不再下载PDF、创建截图文件或请求OCR。原页未载入时明确提示。关闭面板不停止OCR，状态请求也不清空PDF或强行刷新文件。原useReaderDocument的轮询预算耗尽文案明确只是停止刷新，不能伪装任务已暂停。

新useReaderOcrStatus单独管理状态轮询，后台标签页减频且有10分钟预算。调用失败可重试；来源修订变化保留服务器脱敏状态及新正式内容入口，禁止旧身份上的控制，不自动重新绑定或重载原PDF。

## 权限、任务身份与复用

新增GET/POST `/distribution/assets/{asset_id}/ocr-status/`，复用现有_public_asset和发布资格、catalog_ocr.progress_row及ocr_workspace.task_command；不另建处理队列或Worker。GET按白名单投影，不返回未公开OCR文字、人工改稿、Provider、文件路径、后台错误或原始stats。

任务严格匹配精确来源/受核验staging关系，校验源文件hash/实际页数。normalized文字stage复用原PDF字节，不能将另一个可搜索PDF的hash当当前锚点；已完成与公开结果须核对当前CatalogPublicationRevision/DocumentRevision及KnowledgePublicationEvent，百分比和succeeded本身不是公开证明。

后台查看入口需access_back_office，暂停/继续另需can_retry_jobs。公共读者只能读取允许的状态和已公开正文；未发布处理内容只提供授权管理预览。原Reader工具入口误用can_view_system_status已改为后台访问能力。

写入携带X-Reader-Owner、固定request_id、精确job_id、原样job_version、source_sha256和document_revision_id；事务按Edition/Asset/Job锁与当前来源校验，旧请求不得操作新任务。继续复用既有全局暂停、来源保护和已保存页续跑规则。回执使用既有AuditEvent，不新增模型或迁移。

响应未知时保留完整命令，先GET同request_id查回。只有没有回执且文件、任务和修订均未变化时重发原命令；不另建nonce。待确认期间锁面板关闭/离开并提供查回。用户可经明确两步放弃本页核对来解锁，此动作不取消任务、不发送新命令。权限失效清除管理内容，同一账户降权保留未知命令，显式放弃前不静默解锁；换账户取消旧链。旧reader_asset发布后失效时，保留404并提供当前文献详情新标签入口，由详情重新核验新正式版本。

## 契约、静态与待验收

OpenAPI在SQLite内存配置生成tmp/stl4-reader-ocr-schema-20261020.json，0错误/10条既有Home/Scholar/Topic提示；新增1路径至175，原174全部保留，前端生成类型同步。7 Python AST、6目标ESLint（1既有img提示）、CSS143/49节点退出0；全量TypeScript最终32523退出0。19后端函数39场景、15前端合成OCR契约场景仅编写未运行，准确命令记在VALIDATION。

本单元不修改继承未提交的OCR执行、备份、入库或检索实验文件。正式统一验收仍需真实OCR/队列/NAS、当前页落盘暂停、继续/失效来源/幂等竞态、公开与管理权限、移动弹层和全部状态图。没有执行测试、浏览器、构建、迁移、OCR/模型/NAS、检索质量评测或生产操作。

恢复时共同读取reader_ocr服务/serializer/view/路由、ReaderOcrStatus及hook/client/CSS、ReaderPageThumbnail、ReaderShell和局部样式、OpenAPI/生成类型与新增用例/配置。PDF40其余状态沿READER_20261020记录；全站209视图/B01–B06尚未完成。
