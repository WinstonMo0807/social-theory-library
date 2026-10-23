# 2026-10-24 依赖安全升级实施记录

依据 `DEPENDENCY_SECURITY_AUDIT_20261024.md` 和用户“按照排查报告进行升级，且同时继续开发”的授权。本次完成源码依赖、开发安装和离线构建输入更新，未部署生产，未运行测试、构建、浏览器检查、检索评测或数据库迁移。

## 已落地的版本

| 范围 | 更新 |
|---|---|
| Web | Next / eslint-config-next 16.4.1，Vite 8.2.4，sharp 0.35.5；npm 锁文件和本地安装同步 |
| Web 间接依赖 | image-size 2.0.3，source-map-js 1.2.2，fast-uri 3.1.8，undici 7.29.1；brace-expansion 按原主版本升级到 1.1.21 / 2.1.7 / 5.0.12；旧 esbuild 链升级到 0.25.12 |
| Node | Web Dockerfile 固定 24.22.1；项目独立工具安装同版本，官方 ZIP SHA256 已核对；没有替换 Codex 自带运行时 |
| API | Django 5.2.18，DRF 3.18.3，cryptography 50.0.2，Pillow 13.0.0，pypdf 6.21.2，PyJWT 2.15.1，sqlparse 0.6.0，certifi 2026.10.23，urllib3 2.8.0，pytest 9.1.1，pip 26.2.2 |
| OCR / 推理服务 | FastAPI 0.156.4，Starlette 1.9.0，Uvicorn 0.54.0；OCR python-multipart 0.0.32、Pillow 13；证书和 HTTP 依赖下限同步；保留原 Paddle / ONNX / tokenizer 和模型方案 |
| 反向代理 | compose.yaml / compose.public.yaml 的 Nginx 默认镜像更新到 1.30.6-alpine |

保留 Vinext 0.0.50 和 React 19.2.8，没有变更技术栈、检索算法或账户数据。没有 PHP 执行链的证据，浏览器原生上传进度保留。解除 DRF、cryptography、Pillow 的旧版本上限后，以类型和契约检查初步检查兼容性；真实业务兼容性须在统一验收确认。

## 离线输入与防止旧包回流

- 新 Web Linux x64/glibc 运行归档位于 `offline/security-20261024/web-runtime-linux-x64.tar.gz`，原旧归档保留。新归档按当前 npm 锁文件安装，禁用第三方安装钩子，仅执行已有 Vinext 文件补丁。193 个本地运行包、194 个 Linux 运行包的版本与锁文件匹配。
- Web 锁文件 SHA256 为 `7b64c876bfa36537fb8b030f883a3850b78b95fd82ea6f5fd7930d0e417b2e04`；归档 SHA256 为 `d40410679212ce63840847926fa30ee229f8a37f989c80e869fdd0287d04a2ba`。归档内锁指纹和 `verify-runtime-dependencies.mjs` 阻止离线构建继续使用不符版本的 Node / node_modules。该检查不证明应用功能正常。
- Python API 3.12、OCR 3.11、推理 3.12 的 Linux wheels 分别位于同目录 `api-runtime` / `ocr-runtime` / `inference-runtime`。各有 `wheels/`、逐包 SHA256 的 `requirements-linux.lock` 和 `runtime-manifest.json`。最终分别 76 / 84 / 38 个包。
- 复用 `scripts/prepare_discovery_runtime.py`，新增 requirements/Python 版本参数、可选依赖递归核对及 Linux 平台标记核对。实际补齐了 Windows 下载时漏掉的 OCR uvloop。只读取顶层 wheel 元数据，避免将 setuptools 内部 vendored 元数据认作第二个包。
- offline API/OCR Dockerfile 改为新目录和带哈希的精确版本安装；推理离线 Dockerfile沿已有锁文件流程并加入 pip 依赖一致性检查。所有服务准备包包含 pip 26.2.2。
- 新依赖归档、wheels、安装清单及下载运行物均已被 Git 忽略，没有提交二进制包或私人数据。第一次跨平台下载目录 api-wheels / ocr-wheels / inference-wheels 仍保留，但 Dockerfile 不再使用它们。

后续准备可复用以下命令，目标 Web 归档必须选新路径，脚本拒绝覆盖现有归档。Python 目标若有重复版本会直接停止，不能以旧混合目录继续发布。

