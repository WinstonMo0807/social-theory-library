# NEW-R04 研究会话总览

2026-10-23，前置7dc1446。直接从唯一final-r2 PDF读取184页，图像位于tmp/pdfs/stl4-final-r04-20261023/page-184.png。纸白页、白色内容层、细分隔、研究行和移动最近阅读/研究/下一步延续终稿；没有读取替代设计或填入示例研究。

原ResearchProjectViewSet加入DirectoryActions，GET /reading/research-projects/directory/。只查当前User，必需X-Reader-Owner，沿原PrivateAccountResponses/认证。分页20条，当前/归档/全部筛选。ResearchProject本身没有执行status，现用本人项目的ResearchTurn判断正在处理、排队及最后完成/部分/失败/取消；没有轮次则已保存。活动排序取项目更新时间与轮次更新时间较新者。归档期间有任务则明确归档及处理中。count与结果长度不一致时409，空页404，可回第一页。

响应仅项目摘要，不批量回传全部私人加密笔记/材料/答案。最近阅读沿原reader_center查询及notebook公开书目投影，只返回本人当前可读文件的题名、页数和原阅读入口。没有第二套进度或研究库。

原/account/research接生成契约和usePersistentWorkspace，绑定owner与会话epoch；错误时隐藏旧数据，离开/换账号中止请求。当前页有在途轮次才5秒有界轮询，重新聚焦30秒后刷新。桌面摘要列表、分页及真实空态；手机先显示最近阅读/研究，可展开完整分页，回到最近时重置当前范围和第一页。样式使用既有日夜主题变量。

静态ea404a退出0：AST33、38次SQLite/PostgreSQL SQL编译（禁止数据库连接），accounts/reading迁移声明比较一致，274契约/CSS解析；schema零错误、10条既有catalog警告。TypeScript noEmit及目标ESLint636d4f退出0。没有测试、浏览器、实际API/业务、迁移、构建或生产操作。

索引NEW-R04记部分接入，96源码/46部分/67待实施。没有新迁移，reading0022/23/24仍未执行。运行状态轮询、并发删除、多账户隔离、移动交互与精确视觉仍待统一验收，全站未完成。
