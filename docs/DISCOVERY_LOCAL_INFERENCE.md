# 3.0.8 本地检索模型

本文件描述已写出的准备与运行路径，实际验收记录另列于版本交付报告。准备文件成功不表示 N5105 已完成推理验收。

## 固定身份与部署目录

| 用途 | 模型 | 修订 |
| --- | --- | --- |
| 编码 | `intfloat/multilingual-e5-small` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| 重排 | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | `1427fd652930e4ba29e8149678df786c240d8825` |

两者使用发布者提供的通用 FP32 `onnx/model.onnx`，没有 AVX2/AVX512 专用量化，也无需安装 PyTorch 或在 NAS 导出。权重 SHA256 分别为 `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665` 与 `3e9a03ed1e966f7c5288dd4230e3d6a9bf5e3a170a06f1f4241c5bca12c6487c`。文件大小、tokenizer 哈希和配置 Git blob 身份在 `inference_service/model-lock.json`。README 保留发布者的许可与说明，权重与依赖不提交 Git。

使用 Python 3.12、FastAPI、ONNX Runtime CPU 1.22.1、tokenizers 0.21.2、NumPy 1.26.4、OpenCC。运行目录为 `${NAS_HOST_ROOT}/models/discovery/v308-fp32-v1`，与旧 Meilisearch 模型缓存并存。该目录在容器中只读；不得将两个模型的同维向量混入旧空间。

## 显式准备

联网准备只下载固定的官方发布文件，不调用推理 API，不读取馆藏。脚本保留中断文件并支持 Range 续传，所有文件与上游固定校验值一致后才写入完成清单。遇到同名但错误的现有完整文件会停止，不覆盖原文件。

```powershell
.venv/Scripts/python.exe scripts/prepare_discovery_models.py --destination 'F:\agent skills\stl-release-artifacts\v308-models\v308-fp32-v1'
.venv/Scripts/python.exe scripts/prepare_discovery_runtime.py --destination 'F:\agent skills\stl-release-artifacts\v308-runtime'
```

模型准备约 976 MB；保留原缓存和重试空间。第二条命令只下载 Linux x86_64 / Python 3.12 CPU wheel，并生成全部实际依赖的版本/文件 SHA256 清单，既不安装也不运行模型。模型和运行库准备完成后可分别使用 `--offline` 核对已有文件，模型脚本可用 `--archive` 创建一个不存在的新归档。

安装时把完整模型版本目录复制到 NAS 新目录，核对 `manifest.json` 及 SHA256，再挂载新服务。容器使用 UID/GID 10001，仅在这个新版本目录赋予文件读取及目录穿越权限，例如文件 0644、目录 0755；不修改馆藏、旧缓存或私有资料权限。不要替换旧模型目录、旧镜像或活动索引。离线构建将准确提交中的 `inference_service` 源码放入临时构建目录，再加入 runtime 准备目录里的 `wheels/` 和 `requirements-linux.lock`，使用 `Dockerfile.offline` 与 `docker build --network=none`。普通 `Dockerfile` 提供联网安装路径；两者都固定关键推理版本。发布记录须记实际使用路径及镜像 ID。

## 运行与 HTTP 契约

在现有 Compose 文件之后增加 `-f compose.discovery.yaml`。推理服务仅加入 `discovery_internal` 内部网络，不开放宿主端口、不挂 Docker socket、不需要 GPU。API 与任务容器保留原 `backend` 及本地开发 `default` 网络。新增 `discovery-query-worker`、`discovery-index-worker` 分别只消费 `discovery_query`、`discovery_index`，并发与预取均为 1；普通 worker 只消费 `celery`，OCR/上传仍沿原 ingestion 队列。`.env` 的数据库/Redis 配置沿用原项目。

服务只运行一个进程，最多一个 ONNX session 和对应 tokenizer 常驻；切换编码/重排时先释放前一组，再加载下一组。起点为 2 CPU 线程、batch=1、1600 MiB 内存上限、1800 MiB 内存与 swap 合计上限。最多接纳 3 个请求，等待计算锁超过 3 秒返回忙碌，单请求模型执行总预算 120 秒，ORT RunOptions 在到时后终止计算。Celery 长任务应对忙碌/失败保留可重试状态；不把推理降级当作索引完成。

| 路径 | 请求 | 返回 |
| --- | --- | --- |
| `GET /health` | 无 | 清单状态、模型/修订/artifact、已加载及实际完成推理的独立标记 |
| `POST /normalize` | `texts[]` | 仅检索用规范文字；不覆盖展示原文 |
| `POST /chunk` | `text,title,max_tokens=320,overlap_tokens=40` | 全部小块、原文 `start/end` 字符偏移、`text`、`normalized_text`、`embedding_text`、含前缀/标题的真实 token 数 |
| `POST /embed` | `texts[],kind=query|passage,expected_artifact?` | 384 维向量、token 数、固定身份；超长返回 422，绝不静默截尾 |
| `POST /rerank` | `query,documents[],top_n,expected_artifact?` | 候选原序号与相关性 logits；窗口数及截断标記，不返回真假/立场或正确率 |

