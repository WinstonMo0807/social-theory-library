# Meilisearch 状态读取 HTTP 408 修复

2026-11-11 18:10:56，普通 worker-only 已部署 `social-theory-library-api:4.0.0-20261111-index-status-http408-r1`。原等待逻辑只捕获 ReadTimeout，HTTP 408在 raise_for_status 时被当成永久失败。本次继续查询同一 task UID，保留原截止时间，其他HTTP错误仍抛出。没有重发索引内容或改业务完成标志。

25项定向检查通过，隔离镜像 manage.py check 通过。实际运行 indexing.py SHA256为6a6cd629facd8cef64f651068ed5badeffd2c617e21e9cfcaad1e1c8bc06d6a8。其他容器本次身份/启动时间保持，worker memory.events无OOM。

前两次保护断言触发自动代码回退：第一次既有按需管理器正常停启 ingestion，第二次 Meilisearch 退出137并由自身重启策略恢复。后者当前RestartCount20，未查到对应内核OOM或systemd-oomd记录，不把原因写死为OOM。其内存768MiB、swap总限1536MiB、索引预算128Mb和单线程保持。本次未修改检索服务资源，不清空索引。

原worker镜像和Compose位于NAS恢复目录，数据库复用已验证恢复的238460564字节备份并再次核对SHA。回退只针对代码，不恢复旧数据库覆盖新策展。证据见tmp/index-status-http408-r1-20261111/deploy-attempt3.log及NAS同名release的deployment-result.json。

后续仍通过管理员原事件重新处理，并在正式读者页核验；运行修复不等于内容已公开。ingestion进程的同一辅助函数尚未切换新镜像，须先核对其实际基线与使用需求，不能把普通worker更新称为全角色更新。
