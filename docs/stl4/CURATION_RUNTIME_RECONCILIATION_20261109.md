# 2026-11-09 策展发布队列恢复检查

## 问题与修复范围

实际策展中，B056等作品的正式发布命令已接受，投影需求却持续等待普通执行能力。只读核验发现34,926条claim_extraction需求等待llm_small，普通projection仅5条。reconcile_projection_runtime调用reconcile_capability_runtime，每条未结束的claim需求各查询一次EvidenceSpan。恢复任务实际耗时80—85秒，30秒一次、25秒过期的心跳在普通队列中失效，90秒的执行器登记随后到期。

仅修改api/common/task_runtime.py。按200条需求分批查询仍有效的证据段，将结果交给原有有效性检查；其他任务类型的检查不变。保留原事务、锁、历史状态、来源失效取消规则与任务派发流程。不删除等待需求，不启动旧模型，不直接改数据库完成状态。

## 验证

本机项目.venv、SQLite内存库及memory broker运行以下测试，退出0，23 passed：

```
python -m pytest tests/test_capability_reconciliation_batch_20261109.py tests/test_dependency_runtime_v300.py tests/test_projection_propagation_v300.py -q -p no:cacheprovider
```

新测试确认401条有效等待需求仅4次查询，并保留等待状态及输入；来源段过期、文档修订过期和来源段缺失仍按原规则取消。既有依赖恢复及发布投影测试保持通过。

## 发布准备与当前状态

本机从已导出的干净API基础文件打包，14个resource-r4覆盖文件哈希保持，另加入本次公共调度文件。未混入其他未提交改动。镜像social-theory-library-api:4.0.0-20261109-curation-runtime-r1，ID 9dbc78115c8647cd853c55483f36804f0f98594428eed1d3b3309b9efa09a38d；归档SHA256 3324d67c01da736d1c44a00b5d8f3e485ed6b5df49a44b31df285d0e2210648f。

NAS仅load，隔离容器限制512MB/0.75CPU、禁网只读，manage.py check退出0。发布脚本只替换API、普通Worker、Beat和3个按需处理角色的镜像；保留Web及存储服务身份、OCR全局暂停、原件和历史。活动Compose全部参数沿当前正式配置追加，无完整compose up。

第一次备份超过180秒时限，未切换任何服务；已明确识别并中断本次遗留pg_dump，保留失败备份作为运行记录。第二次备份采用压缩级别1和900秒时限，恢复验证改为完整pg_restore --file=/dev/null读取，非仅列目录。恢复目录/volume2/library/stl-releases/20261109-curation-runtime-r1/recovery-r2。

当前仍在备份及正式切换阶段，不能视为已上线。必须继续核对实际发布队列、执行器心跳、作品公开页及NAS资源。运行脚本和归档位于tmp/curation-runtime-20261109，不纳入Git。
