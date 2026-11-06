# STL 4.0 正式运营切换包

## 2026-11-07 已正式上线

用户已最终确认“确认，现在按清单清理并切换公网”，本清单已执行。正式入口 https://books.winstonmo.com/ 为欢迎页，进入书库到 /home；内网 http://192.168.5.6:18084 接同一正式栈。浏览器实际核对欢迎页、点击进入首页、空馆藏/空策展、访客探索跳转登录、注册无需验证提示。截图为 output/launch-20261107/public-live-welcome.png、public-live-home.png、public-live-registration.png。

16 个正式服务容器运行，带健康检查的均 healthy；旧预览栈运行数 0，旧 PaddleOCR 停止，API/四 Worker/Beat/Web 共 7 个容器的镜像 ID 与上述候选精确一致。正式库 library_stl4_20261107、业务目录 /volume2/library/stl4/storage 已使用；当前 0 公开作品、版本、策划、学者、主题、知识条目、时间线，3 个正式学科顺序为社会学、人类学、民族学。13 个资产与 28 个业务文件保留，4 个账号及私人数据核对一致。旧公网新增的 1 条令牌撤销已合并，8 条原撤销记录全部保留。筹备中的 58 个 PDF 未处理。

最终停写快照位于 NAS /volume2/library/stl-releases/20261107-r1/final-recovery：生产包 8,477,697 字节、候选包 17,432,442 字节，均在独立库实际恢复，22/49 张保护表摘要一致，文件逐个核对；停止后的候选 Meili 索引另备份 356,710,400 字节。旧库、原目录、配置及回退镜像保留。上线后另有 stl4-after-launch.dump 15,399,713 字节，**此上线后包未再次独立恢复**，不混称前面的恢复证据。

正式 API /ready 200、version=4.0.0、0 待迁移；首页/学科/策划接口 200，未登录探索、PDF 访问/下载、管理 schema 均 401。实际 RapidOCR 识别后 /ready 200，管理端同源 OCR 记录 cf8bf748-9b84-442a-b1b7-1038c89e97d0 为 healthy，Worker/Beat 同源检查正常；任务清理后的四队列与 unacked 均 0。Redis/Meili/DOCX、其余带健康检查服务均正常。推理模型沿用既定配置，服务 prepared/manifest_ready，未重复执行质量评测或将冷启动模型状态冒充已完成本次推理。

PUBLIC-BIND-01 D：第一次真实公网检查发现 compose.stl4-cutover.yaml 中带额外缩进的多行 shell 命令保留换行，Gunicorn 在 application 参数后启动，后面的 --bind/threads 等参数未生效，造成仅监听 127.0.0.1、edge 连接拒绝。修复为一行完整 exec 命令，重建 API 并重新载入 edge。随后内网 HTTP、真实公网欢迎页和首页通过。保留最初失败日志，不以容器内 /ready 正常替代外部页面验证。

Cloudflared 与 PostgreSQL 原容器保持，隧道凭据/协议核对一致，未改 DNS。26 个其他容器身份与启动时间不变；独立架构展示由并行会话从 v5 更新到 v6-r2，本任务没有操作该容器。NAS 旧部署目录新增 STL4_CURRENT_RELEASE.md 和 stl4-compose.py 指向完整新组合；日常命令使用 `sudo -n python3 /volume2/library/docker/social-theory-library/stl4-compose.py ps`，不要按旧三层组合重新启动历史版本。旧模型路径包含 stl-previews 仍为受保护依赖。

本轮移除的 117 个无引用测试镜像标签保持准确；回退所需旧镜像、数据卷及模型保留。B 视觉/管理员操作验收随用户批注推进；邮件/Google/生成式中转配置依既定决定后续处理。未替用户创建公网测试账号或操作其密码；实际账号登录及管理员日常操作留给本人验收。没有宣称像素一致、全站业务及长期稳定性验收完成。

新增证据在 tmp/stl4-launch-20261107/：cutover-freeze.log、cutover-drain.log、account-delta-final.json、cutover-backup.log、cutover-materialize.log、cutover-cleanup-r2.log、cutover-revocations.log、cutover-verify-application-r3.log、cutover-ocr-ready.log、cutover-binding-fix.log、cutover-edge.log、cutover-health-final.log、cutover-final-state-r3.log、current-release-entry.log。工具对 Compose run 的不支持参数、非 JSON schema 响应及不存在预览 Searxng 的初轮探针错误均保留，不列为产品缺陷。

