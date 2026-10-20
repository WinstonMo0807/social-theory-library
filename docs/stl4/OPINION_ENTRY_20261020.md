# 观点检索入口与本人历史（2026-10-20）

仅依据实际读取的 final-r2 PDF28–29 实施。`/explore/opinions` 是问题与范围入口，提交到原 `/explore/evidence` Discovery 会话。全部文献、特定作品/学者/主题、手机范围弹层、空输入、选项读取失败与真实历史均已接入源码，正式逐图验收待执行。

范围选项来自当前公开 catalog search，学者使用 Person ID；不使用后台或静态假选项。更换一种范围保留其他已有限制，旧 canonical 参数和年份/语言等过滤继续保留。选择全部文献明确清除作品/学者/主题限制。范围用于原文通道，知识与策展按问题提供辅助线索，不宣称三通道都受同一过滤约束。

GET `/reading/search-records/` 复用加密 ReaderSearchRecord，仅本人可读，owner_id 必填，X-Reader-Owner 同步校验，private/no-store，page_size 最大20。读取不创建记录或开启保留；搜索历史默认关闭，停写不删除已有记录。只在本人已启用保留且真实创建检索会话后沿原服务保存。

前端通过原 usePersistentWorkspace 可选读取函数接入，401 不刷新重放，返回 owner_id 不符则丢弃。近期显示3条，完整列表按20条分页；历史链接恢复当时问题与允许的过滤字段。账户变化清除旧页状态。

4个后端测试函数（6个参数案例）和5个浏览器场景仅编写，覆盖本人/管理员隔离、默认停写、加密、分页与原过滤、多范围保留、移动取消和401/错账户。没有运行正式测试或浏览器；静态结果见 VALIDATION 最新项。没有表/迁移/生产或模型操作。

恢复文件：opinion-search-entry.tsx/module.css、opinion-entry.client.ts、opinions/page.tsx、use-persistent-workspace.ts、reading/search_record_views.py/urls.py，连同 OpenAPI 与生成类型共同保存。
