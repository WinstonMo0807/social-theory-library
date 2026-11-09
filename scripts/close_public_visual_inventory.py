"""Close source discovery, not runtime acceptance or design coverage."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/stl4/public-visual-20261110"


def rows(name):
    with (BASE / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(name, records):
    with (BASE / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


coverage = rows("COVERAGE.csv")
excluded = {"historical_design_reference", "disabled_in_public", "excluded_paused_demo"}
for row in coverage:
    if row["classification"] == "historical_design_reference":
        row["key_states_operations"] = "既有设计比较入口；保留路由与代码，不作为当前业务页面重做。"
        row["uncovered_reason"] = "历史候选展示，没有独立业务工作流；本轮排除但不删除。"
        row["business_review"] = "已据部署源码、导航与功能用途归类为历史设计入口。"
    elif row["classification"] not in excluded:
        row["business_review"] = "设计输入已对应：逐页操作笔记、组件、UI_CONTROLS、PAGE_BEHAVIOR、API/字段契约及BUSINESS_FINDINGS；运行验证另记，未计为通过。"
        row["uncovered_reason"] = "正式设计图、全站实现与逐消费者运行验证待完成；真实外部服务和生产写入不在隔离夹具验证范围。"
    if row["id"] == "PV008":
        row["key_states_operations"] += "；usage按本人project/plan和两方revision授权，最多40条/范围；内容修订撤旧授权；删除保留原阅读笔记。"
    if row["id"] in {"PV066", "PV122"}:
        row["key_states_operations"] += "；文章版本绑定评论：署名80/正文3000/同意公开；读者提交及本人删除，管理公开或拒绝/撤下，旧版评论不迁新版。"
    if row["id"] == "PV121":
        row["key_states_operations"] += "；mode=parallel独立双版本并读/手动对齐、同步/自由、术语笔记、私人保存与公共校准提交；来源修订变化须重新选择；手机面板切换保留两侧定位。"
write("COVERAGE.csv", coverage)

dynamic = rows("DYNAMIC_REQUESTS.csv")
notes = {
    "citation-manuscript-preview": "父组件传入 citation-audits/{id}/manuscript/ 或 citation-sources/{id}/segments/；page/page_size/revision与来源generation核对。",
    "reader-groups": "创建 /reading/groups/ 与既有 /reading/groups/{id}/ 命令；请求身份、成员和版本核对。",
    "workflow-inspector": "workflow-editor.inspectPdf读取上下文pdf_preview_url/preview_url，回退 /ingestion/items/{id}/preview/；鉴权文件读取。",
    "material-source-record": "workFilesPath限定work/edition及分页，附asset筛选；正式管理文件工作区。",
    "work-files.client": "internalPath限定catalog/admin或ingestion/items；HEAD核对MIME/长度/ETag；影响CSV走实际授权下载。",
    "workflow-live-preview": "edition封面查询返回的image_url，owner绑定blob请求；不是新业务入口。",
    "intake-confirmation": "服务端返回路径必须完全等于 /api/ingestion/items/{item}/preview/，去api前缀后鉴权HEAD/GET。",
    "outline-pdf-preview": "asset.preview_url为所选文件授权预览；asset及sha256共同绑定，切换/退出清理blob。",
    "person-resolution-workspace": "已存在 /catalog/admin/people/{id}/workspace/。",
    "candidate-review": "服务端descriptor.url/method；回退 /catalog/admin/candidate-review/{kind}/{id}/decision/，仅受支持候选类型。",
    "functional-health": "健康检查响应action.endpoint/method/body；权限、配置版本、请求身份及真实检查回执。",
    "publication-desk": "queueWorkspaceApi按work+edition读取library/works/{id}/?edition，或intake/{id}/；无对象则不请求。",
    "knowledge-object-context": "knowledge_studio服务投影decision_url/publish_url；先核对可用动作、未保存状态、已保存修订，不推导发布权限。",
    "scholar-portrait-panel": "scholarPortraitEndpoint -> /catalog/admin/scholars/{id}/portrait/。",
    "scholar-media": "scholarPortraitEndpoint -> /catalog/admin/scholars/{id}/portrait/。",
    "theory-system-admin": "空path为禁用查询；发布仅用已保存revision的publish_url，对应知识正式发布契约。",
    "research-entity-picker": "候选descriptor动作或既有实体决定端点；item/work/edition/draft_session身份和field/query随请求；馆藏维护模式不得直接创建外部实体。",
    "use-scholar-save": "固定原path/body/method，附X-Editor-Owner与IdempotencyKey，原回执actor/request核对。",
    "feedback-workspace": "adminFeedbackPath -> /catalog/admin/public-feedback/{id?}/；PATCH修订及请求身份。",
    "admin-feedback.client": "adminFeedbackPath -> /catalog/admin/public-feedback/{id?}/。",
    "parallel-calibration-workspace": "calibrationAdminPath -> /reading/parallel-calibrations/admin/{id?}/。",
    "knowledge-image-panel": "knowledgeImageEndpoint -> /catalog/admin/knowledge-media/{type}/{id}/。",
    "knowledge-media": "knowledgeImageEndpoint -> /catalog/admin/knowledge-media/{type}/{id}/。",
    "use-parallel-save": "已核对parallel-tasks创建/修订调用者；by-request恢复，版本冲突保留输入。",
}
for row in dynamic:
    if row["category"] == "caller-bound path":
        row["manual_resolution"] = "调用方绑定路径；对应PAGE_API_LINKS及API_CONTRACTS。共用请求函数不构成独立未命名业务；保留超时、取消、owner和会话失效处理。"
    else:
        row["manual_resolution"] = next((v for k, v in notes.items() if k in row["source"]), "")
    assert row["manual_resolution"], row
    row["runtime_status"] = "源码对应；不等于逐请求运行通过。"
write("DYNAMIC_REQUESTS.csv", dynamic)

active = [r for r in coverage if r["classification"] not in excluded]
assert all(r["key_states_operations"] and r["business_review"] for r in coverage)
assert all(r["api_contracts"] for r in active if r["classification"] not in {"compatibility_redirect", "shared_state"})
gate = {
    "date": "2026-11-10",
    "stage": "business_inventory_ready_for_design",
    "meaning": "部署基线、有效路由/消费者、字段、操作、接口、权限、关键状态和动态路径已形成可追溯设计输入；不是运行验收或设计覆盖完成。",
    "pages": len(coverage), "classification": dict(Counter(r["classification"] for r in coverage)),
    "api_method_paths": len(rows("API_CONTRACTS.csv")), "dynamic_request_sites_reviewed": len(dynamic),
    "ui_controls": len(rows("UI_CONTROLS.csv")), "page_api_candidate_links": len(rows("PAGE_API_LINKS.csv")),
    "evidence": ["BASELINE.md", "COVERAGE.csv", "PAGE_BEHAVIOR.json", "UI_CONTROLS.csv", "API_CONTRACTS.csv", "API_FIELD_CONTRACTS.csv", "PAGE_API_LINKS.csv", "DYNAMIC_REQUESTS.csv", "ROLE_CAPABILITIES.csv", "FEATURE_FLAGS.json", "BUSINESS_FINDINGS.md", "ANONYMOUS_HTTP.json", "FIXTURE_ROLE_HTTP.json", "VERIFICATION.md"],
    "runtime_limits": ["生产核查只读；未提交生产内容或启动任务。", "隔离GET、合成登录、PDF与草稿预览证据；未宣称全部写入通过。", "OCR、模型、邮件、远程存储等真实外部服务未在离线夹具中执行，设计保留未配置/等待/失败状态。", "Worker与API四项部署差异已登记，不引入内网Demo。"],
    "open_existing_defects": ["PV-PREVIEW-01：作品草稿的期刊目录未投影到实际预览。", "PV-FILTER-01：理论目录API使用node_type而后端读取type。"],
    "design_gate": "pending: every active route plus special state needs a real generated image or explicit shared mapping before UI implementation",
}
(BASE / "BUSINESS_GATE.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: gate[k] for k in ["stage", "pages", "classification", "api_method_paths", "dynamic_request_sites_reviewed", "ui_controls", "page_api_candidate_links"]}, ensure_ascii=False))
