# 书库策展对话接续 OCR

用户要求由“书库策展”对话启动本机 OCR。本次优化对话已关闭本机服务，并安全暂停 NAS 的 OCR 工作量。此前已完成的页面、原件和进度均保留。先读同目录 `NAS_RESOURCE_OPTIMIZATION_20261108.md` 和项目 `CURRENT_PROGRESS.md` 顶部，再回读真实后台。

交接实测：58/58 份原件哈希匹配，后台含历史记录的61条上传全部 ready。按58份文件统计，48条 OCR 暂停、8条成功、2份文件无须 OCR；暂停任务剩余14590页，都有显式目标页。《经济与社会》1800页已完成文字解析，NAS最终登记7页待识别；以后台清单为准。计数会随后续实际操作变化，接续先运行 status。

## 已准备的接口

- 本机入口 `http://192.168.5.3:18091`，NAS `192.168.5.6` 可访问；只允许本机/NAS 地址，不信任代理头。IP 改变时须先核对，不盲目改正式全局 OCR 配置。
- 复用现有 RapidOCR 服务、模型和虚拟环境，2 个 CPU 线程，不重新下载模型。
- `scripts/start_curation_ocr.ps1` 只启动本地服务，不自动恢复任务。`-CheckOnly` 仅检查所需文件存在。
- `scripts/curation_ocr_handoff.py status` 只读真实任务；`resume` 先检查模型实际就绪、管理员权限、暂停版本和测试白名单，再经现有管理服务恢复。本轮交接保存于 NAS `/data/backups/nas-resource-20261108/curation-handoff.json`（宿主前缀 `/volume2/library/stl4/storage`）。
- 仅本批显式 job/upload 白名单临时转到电脑；其他书和显式绑定保持原规则。电脑失联时等待重试，不自动让 NAS 接手批量 OCR。

## 策展对话中执行

在 `F:\agent skills\书库开发3` 下使用 Codex 当前 PowerShell 7 终端（此终端已验证 -CheckOnly 成功；不调用执行策略不同的旧 powershell.exe）：

```powershell
.venv/Scripts/python.exe scripts/curation_ocr_handoff.py status
& ./scripts/start_curation_ocr.ps1 -CheckOnly
& ./scripts/start_curation_ocr.ps1
# 确认本地 /health 和 /ready?deep=true 正常后再恢复。
.venv/Scripts/python.exe scripts/curation_ocr_handoff.py resume
```

`resume` 本身也会从 NAS 验证真实就绪。如果暂停版本已变化、来源被撤回、IP/模型/作用范围改变，停止依赖操作并核实；不要绕过保护。脚本成功后回读 job 状态和页级进度，不能只看命令启动。不要重复执行已成功的 resume；若出现部分保留任务，按返回原因使用原管理服务逐项处理。

58 份原件均已按 SHA256 匹配正式存储，禁止重新批量上传。61 条 UploadItem 包含历史/重复记录，不据此删除或合并。已有可用文字层直接利用，按原流程仅 OCR 有证据需要的页；不得强制 58 本全书重跑，也不得覆盖原件、人工修改、笔记和既有可用文字。策展工作区以前用于阅读的本地 OCR 不自动视作网站已完成。

网站继续使用原完成状态和正常页面数据。真实结果通过现有管道写入后才显示 OCR 已完成；不加“本机 OCR”新功能，不直接改数据库完成标志。

任务结束或暂停时，先使用网站既有暂停管理流程并等待在途页保存，然后关闭本轮拥有的本地服务进程；不要直接杀正在识别的页，不退出其他对话的 Python 进程。

NAS 资源管理已部署，不恢复闲置旧推理/预览，不运行完整 compose up，不在 NAS 构建镜像。策展、STL 界面工作继续使用同一正式 API 和数据库。
