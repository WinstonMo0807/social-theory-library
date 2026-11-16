# NAS 清理、存储读取与 R2/子学科检查（2026-11-16）

## 范围与存储事实

用户授权清理已退出计算职责的 NAS 上书库相关镜像，并在保留 NAS 存储职责的前提下检查、优化通信；随后要求纳入 Cloudflare R2 与规则，另提供子学科页面缺少原文入口的截图和网址。

Mac 的 Lima 通过 NFS v3/TCP 挂载 NAS 的 archive、public、private、incoming、backups 五目录，API/worker 使用原挂载，Nginx 对 public 只读。rsize/wsize 已为 1 MiB，hard、同步写与导出权限保持。Mac en0 为 1000baseT 全双工，媒体能力中只有千兆；NAS 两口报告 2.5Gbps。五次 ping 均成功，平均 0.573 ms；检查时 NFS RPC 重传为 0。这不是吞吐上限或并发容量压测。

## NAS 镜像清理

按实际镜像 ID、标签和全部容器引用生成私有清单，仅删除可确认无任何容器引用、标签全部属于 social-theory-library / social-science-library / stl- 的旧镜像。没有使用 force、system/image prune，没有删除容器、volume、存储目录、模型或业务文件。

共移除 464 个旧版本对应的 669 个标签，所有操作成功；部分底层共享层由 Docker 因依赖保留。卷可用空间增加 111,250,251,776 字节，约 103.61 GiB，属于当时文件系统差值而非各镜像虚拟体积之和。保留 40 个仍被容器引用的书库镜像以及其他应用镜像。108 个容器 ID、镜像及状态保持，其中运行的 Firefox、mihomo、kspeeder 保持。NFS 服务 active，导出配置逐字一致，五挂载仍在，另一本 PDF 的未用片段读取返回 206。

当前可运行/回退镜像保留；已清理的更旧版本若需要恢复，应从原发布归档或对应源码重建。私有清理计划、逐项结果在本机 migration/nas-storage-20261116/ 与 NAS /volume2/library/stl-operations/nas-image-cleanup-20261116/，不将运行清单提交 Git。

## PDF 读取优化

根因是受保护 PDF 路径对大于 8 MiB 的文件启用 directio，每次重复 Range 都绕过 Linux 文件页缓存。仅将该 location 的 directio 8m 改为 off，保留 sendfile、aio threads、internal 路径和逐请求 Django 鉴权。HTTP 权限和 Cloudflare 缓存规则不变。Nginx 语法验证、热加载成功，持久模板与运行配置同步；入口内存上限仍为 128 MiB。页缓存可由内核回收，没有另建 PDF 副本库。

同一真实 PDF 的同一 1 MiB 片段，顺序三次请求：

| 条件 | 第一次 | 第二次 | 第三次 | 每次 NAS READ RPC |
| --- | ---: | ---: | ---: | --- |
| 调整前 | 148.9 ms | 44.4 ms | 37.6 ms | 32 / 32 / 32 |
| 调整后 | 94.5 ms | 8.7 ms | 8.1 ms | 9 / 0 / 0 |

