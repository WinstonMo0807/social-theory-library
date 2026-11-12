# MCP文件上传交付

日期：2026-11-12。用户要求加入文件上传，随后明确所有校验和限制交网站设计，不增加多余测试。本轮按此收窄为原网站上传接口的转接。

## 已实现并部署

原七个策展工具保留，新增`stl_prepare_uploads(request_id, files, policy)`和`stl_get_ingestion_status(request_id)`，总计九个。准备工具调用原`UploadWorkspaceView`建立或恢复本人批次，文件清单只含name/size。请求及文件句柄保存在既有AuditEvent中，无新增业务表。状态工具调用网站原分片接口，返回上传、派发、处理状态及已生成的Work/Edition ID。

二进制通道为`/mcp/uploads/{request_id}/{file_id}`，GET读取网站分片状态，PUT其下的分片编号传输字节。使用原MCP认证，不把馆长JWT或Session交给客户端。转接时使用固定受信账户调用原DRF视图，原CanUpload、批次归属、版本/请求回执和文件规则继续执行。

本机辅助程序`tools/stl_mcp/upload_client.py`负责选择的文件、直接传输和本机续传记录；PDF不进入模型工具参数。程序输出request_id，断线后`--resume 请求UUID`复用网站已接收的分片。凭据沿现有DPAPI辅助程序，也支持STL_MCP_TOKEN环境变量。记录在忽略目录`.local/stl-mcp/upload-clients`，不含明文凭据。

## 按用户最新要求保留网站权威

本轮撤掉拟增加的MCP端文件哈希预检、格式/大小/数量判断、独立策略枚举、强制去重和额外上传范围开关。客户端不预读整份文件计算哈希，不按内容去重。策略字典透传原网站，未提供时由网站默认值决定；网站拒绝信息及状态原样返回。文件的最终哈希、PDF判断、批次数量和大小仍由原网站上传代码处理，没有删去网站自身的保护。

分片大小读取网站`MAX_UPLOAD_CHUNK_BYTES`，传输路径沿用原网站ingestion限流、连接和正文配置。公网MCP已有Bearer/Host/Origin及控制请求保护保持，未开放匿名入口。获得上传能力不自动替换现有阅读文件、改人工锁或发布策展内容；此通道接收新增入库文件，替换现有PDF继续使用网站版本与文件工作区。

## 部署记录

release为`/volume2/library/stl-releases/20261112-mcp-uploads-r1`。MCP复用当前API镜像`sha256:08866216dcd234659cb6785d0be8aacc064bfc593dacd4d8b74f2ee94d83851c`，保留主题关系修复。新增原incoming目录的读写挂载，其余原件/公开文件仍只读，无Docker socket、模型或私人文件挂载。只更新独立MCP和新增上传代理路径，没有重建API/Web、修改DNS/Tunnel、运行迁移或部署第二套上传存储。

MCP保持单进程/0.5CPU，内存配置512MiB，上传使用原任务系统，不在MCP进程运行OCR或模型。旧MCP容器以`stl-mcp-before-uploads-20261112`停用保留；原容器配置及Nginx模板留在本release受限文件中。`deploy/mcp/upgrade_uploads.py`保留部署/失败恢复步骤；没有删除旧容器、卷、原件或计划。切换时保留原内部地址，代理继续原域名。

服务启动及Nginx自身配置加载已完成。按用户要求，**未新增或运行上传测试、未运行原策展回归、未选择真实PDF做试传**；源码和启动状态不作为上传成功证据。上传、断点续传及入库结果由后续策展对话实际使用时的网站回执确认，本轮没有虚构文件上传记录。

## 使用入口

在本机调用`tools/stl_mcp/upload_client.py 文件路径`；多份文件可列在同一命令。可选`--access`、`--ocr`、`--duplicates`为网站现有策略值，不填则沿网站默认；本机保留续传记录。现有MCP地址和凭据配置不变。上传收到后根据`stl_get_ingestion_status`返回的实体ID继续使用原策展工具；接收完成、入库处理和正式公开分别读取实际状态。
