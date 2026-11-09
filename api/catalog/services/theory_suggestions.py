"""Read-compatible tombstone for pre-Intelligence extraction workers.

Already claimed old ingestion jobs may still call this name. They must not
create WorkNodeRelation, EvidenceSnippet or TheoryReviewTask candidates.
"""


def generate_theory_review_tasks(asset, *, actor=None, force=False):
    return {"enabled": False, "retired": True, "created": 0, "updated": 0,
        "new_node_tasks": 0, "reason": "学术分析已迁入 Intelligence；旧审核记录保留。",
        "workspace_url": f"/admin/intelligence?work_id={asset.edition.work_id}"}