## 以下为切换前准备记录（上述发布已完成）

2026-11-07：用户已要求清理全部示例内容并正式运营；已确认开放注册、不要求邮箱验证，首发仅书库账号。邮件接口保留，邮件密码重置未配置，现有人工找回申请继续提供。用户确认基础学科为社会学、人类学、民族学；筹备中的 58 个 PDF 不属于此次示例清理范围。

本轮已更新内网候选，**尚未清理真实示例数据、尚未切换 books.winstonmo.com**。按 AGENTS.md“生产不可逆操作先提交具体影响、备份恢复核验并取得最终确认”，完成下列准备后等待一次具体切换确认。当前公网仍为旧版；其他会话的 preview.winstonmo.com 架构展示独立保留。

## 版本与恢复位置

- API、四个 Worker、Beat：`social-theory-library-api:4.0.0-20261107-r1`，镜像 `sha256:d5ad61e3a20a5fbfee438aa46a8f07ab77a97d7d2f062778e1613b95ea20ec4b`。
- Web：`social-theory-library-web:4.0.0-20261107-r1`，镜像 `sha256:f6de047aed7be0566b872999e81a2dd1a496abfa313cffc3cff589c2238c09f5`。
- 内网：`http://192.168.5.6:18084/`；根路径欢迎页，`/home` 为书库首页。
- RapidOCR3、既定推理服务 r2、DOCX 服务沿用已验证候选，不替换模型、不重复补写 EG2。
- NAS 发布配置：`/volume2/library/stl-releases/20261107-r1/public`。该目录 0700，环境文件、完整解析结果与备份 0600；不可外传或提交 Git。
- 新鲜准备备份：`/volume2/library/stl-releases/20261107-r1/recovery-r2`。
- 本轮预览回退：`/volume2/library/stl-previews/20261026-r1/launch-api-4-20261107-recovery`、`launch-web-4-20261107-recovery`，保留 API64、Web132 与配置。

运行文件核对：788 个后端文件、3008 个前端构建及静态文件与工作区一致。此候选包含之前已有的工作区修改；本轮 Git 提交仅收录本轮改动，不以一个提交号冒充全部既有修改的独立重现凭证。

## 数据处理清单

| 对象 | 现有数量 | 切换时的处理 |
|---|---:|---|
| 示例作品 / 出版版本 | 3 / 3 | 原发布命令下架、回收，保留文件与历史 |
| 特别策划 / 所属条目 | 1 / 3 | 撤下活动版本与展示，保留策划修订 |
| 策展项目 | 1 | 使用原归档接口，保留项目记录 |
| 学者展示 | 7 | 回收展示，人物身份和引用历史保留 |
| 主题 / 理论知识条目 | 3 / 3 | 撤下并回收 |
| 关联示例时间线 | 3 | 撤下并回收 |
| 原学科政治学、哲学 | 2 | 撤下回收，不改名冒充新学科 |
| 社会学 | 1 | 保留原身份，排列第一 |
| 人类学、民族学 | 2 | 建立新身份，经原修订发布流程发布 |

保留 4 个既有账户及密码哈希、角色、私人资料、阅读历史与进度、所有原件、人工修订、批注和失败记录。关联已下架作品的私人记录仍保留，不能通过私人链接绕过下架权限。旧生产数据库和文件作为回退保留；不把旧任务、过期缓存与旧业务记录盲目拼入新库。不使用会清空私人资料的历史 `reset_public_library.py`。

`recycle-rehearsal-r5.log` 已在独立恢复库演练上述处理，操作全部回滚，不派发任务。演练后展示对象均为 0，正式学科为社会学、人类学、民族学；账户、reading 全表及 Asset/Page/目录修订/文本修订摘要不变。正式执行仍须在停写后核对新增账户和私人数据；如出现增量差异，先合并核对，不直接覆盖。

## 本轮修复及证据

