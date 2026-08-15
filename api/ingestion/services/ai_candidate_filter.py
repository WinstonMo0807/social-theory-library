from __future__ import annotations

import json

from .ai_client import AIClient, AIInvalidOutput, AIResult


CANDIDATE_RECONCILIATION_PROMPT_VERSION = "candidate-reconciliation-v2"
TARGET_TYPES = ("bibliographic", "agent", "concept", "relation", "timeline")

CANDIDATE_RECONCILIATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidate_group_id", "target_type", "proposals"],
    "properties": {
        "candidate_group_id": {"type": "string"},
        "target_type": {"type": "string", "enum": list(TARGET_TYPES)},
        "proposals": {
            "type": "array",
            "maxItems": 48,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "candidate_id",
                    "decision",
                    "source_record_ids",
                    "evidence_ids",
                    "match_reasons",
                    "conflicts",
                    "warnings",
                    "requires_human_review",
                ],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["retain", "reject", "needs_review"],
                    },
                    "source_record_ids": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "evidence_ids": {
                        "type": "array",
                        "maxItems": 24,
                        "items": {"type": "string"},
                    },
                    "match_reasons": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "conflicts": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "warnings": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "requires_human_review": {"type": "boolean"},
                },
            },
        },
    },
}

CANDIDATE_RECONCILIATION_SYSTEM_PROMPT = """
你是社会理论数字图书馆的候选整理器。输入只包含系统已经取得的候选、来源记录和证据标识。
你只能比较、排序和标记这些输入候选，不得补写输入中没有的事实，不得调用网络，不得声称已经保存、合并、接受、发布或修改数据。

书目候选必须区分抽象作品与具体版本。出版地只能依据该版本的标题页、版权页、CIP 或外部版本记录，不得根据出版社今天的总部推断历史出版地。译者、编者、作者、出版者、发行者和印刷者不得混为同一角色。

人物候选要兼顾中文学者与外国学者。中文名、原文名、译名、别名、简繁体和拼音只能用于召回。仅凭姓名相同不得合并。出生年、逝世年、机构、作品、外部权威标识相互支持时才可说明匹配理由；存在冲突时必须标记 needs_review。

学科、子学科、理论传统、理论节点和主题要区分层级、同义词与相关概念。理论影响、批判、发展、代表学者、奠基著作、时间轴解释等判断必须保持 requires_human_review 为 true。文本中只出现姓名或概念不能证明影响关系。

source_record_ids 与 evidence_ids 只能从输入白名单逐字复制。不得生成新的标识。每个保留或拒绝建议都必须引用至少一个允许的来源记录或证据。输出不包含模型自报置信度，只输出 JSON Schema 允许的字段。
""".strip()


def reconcile_candidate_group(
    *,
    candidate_group_id: str,
    target_type: str,
    candidates: list[dict],
    allowed_source_record_ids: set[str] | list[str] | tuple[str, ...],
    allowed_evidence_ids: set[str] | list[str] | tuple[str, ...],
    client: AIClient | None = None,
) -> AIResult:
    """Filter an existing candidate group without persisting any decision.

    The caller remains responsible for showing the proposals to an
    administrator. This function deliberately has no model imports and no
    database write path.
    """

    group_id = str(candidate_group_id).strip()
    if not group_id:
        raise ValueError("candidate_group_id 不能为空。")
    normalized_target = str(target_type).strip().casefold()
    if normalized_target not in TARGET_TYPES:
        raise ValueError("target_type 不在允许范围内。")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("至少需要一个候选。")
    if len(candidates) > 48:
        raise ValueError("单次候选筛选最多处理 48 项。")

    allowed_candidate_ids = {
        str(candidate.get("candidate_id") or "").strip()
        for candidate in candidates
        if isinstance(candidate, dict)
    }
    if "" in allowed_candidate_ids or len(allowed_candidate_ids) != len(candidates):
        raise ValueError("每个候选必须具有唯一 candidate_id。")
    allowed_sources = {str(value).strip() for value in allowed_source_record_ids if str(value).strip()}
    allowed_evidence = {str(value).strip() for value in allowed_evidence_ids if str(value).strip()}

    payload = {
        "candidate_group_id": group_id,
        "target_type": normalized_target,
        "candidates": candidates,
        "allowed_source_record_ids": sorted(allowed_sources),
        "allowed_evidence_ids": sorted(allowed_evidence),
    }
    result = (client or AIClient()).generate_json(
        task="candidate-reconciliation",
        system_prompt=CANDIDATE_RECONCILIATION_SYSTEM_PROMPT,
        document_text=json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
        schema=CANDIDATE_RECONCILIATION_SCHEMA,
        prompt_version=CANDIDATE_RECONCILIATION_PROMPT_VERSION,
    )
    data = result.data
    if data.get("candidate_group_id") != group_id:
        raise AIInvalidOutput("AI 输出的 candidate_group_id 与请求不一致。")
    if data.get("target_type") != normalized_target:
        raise AIInvalidOutput("AI 输出的 target_type 与请求不一致。")

    proposals = []
    seen_candidate_ids: set[str] = set()
    for proposal in data.get("proposals", []):
        candidate_id = str(proposal.get("candidate_id") or "").strip()
        if candidate_id not in allowed_candidate_ids:
            raise AIInvalidOutput("AI 输出引用了输入之外的候选。")
        if candidate_id in seen_candidate_ids:
            raise AIInvalidOutput("AI 输出重复引用同一候选。")
        seen_candidate_ids.add(candidate_id)
        source_ids = {str(value).strip() for value in proposal.get("source_record_ids", [])}
        evidence_ids = {str(value).strip() for value in proposal.get("evidence_ids", [])}
        if not source_ids.issubset(allowed_sources):
            raise AIInvalidOutput("AI 输出引用了白名单之外的 source_record_id。")
        if not evidence_ids.issubset(allowed_evidence):
            raise AIInvalidOutput("AI 输出引用了白名单之外的 evidence_id。")
        if not source_ids and not evidence_ids:
            raise AIInvalidOutput("每个建议必须引用至少一个来源记录或证据。")
        proposals.append({**proposal, "requires_human_review": True})

    return AIResult(
        data={**data, "proposals": proposals},
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
    )
