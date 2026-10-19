# 共享引用、选材与导出

2026-10-19。仅依据实际渲染并读取的最终 `social-theory-library-visual-atlas-20261015-final-r2.pdf` 第20–22页（R34-main/sub01/states）。源码接入，统一运行和视觉验收待核实。

## 实现与调用

- 桌面保留背景右侧浮层、移动底部抽屉，所选原文、真实来源、研究目标、200字备注、格式选择、操作结果与本机选材共用一个组件。焦点与背景隔离复用原生 Dialog。
- `SharedCitationButton` 位于 `web/components/shared-citation-overlay.tsx`。props为 `editionId?: string`、`reference?: EvidenceReference`、`selectedText?: string`、`className?: string`、`children?: ReactNode`。`SharedCitationOverlay` 同样输入另加 `open`、`onClose`。只有出版版本时提供书目引用/导出，明确无页码；带真实原文身份后开放选材。
- 已接 Reader 选文菜单/当前页、作品引用面板、策划 evidence 块的公开 EvidenceSpan；主线馆藏结果卡另接同一入口。不把无证据的策划说明当原文引用。
- 修复 Reader 跨页选择被绑定单页的问题，跨页原生复制保留，单页标注/引用要求逐页选择。复制权限失败保留选文，提供手动复制；现有作品引用加载失败不再无限显示生成中，复制/导出前重读来源。
- 真实研究列表由原 ResearchProject 读取；目标须显式选择，新建复用原幂等创建，不自动启动模型任务。选材使用同一 owner 项目与加密数据，去重、备注和撤销复用原命令；冲突保留输入。
- 访客仅明确操作后保存来源身份、范围、校验和、本人备注及时间，不在浏览器持久化原文、题名或引用正文。打开/转存/复制/导出时重新核对公开来源。转存须登录后明确选择材料和研究，保留本机记录，不自动同步。
- 多格式导出用实际请求完成状态，支持部分完成、取消与仅重试失败项；下载时再核对当前来源，输出已完成格式的合并文本。没有后台虚构长任务或定时假进度。

## 契约与边界

- 新增 `POST /reading/citation-preview/`，输入 `edition_id?`、`reference?`、`selected_text?`。返回 `source`、`reference`、`citations`，成功和失败均 `no-store`。源身份仅由 AnonymousUser 公共视图复核，即使管理用户也不能通过此接口导出未公开正文；引用格式复用原 `citation_bundle`。
- 选文字段只做空白布局归一化后唯一匹配，不猜重复段落；校验取得代码点范围 `selection_start`/`selection_end`，保存必须带原文 hash。现有单页/span/多锚点引用继续支持；选段身份加入range，因此同页两段不会合并为整页。
- `EvidenceAnchorInput` 增加可选 `selection_start`、`selection_end`；`SelectionInput` 增加 `request_id`、`note`、按reference identity映射的`notes`、`expected_owner_id`。`ProjectCreateInput` 增加 `expected_owner_id`。旧客户端字段可选，新共享入口始终传本人身份。
- 新建和选材写请求禁止401刷新重放，后端在写入前比对 expected_owner_id 与 request.user.pk。会话变化卸载浮层私人状态；未知写结果锁定输入并保留同一请求id，可重试或明确关闭后到研究核对。
- 选材请求记录放在既有加密 payload 最多100项，旧请求若超出保留窗口仍受原 revision 并发约束；不新增表或迁移。备注随选材及最近50次移除保留，重复加入不覆盖原备注。
- `source.work_url` 使用已公开snapshot edition.public_slug，否则使用稳定edition.id；不读取不存在的 Work.slug 或草稿字段。

## 验证记录

- `node node_modules/eslint/bin/eslint.js components/shared-citation-overlay.tsx components/work-citation-panel.tsx components/reader-shell.tsx components/reader/use-reader-selection.ts components/public/issue-block-view.tsx lib/api/shared-citation.client.ts lib/local-citation-materials.ts lib/api/research.client.ts lib/api/research-evidence.ts lib/api/research-navigation.ts tests/shared-citation.spec.ts`：退出0，1条实际封面img提示。
- Python AST解析 `research.py`、`research_serializers.py`、`shared_citation_views.py`、`urls.py`、新增测试：5文件退出0。
- PostCSS解析新增CSS：71节点，退出0。
- 全量TypeScript先发现WorkCitationPanel的null和合成测试fixture缺source，均修复；最后 `node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false`（session50645）退出1，仅并行主线 `lib/api/opinion-entry.client.ts:29` 的 CatalogSearchWork.primary_edition 不存在；本单元未再报错，完整TypeScript尚不能写通过。
- 新增后端13函数/15参数案例、前端4合成契约案例，仅编写，未执行。覆盖匿名公开权限、精确范围、同页去重、撤回/正文变化、幂等重试、备注保护、撤销顺序、账户切换与本机数据约束。
- 未运行正式测试、浏览器、构建、截图比较、模型/OCR、迁移、生产操作。字体/布局、剪贴板与下载浏览器限制仍待统一验收；源码检查不代表PDF逐图验收完成。

## 本单元文件白名单

1. `api/reading/shared_citation_views.py`
2. `api/reading/research.py`
3. `api/reading/research_serializers.py`
4. `api/reading/urls.py`（只新增 shared_citation_views 导入与 citation-preview 路径；其他来源关注改动归其单元）
5. `api/tests/test_shared_citation_20261019.py`
6. `web/components/shared-citation-overlay.tsx`
7. `web/components/shared-citation-overlay.module.css`
8. `web/components/work-citation-panel.tsx`
9. `web/components/reader-shell.tsx`
10. `web/components/reader/use-reader-selection.ts`
11. `web/components/public/issue-block-view.tsx`
12. `web/lib/api/shared-citation.client.ts`
13. `web/lib/api/research.client.ts`
14. `web/lib/api/research-evidence.ts`
15. `web/lib/api/research-navigation.ts`
16. `web/lib/local-citation-materials.ts`
17. `web/tests/shared-citation.spec.ts`
18. `docs/stl4/SHARED_CITATION_20261019.md`

主线需在统一schema生成范围加入新公开预览接口并重新生成前端契约；本单元未修改生成文件和全局记录，也未自行提交。既有dirty文件继续保留。