```powershell
.\.venv\Scripts\python.exe scripts/prepare_discovery_runtime.py --destination offline/security-20261024/api-runtime --requirements api/requirements.txt
.\.venv\Scripts\python.exe scripts/prepare_discovery_runtime.py --destination offline/security-20261024/ocr-runtime --requirements ocr_service/requirements.txt --python-version 3.11
.\.venv\Scripts\python.exe scripts/prepare_discovery_runtime.py --destination offline/security-20261024/inference-runtime
# 已准备后的纯元数据检查可在对应命令尾部加 --offline。
```

Web 准备脚本 `scripts/prepare_web_runtime.py` 接受 `--node`、`--npm-cli` 和 `--destination`。本轮使用的项目 Node 位于 `tmp/security-runtime-20261024/node-v24.22.1-win-x64/`，ZIP SHA256 为 `d2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5`。

## 已做的静态核对

- npm 公告重新查询 618 个包名，命中 0。Python 本地及固定服务版本 87 项查询，命中 0。新 Linux wheels 192 项版本查询，命中 0。仅上传公共包名/版本，无项目源码或用户资料。
- 本地 `pip check` 无依赖冲突；完整 TypeScript `--noEmit` 退出 0；新运行包检查脚本语法与目标 ESLint 退出 0；两个 Python 准备脚本 AST 解析通过。
- 升级后禁止数据库连接生成 OpenAPI，0 错误、10 条原有警告，333 路径；与升级前契约完全相同。
- 关键输出记录：安装 e3ad99 / d084ed；类型检查 0344bb；Web 归档 0f845c；公告查询 ccc497 / eef516；Linux 依赖核对 1a3d41 / a118a4 / 16e978；AST/契约 fccea8；脚本静态检查 375513。目标脚本首次命令使用了错误工作目录，未执行成功，修正后 375513 退出 0。OCR 首轮识别 setuptools 元数据失败，修正顶层元数据读取后完成，不能将失败轮写成通过。

## 尚未完成的部署与验收边界

数据库零命中不等于不存在漏洞；本轮并未获得生产容器内的完整包表、系统包表、镜像摘要或 NAS 其他应用清单。未核实应用在新版 DRF/Pillow/cryptography/FastAPI 上的完整运行行为。

正式验收时需构建新镜像，核对实际 Node / Python / Nginx 及系统包补丁，执行原有重要业务和权限用例、OCR/推理实际调用，再按授权发布。`offline/web.Dockerfile` 仍需要由新版依赖构建的 `web/dist`；旧 BASE_IMAGE 的 Node 不达基线会被阻止。原历史冻结版发布打包脚本不能直接当本轮发布入口。推理 bundle 还需沿原发布步骤装入当前源码/Dockerfile。未生成新应用 dist 或发布整包。

安全升级不能记作全站完成。当前功能继续接 M09 索引结果与失败恢复，333 契约和 96 源码接入 / 110 部分 / 3 排除项待实施的视图状态保持，实际运行与逐图验收另记。

## 最终补查：独立 Paddle wheel 的间接依赖

在功能检查点1f66906后，补读原本单独以 `--no-deps` 安装的 PaddlePaddle 3.3.1 wheel。该原包本次 OSV 查询0命中，但其依赖没有完整出现在OCR准备包：缺少 httpx、protobuf、opt_einsum、networkx、safetensors。旧镜像可能已带其中部分包，不能据此认定新镜像也完整，或把旧包留作升级结果。

已按该 wheel 的实际 METADATA 补入 OCR requirements，保留它精确要求的 opt_einsum 3.3.0；准备包采用 httpx 0.28.1、protobuf 7.36.2、networkx 3.6.1、safetensors 0.8.0及间接httpcore 1.0.9。OCR包数由78变为84，三服务198项版本重新查询0命中，独立Paddle原包另1项查询0命中。Docker安装后加入依赖一致性门禁，未运行镜像中的导入/计算指令，Paddle/protobuf实际运行兼容性继续列入统一验收。

ab3657为Paddle包元数据/公告读取，42a9e8记录缺项；14ef2f→b4b0e2补齐下载成功，7e5163记录最终198项0命中。这些步骤只读取元数据、下载包和生成哈希清单，没有执行OCR模型。
