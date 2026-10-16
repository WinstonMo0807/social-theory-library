# 隔离深度推理运行时

当前实现只服务于 STL 4.0 Discovery 的可选深度阶段，不替代首屏检索，也不切换生产索引。`DEEP_INFERENCE_ENABLED` 默认关闭；启用时必须提供只读 bundle、manifest、lock 和 generation。启动阶段逐文件校验 repo/revision、bytes、SHA-256、模型文件、tokenizer、artifact_id 与 pipeline，任何不一致都降级为即时结果保留。

BGE reranker 与 ConvMemory 上下文层共用一个 CPU ONNX session 槽，batch size 与线程数均为1，tokenizer 使用 longest-first 截断。BGE 只返回标量候选分数；ConvMemory 只为已回读的原文窗口附加 `context_score`、`context_rank` 和截断信息，保持调用方候选顺序，不生成或缓存替代原文。

本轮未下载、加载或运行模型，未执行第三步检索质量评测。正式环境需要在统一验收阶段核对真实 bundle、Worker 超时/取消、资源占用和来源回读；本文件不构成生产就绪证明。
