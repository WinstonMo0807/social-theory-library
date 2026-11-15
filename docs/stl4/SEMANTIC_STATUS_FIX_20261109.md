# 观点检索状态与 NAS 内存核验

本轮目标是解释运行维护页的语义索引、语义模型不可用，修复检查对象错误，并核查 NAS 内存风险。用户明确“批准，上线”后，已完成正式发布、内核 swap 限制和线上页面核验。当前模型显示可用，索引显示部分就绪，11 个当前公开版本中 6 个完整覆盖、5 个继续处理。

## 2026-11-09 正式发布结果

- API 六角色已统一切换到 `4.0.0-20261109-semantic-status-r2`，Web 为 `4.0.0-20261109-semantic-status-r1`。NAS 发布回执分别为 `2026-11-09T07:32:21Z` 与 `2026-11-09T07:33:39Z`。5 个后端目标文件和 1,846 个 Web 构建文件逐项匹配；运行时生成的 runtime-config 另与上线前比较，一致。
- NAS 上使用 512 MiB 内存上限、禁网、无业务挂载的临时容器执行 Django check，通过后退出。最新数据库备份 237,315,032 字节，通过 pg_restore 完整读取，SHA-256 为 `fa4f9259d8a5f337e84d33395def2cb07f3d42f7ac91148e6f31078da926a8ac`。恢复目录 `/volume2/library/stl-releases/20261109-semantic-status-r2/recovery-r2` 保存准确 Compose、显式环境文件及旧容器/镜像信息；Web 恢复资料在同 release 的 `web-recovery`。
- 任务仅暖退出。现场在途索引任务正常完成约 258.55 秒的一轮处理后退出；上线后按需管理器恢复，处理 Worker 健康，1 项执行、4 项排队。闲置独立查询/索引 Worker 保持 created，OCR 保持暂停。
- 公网浏览器实际读取运行维护页，确认“语义模型 可用”、`intfloat/multilingual-e5-small`、384 维及“语义索引 部分就绪”“6 / 11”。首页、后台、知识页及 API 就绪检查均返回 200。
- 发布后当前活动索引有 8,265 条远端文档，8,265 条带向量文档；当前公开修订中完整覆盖的原文片段为 6,054 条。使用当前公开文档的已有 384 维向量发起真实查询，返回 3 条命中，约 0.403 秒。没有进行新问句编码和完整重排验收。
- 搜索 RAM 上限仍为 768 MiB，swap 从内核实际无限额改为 768 MiB，Docker RAM+swap 总额为 1,536 MiB。读回 `memory.max=805306368`、`memory.swap.max=805306368` 后才将覆盖文件加入活动 Compose；搜索容器 ID 和启动时间不变，索引保留。
- 第一次资源应用在配置比较时安全中止，原因是本机 Compose 将字节额度序列化为字符串，脚本预期整数。当时尚未执行 docker update。修正比较类型并核对原恢复材料后再次执行成功，未放宽其他配置比较。
- 验收快照 NAS MemAvailable 为 2,017,288 KiB，约 1.92 GiB；swap 总计 6,094,828 KiB、剩余 747,932 KiB，仍有约 5.10 GiB 在用。API、普通 Worker、处理 Worker、搜索和推理容器均无 oom/oom_kill；推理 RAM 1,600 MiB、swap 200 MiB，线程和 batch 均为 1。原推理容器及启动时间保持。此为现场观测，不是长期满负荷稳定性保证。
- 发布回执、资源前后值、文件哈希及真实检索结果已保存在 `tmp/semantic-status-20261109/`，NAS 同 release 的 `verification-result.json` 可复核。源码检查点 `refs/codex/checkpoints/semantic-status-20261109` 指向 `80dba334d2b9c8433f3f049a438cdb0493f46b1b`，未移动分支 HEAD 或改动用户暂存区。

## 已核实的原因与范围

- 运行维护页检查 `SemanticIndexVersion.objects` 的旧 semantic 家族和 MiniLM Hugging Face 缓存。当前生产使用 discovery 家族，活动编码模型为 `intfloat/multilingual-e5-small`，384 维，离线 ONNX CPU 推理。旧索引为空及旧模型缓存不存在，不能用来判断当前观点检索失效。
- 活动索引为 `discovery_v308_abb05eb02b7744f8a6c7f24dfe0d9336`。现场读得 8,042 条远端文档、8,042 条带向量文档，与本地 DiscoveryDocument 的 7,978 条原文、37 条知识入口、27 条策展记录相符。该总数包含处理中与旧修订记录，不等于当前公开修订覆盖率。
- 11 个当前公开、可检索版本中，6 个当前修订完整就绪，5 个仍待完成。现场再次读得 1 个正在执行、4 个排队，检查点仍更新。两条历史失败分别来自 11 月 7 日和 10 月 26 日，未将其一律重试或当成当前 5 项失败。
- 模型健康接口报告本次进程已实际执行 E5 编码和深度 EG2 编码；当前进程的 mMARCO 重排尚无执行记录。历史读者检索记录包含基础原文召回及 EG2/BGE/ConvMemory 成功记录，同时保留过规范化服务不可用警告。因此不宣称每次查询、所有通道或检索质量均已验收。
- 以当前公开修订中的一个已有向量发起真实 Meilisearch 向量查询，384 维、返回 3 条命中，约 0.397 秒。此检查没有加载模型、创建检索会话或修改业务数据；不等同于新问句编码和完整读者端端到端测试。

## 修复内容

