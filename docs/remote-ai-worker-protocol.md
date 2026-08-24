# 远程 AI Worker 拉取协议

本协议让 RTX 4070 等临时在线的 GPU 设备主动连接书库。NAS 不连接笔记本，也不依赖笔记本的固定公网 IP。任务事实、租约和派生结果均写入 PostgreSQL。

## 启用条件

服务端默认关闭协议。生产环境启用时需在未纳入版本控制的 `.env` 中设置：

```dotenv
CAPABILITY_REMOTE_WORKER_ENABLED=true
CAPABILITY_REMOTE_WORKER_SHARED_SECRET=<独立生成的至少 32 位随机值>
```

Worker 将密钥放在 `X-Library-Worker-Token` 请求头。不得把该请求头写入访问日志、错误日志或任务 payload。所有生产请求必须使用 HTTPS。

## 生命周期

1. Worker 每 30 秒以内调用 `POST /api/capability-worker/heartbeat/`。
2. Worker 调用 `POST /api/capability-worker/claim/` 主动领取任务。没有任务时返回 HTTP 204。
3. 长任务在租约到期前调用 `POST /api/capability-worker/demands/{id}/renew/`。
4. 成功时调用 `complete/`。服务端先校验并持久化专业结果，再结束租约。
5. 可重试失败调用 `release/`，并提供有限的退避秒数。

Heartbeat 必须声明 `executor_id`、capabilities、并发数，以及每项 AI capability 的 provider、model 和不可变 model revision。服务端记录声明时不接受密钥、Token 等任意 metadata 字段。

当前可远程完成的首个专业任务是 `claim_extraction`。领取响应包含原文 EvidenceSpan、固定 Prompt 版本和输出 schema。完成结果只有在写入 `DerivedClaim` 与 `ClaimEvidence` 后，CapabilityDemand 才会成为 completed。其他任务类型不会被该版本的拉取端点领取。

## 3.0.1 可运行客户端

仓库已提供 `api/common/remote_worker_client.py`。它不是协议示例，而是可直接运行的 pull worker。客户端先发送 heartbeat，再领取 Claim 任务，调用笔记本本地的 Ollama、vLLM 或 OpenAI-compatible endpoint，最后通过带租约的 completion API 写回候选。客户端不能访问 PostgreSQL，也不能直接写 Canonical Knowledge。

在 4070 笔记本的私有环境中设置以下变量。Token 与模型 API Key 不得写入仓库或命令历史。

```dotenv
STL_WORKER_SERVER_URL=https://books.winstonmo.com/api/capability-worker
STL_WORKER_TOKEN=<与服务端一致的独立 worker token>
STL_WORKER_EXECUTOR_ID=remote-gpu:4070-winston
STL_WORKER_PROVIDER=ollama
STL_WORKER_MODEL_URL=http://127.0.0.1:11434
STL_WORKER_MODEL=<本地模型名>
STL_WORKER_MODEL_REVISION=<不可变模型 revision>
STL_WORKER_GPU_NAME=RTX 4070
# 可选。空闲领取间隔下限为 10 秒，以免超过服务端专用限流
STL_WORKER_POLL_SECONDS=10
# 可选。长推理期间 heartbeat 与 lease 的续期间隔，默认 30 秒
STL_WORKER_KEEPALIVE_SECONDS=30
```

从 `api` 目录运行：

```powershell
..\.venv\Scripts\python.exe -m common.remote_worker_client
```

首次接入可使用 `--once`，它只 heartbeat 并最多处理一项需求。服务端 URL 在非本机环境必须使用 HTTPS。笔记本下线后 heartbeat 会过期，未领取任务回到 `waiting_for_capability`；已过期租约不能提交结果，人工上传和发布不受影响。

客户端空闲时最多每 30 秒发送一次 heartbeat，并按服务端返回值且不短于 10 秒领取任务。临时网络中断会进入有界退避，不会结束常驻进程。

## 租约和幂等

- 领取使用数据库行锁，并受 Worker concurrency 限制。
- NAS Celery 与远程 Worker 不能同时领取同一需求。
- 续租和完成都必须提供 executor id 与 lease token。
- 过期租约不能提交结果。
- 完成请求必须提供稳定的 `completion_id`。相同完成 ID 和相同结果可安全重放。不同结果会返回 409。
- release 后任务按当前可用 capability 回到 ready 或 waiting_for_capability。

Worker 下线后，heartbeat 到期和租约回收由 capability reconciliation 处理。没有合适执行器时，Claim 任务保持 `waiting_for_capability`，且 `publication_blocking=false`。

## 请求边界

所有端点只接收 JSON，并受 `CAPABILITY_REMOTE_WORKER_MAX_REQUEST_BYTES` 与专用 API rate limit 限制。馆藏原文响应受 `CAPABILITY_REMOTE_WORKER_MAX_JOB_TEXT_CHARS` 限制。Claim 结果最多包含 24 条候选。服务端不接受 PDF、模型文件或任意二进制上传。
