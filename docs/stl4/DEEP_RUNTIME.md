# 隔离深度推理运行时

## 2026-10-26 继承制品与真实接线

DEEP-01修正原EG2请求误走基础E5 `/embed` 的调用链。新增同一服务 `/deep-embed`，使用旧实验的SearchQuery/题名模板和已导出的768维mean/L2输出；拒绝截断，模型和代次单独核对。EG2/BGE/ConvMemory仍共享一个串行CPU模型槽。新增artifact_identity供制备与运行共用，两个Dockerfile包含该文件。

DEEP-02复用DiscoveryDocument和原索引作业维护独立EG2投影；写入同一document ID/source revision，按基础generation隔离，原文资格读前/推理后复核。原来源撤回清理同代次投影；模型失败保留基础结果并在ProcessingJob.stats登记deep_index_pending，可用`python manage.py discovery_deep_index`按输入hash补写。`--prepare-only`只准备索引设置，不执行推理。索引名称绑定深度UUID与完整制品hash，不能用命令覆盖基础索引。

脚本scripts/prepare_stl4_deep_models.py只封装10月14日已有EG2 int8、BGE int8、ConvMemory-v2 FP32导出，核对原revision和全部制品hash，不下载/重新导出/运行测评。bundle已制备并传到隔离预览storage/models/deep-bundle-r1，generation为a8b6434b-c073-4874-9192-23129fae478a。API r5和Discovery r2镜像已构建，尚未替换当前运行r3/r1；待视觉修正后合并更新预览。不得把制品核对称为模型运行通过。

db580a完成10文件AST，无测试、模型调用或索引执行；契约用例只编写。后续实际推理/超时/内存和当前馆藏索引仍B待验收。用户现转入真实页面视觉差异修正；不重开模型质量评测。

当前实现只服务于 STL 4.0 Discovery 的可选深度阶段，不替代首屏检索，也不切换生产索引。`DEEP_INFERENCE_ENABLED` 默认关闭；启用时必须提供只读 bundle、manifest、lock 和 generation。启动阶段逐文件校验 repo/revision、bytes、SHA-256、模型文件、tokenizer、artifact_id 与 pipeline，任何不一致都降级为即时结果保留。

BGE reranker 与 ConvMemory 上下文层共用一个 CPU ONNX session 槽，batch size 与线程数均为1，tokenizer 使用 longest-first 截断。BGE 只返回标量候选分数；ConvMemory 只为已回读的原文窗口附加 `context_score`、`context_rank` 和截断信息，保持调用方候选顺序，不生成或缓存替代原文。

本轮未下载、加载或运行模型，未执行第三步检索质量评测。正式环境需要在统一验收阶段核对真实 bundle、Worker 超时/取消、资源占用和来源回读；本文件不构成生产就绪证明。