1. 运行维护页在 Discovery 启用时使用当前观点索引及其模型身份，保留旧配置未启用 Discovery 时的兼容行为。
2. 当前公开修订覆盖不足时显示“部分就绪”及实际分母，不以活动版本存在冒充覆盖完成。
3. 模型检查读取有界健康文档，对照活动索引的模型制品和向量维度。区分已执行、仅准备、身份不符与未连通。按需服务未连通时保留未知，不能直接认定是休眠或损坏。
4. 状态页、专业自检和索引详情的检查不触发模型按需启动、不载入权重、不建立索引。周期巡检使用真实活动索引统计；人工恢复动作按当前启用的索引家族路由。
5. 前端补齐状态、模型版本、覆盖数及检查时间的中文说明，沿用当前页面布局。

未修改模型、推理内存上限、并发、原件、人工修订、权限、数据库结构或索引内容。

## 发布前内存观测与应用边界

NAS 总内存约 7.63 GiB，本轮 MemAvailable 约 1.26–1.76 GiB；交换空间使用约 5.08 GiB。推理容器内核 RAM 上限 1,600 MiB、swap 上限 200 MiB；处理 Worker RAM 上限 768 MiB、单并发；API 512 MiB。读取到相关当前容器 oom/oom_kill 均为 0，但推理曾触及内存上限，不能据此保证长期无 OOM。

Meilisearch RAM 上限 768 MiB。Docker 元数据记录 MemorySwap 与 RAM 相等，内核 `memory.swap.max` 却为 `max`，实际已有约 620 MiB swap。这是配置与执行状态不一致，不能宣称目前已禁止 swap。Docker 官方说明中，MemorySwap 表示 RAM 与 swap 总额度，二者相等才应禁用 swap，见 [Docker 资源约束](https://docs.docker.com/engine/containers/resource_constraints/)。

独立守卫脚本 `tmp/semantic-status-20261109/limit_search_swap_after_approval.py` 默认只读；用户批准后已使用 apply 执行。保持 RAM 768 MiB，把 swap 从实际无限额限制为 768 MiB（Docker 总额 1,536 MiB），没有重启搜索容器或重建索引。执行前已确认宿主机至少 1 GiB 可用内存、当前 swap 低于上限且留有 64 MiB 余量、准确容器归属及 RAM 上限一致。执行后读回内核值，才写入持久 Compose 覆盖，结果见上方正式发布记录。

## 验证与交付

- 最终 `pytest tests/test_discovery_status_20261109.py tests/test_discovery_admin_v308.py tests/test_stl4_service_identity_20261025.py -q -p no:cacheprovider`：19 项通过。
- 另运行 system-status 旧配置兼容选择集，18 项通过（与上述检查有重叠，不能相加）。
- 从当前生产 Web 对应的隔离源码准备候选，仅替换状态组件；Vinext 正式构建退出 0，TypeScript 定向工程检查退出 0。首次准备遗漏构建配置目录导致类型检查失败，补入原配置后复测通过；本机没有 npm 命令，改用已安装的 Vinext CLI 执行相同构建。
- 4 个既有后端目标文件与当前线上文件 SHA-256 逐项一致后再制作修复包，新增 1 个模型状态模块。生产 API/六角色基线镜像 `0ad687520b142797198d3a8e1710d9b047e58cc409cae9fdfbe9b967f2c35563`，Web 基线 `68985623d6e520b448f0c928cb0a99a85068c62acd75e26690ac62111437e979`。
- 已发布 API `4.0.0-20261109-semantic-status-r2`，镜像 `7a37331f1aa2c2362f93909a53d3dcb3ae3693d82cc9f4ca84e1f056ce83e44c`；Web `4.0.0-20261109-semantic-status-r1`，镜像 `ba8867c7ac3aa629b621f489604cbe8741dcfb9fcb16c2c31ab3d74b57c38b95`。均在本机打包，NAS 只加载；仅有已退出的受限临时启动检查容器，没有增加常驻模型服务。
- 修复包、清单、真实线上差异、部署守卫、资源只读预演及验证日志位于 `tmp/semantic-status-20261109/`。只读运行证据位于 `F:/书库策展/策展工作区/语义检索修复-20261109/`。

## 上线与回退范围

用户已明确批准具体修复包；上传、加载、生产切换和 swap 限制均已完成。活动 Compose 入口仍为 `/volume2/library/stl-releases/20261107-r1/public/compose-command.json`，末尾已追加本次 API、Web 和 `bounded-search-swap.compose.json` 覆盖，不以旧文档的镜像标签推断当前版本。

API 与 Web 守卫发布脚本已执行，执行前核对准确基线镜像、当前 Compose 和 OCR 暂停状态，保存最新数据库包并完整解压读取验证。任务进程仅暖退出，超过时限则中止，不强杀在途索引。只更新 API/Web 及共用 API 镜像的任务角色，闲置查询/独立索引角色保持不启动。模型、数据库、Redis、搜索、网关和隧道保持身份；资源 cap 作为单独步骤完成核对。

回退只恢复代码镜像和准确 Compose，不以旧数据库覆盖后续策展数据，不完整 compose up、不清队列、不恢复旧模型。最终发布前如发现其他对话已更新镜像，应重新基于新版本制作候选，不能覆盖。

尚未验证项目：新问句完整检索与重排、待处理 5 个版本的最终完成、长期满负荷稳定性。Linux 启动、生产状态页面、真实已有向量查询及 swap 限制实际生效已完成核验。