三次响应字节数及 SHA 一致。后两次重复片段请求不再从 NAS 取数据，热读约快 4.9 倍；不能外推为整站或所有冷读都提速 4.9 倍。未清空内核缓存，未做并发压测，未改 NFS 挂载/同步写策略或申请额外资源。技术语义参考 [Nginx directio](https://nginx.org/en/docs/http/ngx_http_core_module.html#directio)。备份在 Lima /srv/stl/nas-storage-20261116/edge-template-before.conf 与 edge-runtime-before.conf，恢复二者后 nginx -t / reload 即可回退；备份含私有配置，权限 0600。

## R2 与 Cloudflare 实际规则

API 的 R2_UPLOAD_STAGING_ENABLED=true，8 MiB 上传分片、签名 URL 900 秒；CloudProvider/CloudObject 均为空，所以当前在线阅读仍由 NAS 提供，R2 只作上传中转。实查桶无对象、无未完成 multipart 上传。S3 凭据保留最小对象权限，读取桶 CORS/生命周期返回 AccessDenied；通过已登录的 Cloudflare 控制台另行核对，没有扩大凭据权限。

桶 library-upload-staging 位于 APAC，公开开发 URL 关闭，Local Uploads 已启用。生命周期两项启用：默认 7 天中止 multipart；临时上传规则对整个桶 3 天删对象、1 天中止 multipart。这符合临时桶职责，不应把长期阅读文件直接放入该桶。未修改这些清理规则。

域名的 “Bypass cache for authenticated library PDFs” 规则 Active，匹配 books.winstonmo.com 与 /api/distribution/assets/…/file/，动作 bypass。公网匿名 PDF 及 download=1 均 401，页面 private/no-store 逻辑保持；本轮未修改 Cloudflare HTTP 缓存策略。

发现真实迁移遗漏：云端 CORS 仍允许 NAS 192.168.5.6 的 3000/18080/18082，而服务配置预期 Mac .8；公网域名 OPTIONS 为 204，Mac .8 的 3000/18080/18082/18084 均 403，旧 NAS origin 为 204，陌生 origin 为 403。已准备将旧地址替换为四个 Mac origin，保留公网/localhost，仍仅 PUT、Content-Type、暴露 ETag、预检 3600 秒。用户随后明确同意保存，已在控制台提交并读回新规则。签名 PUT 的实际 OPTIONS 回查：公网域名及 Mac 四入口全部 204，旧 NAS 及陌生 origin 403；没有上传对象或开放匿名读取。生产规则快照见 `deploy/r2/upload-staging.cors.json`。持久 Compose 中八个角色的预期 origin 同步补上 18084，仅重建 API 以加载配置，API 镜像不变；其他 18 个运行容器保持，索引/上传 worker 未被中断，未使用 CORS 管理功能的角色将在自然重启时加载新环境。

## 截图中子学科的原文入口

页面 /subdisciplines/ethnicity-and-national-identity 的四本书都有合格文件。《逃避统治的艺术》为 public，另三本 registered。实际 API 在已登录时返回四条 reader_href，匿名只返回一条；前端 taxonomy.server 未转发会话造成错误显示。已改为转发会话、401 保留公共资料且标记会话待恢复；浏览器可能完全省略过期 Cookie，因此无 access cookie 的初始服务端结果也标记待恢复，待共享会话启动成功后只刷新一次。无链接时不再声称缺文件，改为查看版本及阅读权限。

11 项 Web 定向检查通过，覆盖会话、无 Cookie 恢复、分页/404 与服务故障；类型、构建和静态预算通过。最终版公网验证登录四条、匿名/过期一条，均 no-store/DYNAMIC，无旧误报；真实 Edge 重新打开该专题页后四条阅读入口均可见。匿名受保护 PDF 及 download=1 继续返回 401。未修改四本书的权限、版本或文件。

## 发布与回退

12:33:51 +08:00 最终 Web 发布为 `social-science-library-web:subdiscipline-reader-20261116-r2`，image `sha256:ee733ea00a902490213b674c5e59e6632e04fecd44af1b6a4f74e2950e10df17`。3197 个构建文件哈希一致，启动入口生成的 runtime-config 单独验证，共 3198 文件；只重建 Web，其他 18 个运行容器身份/镜像/启动时间保持。

最终版前的子学科镜像 c3413a7415be、任务前的阅读恢复镜像 baef232d2763 都保留。最终 Web overlay 备份 `/srv/stl/nas-storage-20261116/release-before-subdiscipline-r2.compose.json`，需要回退时恢复 overlay 后仅重建 Web。图书文件、权限、数据库、活动索引均没有被本轮修改；没有压测或新建收费服务。

R2 配置同步最终于 12:40:09 完成，API `/api/ready/` 为 200。首轮维护就绪探针漏带 `Host`/`X-Forwarded-Proto` 而被重定向，触发脚本自动恢复原 Compose 并重建 API；补齐与现有健康检查一致的头后重发成功。服务自身健康检查一直正常，不把该探针错误当业务故障，也不声称全程未重启。备份 `/srv/stl/nas-storage-20261116/compose-before-r2-cors.json` 为 0600。云端规则回退和本机环境回退是两项独立操作，恢复旧 origins 会重新阻止 Mac 浏览器上传，应只在明确回迁时执行。

最终 API 运行时生成的 CORS policy 与版本化规则文件逐字段相同。API 配置更新后再次经公网核对该专题页登录/匿名/过期三种响应以及两个匿名 PDF 请求，结果保持 4/1/1 条入口与 401 权限边界。
