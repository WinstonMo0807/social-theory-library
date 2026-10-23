# M30质量评审接续

## 2026-10-23 M30实际图像与旧入口核对

前置a92c85c。已实际读取唯一PDF170–172，确认M30实际是检索与智能质量评审，不能将索引路由/admin/feedback机械解释为普通读者反馈。原读者反馈完整组件在/admin/support/feedback，保持独立。

已读取SearchEvaluationSet/Query/Judgment/Run/Result模型、search_evaluation_views的集合/问题/运行读写入口及主要序列化器，services/search_evaluation.py开头至build_evaluation_plan，已有记录与人工等级可复用；旧执行服务调用semantic_search，尚不能证明对应当前Discovery首选方案，禁止机械接入或自动执行。尚未查看后续执行/结果落点、首选Discovery实际对照及原文权限完整链路，未新增M30代码，也未计完成。进一步回查DECISIONS D010，明确本轮不新建第三步评测页面；保留本次源码定位，不启动新界面或运行任何评测，转入M31/M32。

M29补查发现同一草稿发布后原版本号不变，会让另一个编辑者持续面对过期状态；已将site_content版本改为不透明的修订ID与状态组合，并同步前端并发提示，已静态收口，随本轮后续检查点保存。源码a92c85c仍为此前检查点；298契约、96/75/38不变。全部测试、浏览器、迁移和生产仍未执行。
