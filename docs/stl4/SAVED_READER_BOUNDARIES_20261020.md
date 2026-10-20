# 收藏、书单与私人分页边界（2026-10-20）

接续 final-r2 PDF25–31 中真实作品操作，沿原 SavedItem/ReadingList/ReadingProgress 和 Reader 文件权限实现，不另建私人收藏存储。

- 收藏接受当前主版本公开但尚无可读文件的书目；撤回后保留本人收藏，题名/书目和阅读进度展示遮蔽。书单亦重验公开主版本，名称来自正式快照。
- 阅读文件必须同时满足已激活公开修订、NORMALIZED/READY/VALID、非空文件、snapshot document.asset_id 与文件一致及当前用户访问资格。角色 admin/editor/reviewer 沿现有文件权限，单独 Django is_staff 不授予私人文件资格。无效进度继续保存，不作为可读入口。
- 同作品收藏 get_or_create 和加入书单沿所有者事务锁；响应未知时前端先查回收藏状态，再恢复原操作，不重复翻转。书单明确选择目标，重复加入幂等。
- 结果页按50个作品分批读取收藏。共享 readAllPages 必须传入预期账户，每页发送 X-Reader-Owner，不自动刷新或重放401。后端 OwnedModelViewSet/PrivateResponses 逐请求验证，防止分页中间 cookie 换成另一账户。所有现有调用者同步传入身份。

新增3个后端测试函数（16个参数案例）和4个前端合成分页案例，仅编写未运行；原收藏6函数/9案例继续保留。静态结果以 VALIDATION 为准。实际权限、并发、Cookie切换及真空馆藏等待统一验收；未改账户、生产数据或应用迁移。

继承依赖单独审查并纳入：public-catalog.ts 保留 Reader 目录/文档修订类型；server-request.ts 关闭运行时假数据回填，API故障沿现有错误状态呈现，不用演示馆藏掩盖故障。其他历史改动未混入。