- **D REGISTRATION-LAUNCH-01**：原登录本来允许未验证邮箱，但注册成功页仍要求去邮箱验证。修改 `api/accounts/views.py`、`web/components/auth-form.tsx`、`auth-page-frame.tsx`，按实际邮件可用状态显示，未配置时注册后直接登录，找回页使用原人工申请。未把邮箱标记为已验证，未取消 CSRF、权限、限流或安全 Cookie。
- **D RECYCLE-LEGACY-SLUG-01**：`publish_editorial_revision()` 的 `full_clean()` 会因既有中文 slug 阻止单纯下架。实际克隆清理触发该错误。最小修复只允许纯状态撤回保留原 slug；其他编辑、重新发布继续验证，正常修改无放宽。
- API/Web 版本号统一为 4.0.0；OCR 镜像内部已有版本标识保持真实，不据标签推断算法版本。
- **D OCR-STARTUP-READBACK**：`/health` 200 并不代表模型已运行。冷启动 `/ready` 未就绪；原有 `/ready?deep=true` 在 7.968 秒内完成一次真实识别，随后 `/ready` 200，available/runtime_verified 均 true。管理端同源健康记录 `1e39329e-e736-4547-9b78-6d409288ea9f` 为 healthy。未重跑整书 OCR，不修改代码制造绿色状态。

验证：注册/CSRF/越权注入/真实 Cookie 登录定向测试 1 项通过；旧 slug 撤回与保持编辑验证测试 2 项通过；TypeScript 和 Vinext 构建退出 0。浏览器实际查看注册、找回入口，没有注册真实账户或提交找回申请。截图 `output/launch-20261107/registration.png`。

服务读回：API 4.0.0 ready、数据库连接成功、0 待迁移；四 Worker 与 Beat 运行；Redis、Meilisearch、DOCX 响应正常；OCR 如上完成实际就绪验证。推理服务 manifest_ready=true、status=prepared，冷启动 ready=false 如实保留，本轮不重跑检索质量评测或将安装就绪当推理通过。既有实际检索证据继续有效，但不能代表本次全站或长期稳定性验收。

NAS 脚本访问公网返回 403，而实际浏览器可正常打开旧公网首页，因此不把该 403 记为全站故障。最终公网必须在切换后用真实浏览器重新读回。

## 备份恢复证据

| 准备快照 | 字节 | 独立恢复库 | 恢复核对 |
|---|---:|---|---|
| production.dump | 8,465,185 | stl4_verify_production_20261107 | 22 张保护表摘要一致，4 账户 |
| candidate.dump | 17,418,858 | stl4_verify_candidate_20261107 | 49 张保护表摘要一致，4 账户 |

原生产业务目录当前 0 文件；候选 archive/public/private/incoming 共 28 文件、99,953,690 字节，逐文件哈希与归档内容一致。恢复库在预览 PostgreSQL 中，与源库隔离。准备快照没有停写，**不能充当最终停写快照**；切换窗口须再备份和核对增量。

备份 SHA256：

- production.dump：`7d08c713004fed97d75b61cb810956746ec900ae777afc245306fa590e56fad2`
- candidate.dump：`3ea172376e71c399dc438225771ea498b2679758dfc5cae7bdcbf05aa3009bd2`

本轮早期根目录权限/归档权限探针失败和恢复成功记录均保留；没有因探针失败删除数据。

## 已解析的正式组合

`compose.public.yaml` + `compose.cloudflare.yaml` + `compose.discovery.yaml` + `compose.docx-preview.yaml` + `compose.stl4-deep.yaml` + `compose.stl4-cutover.yaml` + 发布目录的 `compose.stl4-launch.yaml`。

完整命令保存在受限目录 `compose-command.json`。`docker compose config` 与严格公网 Django 设置加载均退出 0；全部指定镜像本机已存在。不是已部署证据。

- 继续使用项目 `social-science-library`，域名 books.winstonmo.com，不新增公网服务端口。
- 使用现有生产 PostgreSQL 的新数据库 `library_stl4_20261107`，保留旧数据库；POSTGRES_DB 初始化值沿用当前生产，应用 DATABASE_URL 指向新库。
- 业务文件目标 `/volume2/library/stl4/storage`，精确复制候选业务目录并核对哈希，原目录保留。
- 选定模型目录沿用现有已验证路径；当前路径包含 stl-previews，**这些路径是受保护模型依赖，不得按目录名认定可删**。
- Meilisearch 使用候选索引卷 `stl4-preview-20261026-r1_meilisearch_data`，接管前停止原持有容器并留索引快照；同一卷不得同时挂给两个服务。沿既有撤回任务清理示例公开投影，禁止重复 EG2 全量补写。
- Redis 使用新正式卷，原卷保留；先停止调度和排空任务，不能清队列代替排空。
- API、四 Worker、Beat 统一镜像和 HTTPS 配置；RapidOCR 替代旧 PaddleOCR。带限制的业务文件访问继续走 API，不公开原件目录。
- 安全 Cookie、CSRF、权限和公网模式开启。邮件服务未配置，按用户决定不阻止注册；生成式中转服务仍须管理员后续配置，未配置不声称可用。
- edge 只绑定 NAS 的 LAN 地址 192.168.5.6 的 3000/18080/18082/18084；不新增路由器转发。局域网与公网接到同一新版本、数据库、任务系统。
- 不重建 cloudflared、不改 DNS 或其他域名；保留现有隧道网络、独立架构展示、政策研究服务及其他 NAS 应用。
- 生产视觉批注工具仍关闭，原批注保留；后续按用户批注修订。未宣称 206 视图逐像素验收通过。

