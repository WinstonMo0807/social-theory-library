# 2026-11-07 策展预览修复

管理员编目文件检查器生成了 `/api/api/distribution/admin/assets/.../preview/`，因此草稿文件返回404。修正工作台后备地址，由客户端统一添加 `/api`。知识对象发布检查的内嵌真实预览被全局 `X-Frame-Options: DENY` 阻挡；仅 `/admin/preview/` 使用 `SAMEORIGIN`，其他页面继续 `DENY`。

两项定向测试通过：管理员可按工作台实际地址读取范围文件；访客需登录、普通读者不能读取管理员预览及未发布文件。公开访问断言同步当前访客登录规则。NGINX候选配置检查通过，运行响应头分别核对预览、首页及管理编辑页。

正式API为 `4.0.0-20261107-curation-preview-r1`，镜像 `7fea47bfb21b4fff226bdd3edcc56949d6ef6d81e8b20ead43cadcb9d8e91514`，继承当前avatar-r2及日期修复。仅API重建，其他24容器身份与启动时间不变；edge平滑reload。Web仍avatar-r2，Worker/Beat仍upload-r5。正式Compose最后追加 `/volume2/library/stl-releases/20261107-curation-preview-r1/api-preview-fix.compose.json`。

恢复点位于同目录的 `api-recovery` 与 `edge-recovery-r2`，保留原镜像、配置及23,369,870字节数据库备份，目录可读性验证通过。没有数据库迁移。回退只恢复对应服务与配置，不用旧数据库覆盖后续策展。第一轮边缘检查因不存在路径未产生预期响应头而自动回退，第二轮改用实际路径核验通过，原日志保留。

浏览器已显示草稿PDF的blob阅读器；组织社会学子学科保存版本实际渲染，发布前检查无阻断，发布确认成功。公开 `/subdisciplines/sociology-of-organizations` 已显示说明与三个关键问题。作品、学者及理论关联继续策展，尚未以该基础对象发布代替整体任务完成。

浏览器证据位于策展工作区 `编目修复-20261107/reader-preview-fixed.jpg` 与 `subdiscipline-published.jpg`。运行与部署脚本及日志留在策展工作区，不提交馆藏数据、凭据或运行产物。

实际文章编排另发现 `/admin/recommendations/issues/<UUID>/preview` 使用独立路由，仍被 DENY 阻止内嵌。补充同源预览路径后，NGINX 配置检查及四条响应头检查通过：首页与文章编辑器为 DENY，两类预览为 SAMEORIGIN。仅平滑 reload，edge 容器与启动时间未变。恢复点 `issue-preview-recovery` 保存修改前配置，失败会自动恢复。浏览器实际显示 C001 的标题、正文、winston 署名及来源链接，证据 `预览修复-20261107/issue-preview-fixed.jpg`；当前文章仍因关联作品尚未公开而阻断发布，未绕过检查。
