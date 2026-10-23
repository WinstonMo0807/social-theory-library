"""Read-only observations from the existing outline, accepted by the draft save."""
from django.core import signing
from django.db import transaction

from catalog.models import Asset
from catalog.services.document_outline import _source_current, OutlineConflict
from catalog.services.workspace_edits import _digest, workspace_edit_version
from catalog.services.work_editor import WorkflowEditConflict

SALT = "stl.journal-outline-candidate.v1"


def _current(asset):
    _source_current(asset)
    revision = asset.outline_revisions.first()
    document = asset.document_revisions.filter(is_active=True).first()
    if not revision:
        return None
    if revision.source_checksum != asset.sha256 or revision.document_revision_id != (document.pk if document else None):
        raise OutlineConflict("目录候选对应旧文件或旧正文，请先重新生成目录。")
    return revision


def directory(edition, owner, *, asset_id=None, page=1):
    assets = edition.assets.filter(kind="normalized", is_current=True, status="ready", validation_status="valid").order_by("created_at", "pk")
    files = [{"id":str(row.pk), "name":row.original_filename or "阅读文件", "page_count":row.page_count} for row in assets]
    result = {"owner_id":str(owner.pk), "edition_id":str(edition.pk), "edit_version":workspace_edit_version(edition),
        "files":files, "asset_id":None, "outline_revision_id":None, "count":0, "page":page, "page_size":50, "results":[],
        "message":"请选择本期阅读文件。" if files else "尚无就绪的阅读文件，请先完成文件处理。"}
    asset = assets.filter(pk=asset_id).first() if asset_id else assets.first() if len(files)==1 else None
    if asset_id and not asset:
        raise OutlineConflict("所选文件已变化，或不属于当前出版版本。")
    if not asset:
        return result
    result["asset_id"] = str(asset.pk)
    revision = _current(asset)
    if not revision:
        result["message"] = "尚无目录候选，请先在自动目录与跳转校准中生成。"
        return result
    nodes = revision.nodes
    result.update(outline_revision_id=str(revision.pk), count=len(nodes), message="标题来自原目录观察；栏目、广告、作者和终止页仍需对照原文，不会自动判定为论文。")
    for node in nodes[(page-1)*50:page*50]:
        proof = {"owner_id":str(owner.pk), "edition_id":str(edition.pk), "edit_version":result["edit_version"],
            "asset_id":str(asset.pk), "source_checksum":asset.sha256, "document_revision_id":str(revision.document_revision_id or ""),
            "outline_revision_id":str(revision.pk), "node_id":node["id"], "node_digest":_digest(node)}
        result["results"].append({"node_id":node["id"], "title":node["title"], "printed_label":node.get("printed_label", ""),
            "pdf_page":node.get("pdf_page"), "contents_page":node.get("contents_page"), "source":node["source"],
            "calibration_status":node["calibration_status"], "candidate_source":signing.dumps(proof, salt=SALT, compress=True)})
    return result


def prepare_rows(edition, actor, rows, expected_version):
    """Called under the original actor/Edition/Work save locks; no separate write."""
    prepared, observations, proofs = [], [], []
    for position, row in enumerate(rows):
        token = row.get("candidate_source")
        if not token:
            prepared.append(dict(row)); continue
        try:
            proof = signing.loads(token, salt=SALT, max_age=7*24*60*60)
        except signing.BadSignature:
            raise WorkflowEditConflict("目录候选已失效，请保留填写内容并重新读取来源。")
        if (proof.get("owner_id") != str(actor.pk) or proof.get("edition_id") != str(edition.pk)
                or proof.get("edit_version") != expected_version):
            raise WorkflowEditConflict("目录候选不属于当前账户或书目修订，请重新核对来源。")
        proofs.append((position, row, proof))
        prepared.append({key:value for key,value in row.items() if key != "candidate_source"})
    if not proofs:
        return prepared, observations
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Journal candidate adoption requires the workspace save transaction")
    assets = {str(asset.pk):asset for asset in Asset.objects.select_for_update().filter(
        pk__in={proof["asset_id"] for _,_,proof in proofs}, edition=edition, kind="normalized", is_current=True).order_by("pk")}
    seen = set()
    revisions = {}
    for position, row, proof in proofs:
        asset = assets.get(proof["asset_id"])
        if not asset or asset.sha256 != proof["source_checksum"]:
            raise WorkflowEditConflict("候选原文件已更换，请保留输入并重新核对。")
        try:
            if asset.pk not in revisions:
                revision = _current(asset)
                revisions[asset.pk] = (revision, {node["id"]:node for node in revision.nodes} if revision else {})
            revision, nodes = revisions[asset.pk]
        except OutlineConflict as error:
            raise WorkflowEditConflict(str(error)) from error
        node = nodes.get(proof["node_id"])
        if (not revision or str(revision.pk) != proof["outline_revision_id"] or not node
                or str(revision.document_revision_id or "") != proof["document_revision_id"] or _digest(node) != proof["node_digest"]):
            raise WorkflowEditConflict("候选目录已有新修订，请保留输入并重新核对所选条目。")
        identity = (asset.pk, node["id"])
        if identity in seen:
            raise WorkflowEditConflict("同一目录候选不能重复填入本次草稿。")
        seen.add(identity)
        observations.append({"source":{key:value for key,value in proof.items() if key not in {"owner_id", "edit_version"}},
            "position":position, "observed_title":node["title"], "contents_page":node.get("contents_page"),
            "pdf_page":node.get("pdf_page"), "final_title":row["title"], "final_author_display":row.get("author_display", ""),
            "final_page_range":row.get("page_range", ""), "correctness":"not_evaluated"})
    return prepared, observations
