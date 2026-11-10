# 独立候选预览

**登录说明：这里是合成测试账号库，正式网站账号密码无法用于此入口。** 当前库只包含4个合成测试账号。独立Edge与Codex内置浏览器不共享登录状态；2026-11-10已在用户当前内置浏览器标签完成测试账号登录，实际进入/admin的“今日工作”。无需为预览重置正式账号密码，不能把生产账号或密码库复制进测试环境。

已打开独立Edge预览窗口，两个标签分别为管理台与读者中心，使用合成测试账号登录；与用户日常浏览器会话隔离。实际读回标题为“今日工作”和“读者中心 仅本人可见”。

当前本机入口：

- 管理台：http://127.0.0.1:18110/admin
- 读者中心：http://127.0.0.1:18110/account
- 隔离API：http://127.0.0.1:18111/api/health/

18110/18111为本轮专用本机入口，不是公网或Knowledge Core内网Demo端口。API由scripts/local_cataloging_e2e_api.py以--offline启动，存储为新建临时SQLite及合成PDF，socket出站阻断、内存broker、无worker、不向外发送邮件。专用启动器将Web的INTERNAL_API_URL和/api开发代理明确指向127.0.0.1:18111；ALLOW_DEMO_FALLBACK=false。没有使用生产数据库或真实账号资料。

前端源码中的正式transport与Vite配置已恢复公网原版。仅此启动器在开发进程内兼容本机Workers的redirect限制；生产构建不会包含该转换。

运行中的进程与测试会话文件均在本地output/public-visual-20261110，不提交或外传会话。浏览器使用专用合成测试账号，报告不写凭据。测试数据包含长标题、缺封面、空目录、失败任务与可编辑测试草稿，不能当成正式学术内容。

若本机预览停止，先核对端口；在工作区根目录运行 `powershell -NoProfile -File scripts/start-center-layout-preview.ps1`。它复用已记录的临时测试库，在独立隐藏后台进程启动API与Web，启动命令退出后进程继续运行。记录在output/public-visual-20261110/runtime/background-processes.json，日志为api-background与web-background的out/err文件。端口占用时拒绝继续，不终止其他服务；电脑重启后需重新执行，不安装开机项。

API恢复使用 `--offline --resume-ready-file output/public-visual-20261110/audit/FIXTURE_RUNTIME.json`，不迁移、不重新填充、不重置测试账号。只允许TEMP下既有合成SQLite和匹配本机URL；数据不存在时明确报错，不暗中新建替代。首次创建隔离库才使用原有--ready-file流程。前端沿用node scripts/start_center_layout_preview.mjs；绑定127.0.0.1:18110、strictPort，不读取生产.env。

2026-11-10实际恢复后，启动脚本已退出，18110/18111仍监听；health/account/admin均200，内置浏览器显示已登录读者中心和原有测试记录。实际UI核对不等同全部业务重验。

本轮未推送、未部署、未改DNS或隧道。切换前应再次核对公网是否有同期更新，在此候选基础上形成准确发布包与回退清单，再等待用户最终授权；不能把本地构建或此入口视为生产上线。
