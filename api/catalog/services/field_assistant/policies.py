from __future__ import annotations

from dataclasses import dataclass

from catalog.models import Contribution


@dataclass(frozen=True, slots=True)
class AssistantFieldPolicy:
    key: str
    label: str
    action_label: str
    lookup_label: str
    create_label: str
    value_kind: str
    entity_type: str
    metadata_fields: tuple[str, ...]
    enrichment_fields: tuple[str, ...]
    entity_target_types: tuple[str, ...]
    contribution_role: str = ""
    allow_authority: bool = True
    allow_web: bool = True
    query_context_fields: tuple[str, ...] = (
        "title",
        "original_title",
        "isbn",
        "publisher",
        "publication_year",
    )
    strategy_labels: tuple[str, ...] = ()


FIELD_POLICIES: dict[str, AssistantFieldPolicy] = {}


def _register(policy: AssistantFieldPolicy, *aliases: str) -> None:
    for name in (policy.key, *aliases):
        normalized = str(name).strip().casefold()
        if normalized in FIELD_POLICIES:
            raise RuntimeError(f"重复的字段助手策略：{normalized}")
        FIELD_POLICIES[normalized] = policy


_register(
    AssistantFieldPolicy(
        key="author",
        label="作者",
        action_label="采用作者",
        lookup_label="智能查找",
        create_label="学者",
        value_kind="entity",
        entity_type="person",
        metadata_fields=("author", "authors", "contributors"),
        enrichment_fields=("author", "authors"),
        entity_target_types=("person",),
        contribution_role=Contribution.Role.AUTHOR,
        strategy_labels=(
            "本书正文与版权页",
            "馆内已有学者",
            "书名、ISBN与正式书目资料",
            "人物权威资料",
            "其他外部资料",
        ),
    ),
    "authors",
)

_register(
    AssistantFieldPolicy(
        key="translator",
        label="译者",
        action_label="采用译者",
        lookup_label="智能查找",
        create_label="学者",
        value_kind="entity",
        entity_type="person",
        metadata_fields=("translator", "translators", "contributors"),
        enrichment_fields=("translator", "translators"),
        entity_target_types=("person",),
        contribution_role=Contribution.Role.TRANSLATOR,
        strategy_labels=(
            "当前版本版权页",
            "本书正文与文字识别结果",
            "ISBN与出版社资料",
            "馆内已有学者",
            "其他正式书目资料",
        ),
    ),
    "translators",
)

_register(
    AssistantFieldPolicy(
        key="publisher",
        label="出版社",
        action_label="采用出版社",
        lookup_label="重新查找",
        create_label="出版社",
        value_kind="entity_or_value",
        entity_type="publisher",
        metadata_fields=("publisher",),
        enrichment_fields=("publisher",),
        entity_target_types=("publisher",),
        allow_authority=False,
        strategy_labels=(
            "当前版本版权页",
            "ISBN与正式书目资料",
            "馆内出版社记录",
        ),
    )
)

_register(
    AssistantFieldPolicy(
        key="publication_year",
        label="本版出版年份",
        action_label="采用年份",
        lookup_label="智能查找",
        create_label="",
        value_kind="value",
        entity_type="",
        metadata_fields=("publication_year",),
        enrichment_fields=("publication_year",),
        entity_target_types=(),
        allow_authority=False,
        strategy_labels=("当前版本版权页", "ISBN与当前出版社书目", "同版本馆藏记录"),
    ),
    "year",
)

_register(
    AssistantFieldPolicy(
        key="abstract",
        label="简介",
        action_label="采用简介",
        lookup_label="查找简介",
        create_label="",
        value_kind="value",
        entity_type="",
        metadata_fields=("abstract", "summary"),
        enrichment_fields=("abstract",),
        entity_target_types=(),
        allow_authority=False,
        strategy_labels=("本书内容简介、封底或摘要", "出版社正式介绍", "可靠馆藏介绍", "待管理员确认的AI整理"),
    ),
    "summary",
)

_register(
    AssistantFieldPolicy(
        key="topic",
        label="主题",
        action_label="采用主题",
        lookup_label="获取分类建议",
        create_label="主题",
        value_kind="entity",
        entity_type="topic",
        metadata_fields=("topic", "topics"),
        enrichment_fields=("topic", "topics"),
        entity_target_types=("topic", "knowledge_node"),
        allow_web=False,
        query_context_fields=("title", "abstract", "authors"),
        strategy_labels=(
            "馆内已有主题",
            "已确认的作品内容与人物关系",
            "编辑确认的馆藏分类",
        ),
    ),
    "topics",
)

_register(
    AssistantFieldPolicy(
        key="theory",
        label="理论传统",
        action_label="采用理论传统",
        lookup_label="获取分类建议",
        create_label="理论传统",
        value_kind="entity",
        entity_type="theory",
        metadata_fields=(
            "theory",
            "theories",
            "theory_school",
            "theory_schools",
            "knowledge_nodes",
        ),
        enrichment_fields=("theory", "theories", "relation"),
        entity_target_types=("theory", "knowledge_node"),
        allow_web=False,
        query_context_fields=("title", "abstract", "authors", "topics"),
        strategy_labels=(
            "馆内已有理论节点",
            "已确认的作品内容与人物关系",
            "编辑确认的馆藏分类",
        ),
    ),
    "theories",
    "theory_school",
    "theory_schools",
    "theory_tradition",
)


def get_field_policy(field_name: str) -> AssistantFieldPolicy:
    normalized = str(field_name or "").strip().casefold()
    try:
        return FIELD_POLICIES[normalized]
    except KeyError as exc:
        raise ValueError("该字段暂不支持智能查找。") from exc


def available_field_policies() -> tuple[AssistantFieldPolicy, ...]:
    return tuple({policy.key: policy for policy in FIELD_POLICIES.values()}.values())