## 最终确认后执行顺序

1. 再核对镜像、源文件摘要、生产/候选账号与私人数据增量、空闲容量、容器身份，记录受限恢复点。若其他会话改变书库生产配置，先核对变化，不能覆盖。
2. 对书库公网及内网入口临时显示维护页，阻止新写入；停止两边 Beat，等待现有四类队列和活动任务完成，再停业务 API/Web/Worker。队列不清空，有活动上传/OCR/检索就等待其结束。其他域名和应用继续运行。
3. 在同一停写窗口重新备份两边数据库、业务文件、环境与镜像信息，核对保护摘要；复制新业务目录，恢复候选到新正式数据库并核对。新库验证失败则保持旧库及原服务可回退。
4. 对新正式库执行已演练的回收/归档与三学科修订发布。保留所有原件与私人数据。核对当前公开来源、欢迎页选书、策划、时间线及权限过滤都不再展示示例。
5. 停止预览 Meilisearch/OCR/推理/DOCX 等将被正式实例接管的服务；备份停止状态索引卷。旧 PaddleOCR 停止，旧镜像和旧配置保留。按明确服务列表更新正式实例，避免无区别重建 cloudflared、PostgreSQL 与其他独立服务。
6. 启动 API、Worker 与新版 Web，完成迁移状态读回、真实 OCR 就绪探测和管理状态读回，等待示例撤回投影任务结束。核对匿名保护、登录、管理权限、欢迎页及 /home，检查状态而非仅看容器 running。
7. 更新同一个 edge，公网和内网指向同一正式栈；浏览器实际检查 books.winstonmo.com、欢迎页进入首页、账号入口和匿名受限入口。验证后恢复入口并启动单个正式 Beat，预览重复业务服务保持停止。
8. 留最终恢复点与服务清单。旧生产版本、数据库/文件、即时回退镜像不在首轮删除；其余确认无引用的测试镜像才清理。任何失败保留记录，不伪造绿色状态。

回退：对新入口重新维护并暂停新写入，先备份新版本期间的账户和业务增量；用保存的原 Compose、环境、镜像、数据库和文件恢复旧服务及 edge。不能把已发生的新用户写入直接丢弃。新正式库与新业务目录保留排查，不执行 down -v 或递归清理。

## Docker 清理及真实待办

本轮已从旧 API/Web 预览标签中清理 117 个无容器引用、无恢复点引用的标签，0 失败。扫描了 208 个恢复/配置文件并保护 114 个引用标签；未用 force/prune、未清数据卷、模型或其他应用。117 是标签数，不是回收空间或独立镜像层数。计划/结果在 NAS 发布根目录与本机 `tmp/stl4-launch-20261107/cleanup-*.json` / `cleanup-result.log`。

- **B** 正式数据清理与公网切换：准备完成，待最终具体确认及上述停写执行。
- **B** 全站视觉和管理员交互：由用户批注和运营期实际操作验收；不重新列为未开发。
- **C** 邮件/自动密码恢复：用户选择后续配置，首发人工申请。
- **C** Google 登录、中转生成式服务：按既有决定后补/管理员自行配置，现有账户与检索能力保留。

主要证据位于 `tmp/stl4-launch-20261107/`：`registration-check.log`、`recycle-check.log`、`recycle-rehearsal-r5.log`、`typecheck.log`、`web-build.log`、`image-build.log`、`preview-api-deploy.log`、`preview-web-deploy.log`、`source-inventory-final.log`、`backup-restore-r3.log`、`public-config.log`、`public-settings-check.log`、`ocr-ready.log`、`worker-ocr-ready.log`、`service-health-final.log`、`final-preflight-r3.log`。探针将已停用的旧 PaddleOCR 计入所有候选容器而触发的断言失败不属于 RapidOCR 故障；最终读回明确其为已停用历史容器。