E5 的两种前缀均按模型卡使用。正文与查询都经过固定版本的 OpenCC 繁简对齐、NFKC 和英文行末断词修复，然后 attention mask 均值池化及 L2 归一化。分块以原始文字字符位置保存切片；根据规范化之后的实际 tokenizer 数量控制预算，重叠处不伪造连续新文字。

重排使用真实问题—候选文本配对。查询最多 128 个 tokenizer token，长候选最多 3 个有界窗口；超出时取首、中、尾窗口，并返回 `query_truncated`/`truncated`，不声称全文已重排。logits 只用于排序，不当作概率。客户端对返回向量长度、有限值、单位范数、原文切片完整性及候选索引做验证。

`/health` 的 `manifest_ready=true` 只代表固定文件已验证。只有本进程编码和重排均真实完成后才有 `ready=true`；Compose 健康探针不自动进行模型推理。开发完成后的集中验收须在实际 N5105 上完成两种调用，记录耗时、内存、指令集兼容与失效处理，不能用文件清单或开发电脑结果替代。

## 缺失、升级和回退

模型缺失、清单不一致、服务过载或执行超时会返回明确代码。查询保留已得到的关键词/知识/策展结果并标出向量或重排降级；索引任务保留失败和重试，不能将排队写成完成。运行时环境为离线且无外网路由，不自动寻找替代模型或付费服务。

更换模型、tokenizer、池化、规范化或后端会改变 artifact 身份；先构建隔离 generation，文档和查询身份相符后才能激活。更换头像等展示字段不属于正文重编码触发条件。回退时切回保留的应用镜像与原索引 generation，停止新 discovery workers 和推理服务；保留新版模型、数据库新增 schema、人工资料与旧有效索引，不执行破坏性回滚。

官方依据：[E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-small)、[Cross-Encoder 模型卡](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)、[ONNX Runtime CPU 构建说明](https://onnxruntime.ai/docs/build/inferencing.html)。这些资料不能证明本馆精度或 N5105 吞吐，实际执行结果单独记录。

## 2026-09-22 实际 N5105 验证

模型准备与 NAS 复核均退出 0，共 12 文件、975,820,242 字节；新版本目录在上传前核实不存在，校验后原子就位，旧模型未改。模型归档 SHA256 为 `468a47b0aa354e4d7079e7ac7f9553c5da950aece8d23092b9e4a036ec27b7df`。Linux Python 3.12 的 35 个离线 wheel 全部按哈希安装；运行库清单 SHA256 为 `11d2bdd31b72051233a595c21be7bde1740eccd06d82ee2246460eb043d15259`，依赖锁文件 SHA256 为 `523eeb3ffcfdeefe4ebf22dfc1c764d207d13bda3eff7bade383177b6ebd28ec`。

在无 AVX/AVX2 的 N5105 上，以独立 internal 网络、无宿主端口、模型只读挂载实际运行。首轮功能通过，但双 tokenizer 常驻令 swap 达到 200 MiB 上限，随后修复生命周期，仅复验相关推理流程。修复后的 10 次调用及断言全部通过，退出 0、OOM/oom_kill 均为 0、容器重启 0，容器已停止。

| 实际检查 | 结果 |
| --- | --- |
| E5 四段短文本 | 冷加载 3.983 秒，热调用 0.116 秒；全部 384 维、L2 归一；繁简同义输入一致 |
| tokenizer 原文定位 | 混合中英、繁简、断词换行、非 BMP 字符共 3,019 字，5 个原位切片完整覆盖，最大 318 token |
| 拒绝与身份保护 | 超长编码返回 422，错误 artifact 返回 409 |
| 20 个合成候选重排 | 换载冷调用 8.595 秒，热调用 1.676 秒；相关样本为前两项，结果排列和热调用一致 |
| 再切回 E5 | 4.150 秒，输出一致；health 显示两模型均完成实际推理 |
| 内存 | 启动后 RSS 76.4 MiB；调用后 RSS 约 836–850 MiB，采样 swap 最大 17.9 MiB；含文件缓存的 cgroup 峰值仍触 1,600 MiB 上限，发生回收，无 OOM |

这些是有界合成功能样本，不代表馆藏相关性评测、长文最大负荷、并发吞吐或公网验收。原始证据在忽略目录 `output/verification/v308/inference-r2/`，首轮证据单独保留在 `inference/`。后续真实馆藏三通道联动由隔离恢复环境验收，不能以本节替代。

最终本地推理候选镜像为 `sha256:62c11c6a0d5ba5a563472370268141b561965ad44612571b8d2ff30492e29bd3`，标签 `stl-v308-inference-candidate:20260922-d11b3430bf`。其来源明确标为未提交工作区，冻结源码集合 SHA256 为 `d11b3430bfacb276a0626de0b3015530e18d88c2a4bcf7eba9da49a135186818`，其中 `runtime.py` SHA256 为 `fdab33487495910fb88dcf6bac7f495760f9aec844baa0e1a8ae6293399f6450`。正式提交后须逐文件核对再记录最终提交与镜像映射；此处不宣称该候选由尚不存在的提交构建，也不宣称已上线。
