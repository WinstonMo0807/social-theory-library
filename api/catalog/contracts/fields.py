"""One declaration for a field's editorial and publication semantics.

Research producer policies remain adapters; they may propose values but do
not define canonical requirements or silently loosen publication validation.
"""
from dataclasses import asdict, dataclass


DOCUMENT_TYPES = ("book", "journal_article", "journal_issue", "thesis", "report")
_IDENTITY = ("title", "authors", "isbn10", "isbn13", "publisher", "publication_year")


@dataclass(frozen=True)
class CatalogFieldContract:
    name: str
    domain_object: str
    section: str
    label: str
    data_type: str = "string"
    nullable: bool = False
    required_for: tuple[str, ...] = ()
    normalizer: str = "identity"
    validator: str = "none"
    candidate_sources: tuple[str, ...] = ("manual", "pdf", "structured", "verified_web")
    authority_resolver: str = ""
    dependencies: tuple[str, ...] = ()
    publication_rules: tuple[str, ...] = ("human_confirmation",)
    blocking_rules: tuple[str, ...] = ("conflict", "invalid_value", "required_unconfirmed")
    warning_rules: tuple[str, ...] = ("stale",)
    projection_impact: tuple[str, ...] = ("catalog_metadata",)
    display: str = "input"

    @property
    def key(self):
        return f"{self.domain_object}.{self.name}"

    def payload(self):
        return {"key": self.key, **asdict(self)}


def _work(name, label, **kwargs):
    return CatalogFieldContract(name, "work", "work", label, **kwargs)


def _edition(name, label, **kwargs):
    return CatalogFieldContract(name, "edition", "bibliography", label, **kwargs)


FIELDS = (
    CatalogFieldContract("file", "asset", "file", "文件", data_type="file", required_for=DOCUMENT_TYPES,
                         publication_rules=("required_for_document_holdings", "original_preserved", "readable_validated_asset"),
                         projection_impact=("document",)),
    _work("title", "作品题名", required_for=DOCUMENT_TYPES, normalizer="trim"),
    _work("subtitle", "副题名"),
    _work("original_title", "原文题名"),
    _work("uniform_title", "规范题名"),
    _work("document_type", "资源类型", data_type="enum", required_for=DOCUMENT_TYPES, validator="document_type"),
    _work("language", "正文语言", required_for=DOCUMENT_TYPES),
    _work("original_language", "原文语言"),
    _work("first_publication_date", "首次出版日期", data_type="date", nullable=True),
    _work("translation_of", "原作", data_type="entity", nullable=True, authority_resolver="work"),
    _work("abstract", "简介", data_type="text", dependencies=_IDENTITY, display="textarea"),
    _work("cover", "封面", data_type="image", dependencies=_IDENTITY, warning_rules=("missing", "stale"),
          projection_impact=("public", "recommendation"), display="media"),
    _work("recommendation_image", "推荐图例", data_type="image", dependencies=_IDENTITY,
          projection_impact=("public", "recommendation"), display="media"),
    _edition("journal_contents", "本期目录与论文", data_type="relation_list", display="journal_contents"),
    _edition("publication_mode", "公开内容", data_type="enum", validator="publication_mode", candidate_sources=("manual",)),
    _edition("version_label", "版本说明"),
    _edition("publication_date", "出版日期", data_type="date", nullable=True),
    _edition("publication_year", "出版年份", data_type="integer", nullable=True,
             required_for=("journal_article", "journal_issue"), normalizer="integer", validator="publication_year",
             dependencies=("title", "isbn10", "isbn13", "publisher")),
    _edition("publisher", "出版社", authority_resolver="publisher",
             dependencies=("title", "isbn10", "isbn13", "publication_year")),
    _edition("publisher_authority_id", "规范出版社", data_type="entity", nullable=True, authority_resolver="publisher"),
    _edition("publication_place", "出版地", warning_rules=("missing", "stale")),
    _edition("isbn10", "ISBN-10", data_type="identifier", normalizer="isbn", validator="isbn10"),
    _edition("isbn13", "ISBN-13", data_type="identifier", normalizer="isbn", validator="isbn13"),
    _edition("isbn", "ISBN 兼容值", data_type="identifier", normalizer="isbn", validator="isbn", publication_rules=("compatibility_alias",)),
    _edition("responsibility_statement", "原书责任说明", data_type="text", display="textarea"),
    _edition("series", "丛书"),
    _edition("extent", "页数或篇幅"),
    _edition("journal_title", "期刊", required_for=("journal_article", "journal_issue")),
    _edition("volume", "卷", required_for=("journal_issue",)),
    _edition("issue", "期", required_for=("journal_issue",)),
    _edition("page_range", "页码"),
    _edition("doi", "DOI", data_type="identifier", normalizer="doi", validator="doi"),
    _edition("degree_institution", "学位授予单位", required_for=("thesis",), authority_resolver="organization"),
    _edition("degree_type", "学位类型"),
    _edition("report_institution", "发布机构", required_for=("report",), authority_resolver="organization"),
    *(CatalogFieldContract(name, "contribution", "contributors", label, data_type="entity_list",
                           authority_resolver="person", display="entity_picker",
                           required_for=tuple(kind for kind in DOCUMENT_TYPES if kind != "journal_issue") if name == "authors" else (),
                           dependencies=_IDENTITY if name == "translators" else ())
      for name, label in (("authors", "作者"), ("translators", "译者"), ("chief_editors", "主编"),
                          ("editors", "编者"), ("annotators", "校注"), ("photographers", "摄影"), ("other_contributors", "其他贡献者"))),
    *(CatalogFieldContract(name, "work", section, label, data_type="relation_list", authority_resolver=resolver,
                           dependencies=dependencies, display="entity_picker")
      for name, label, section, resolver, dependencies in (
          ("disciplines", "学科", "classification", "discipline", ("title", "authors", "abstract")),
          ("subdisciplines", "子学科", "classification", "subdiscipline", ("title", "authors", "abstract", "disciplines")),
          ("topics", "主题", "knowledge", "topic", ("title", "authors", "abstract", "disciplines")),
          ("theories", "理论传统", "knowledge", "knowledge_node", ("title", "authors", "abstract", "disciplines", "topics")),
      )),
    CatalogFieldContract("reader_asset", "asset", "reader", "阅读文件", data_type="entity", nullable=True, projection_impact=("document",)),
    CatalogFieldContract("ocr_text", "document_revision", "reader", "正文文字", data_type="boolean", candidate_sources=(), projection_impact=("document",)),
    CatalogFieldContract("page_labels", "page", "reader", "引用页码", data_type="boolean", candidate_sources=(), projection_impact=("document",)),
    CatalogFieldContract("curation", "work", "curation", "策展", data_type="boolean", projection_impact=("recommendation",)),
)

FIELD_CONTRACTS = {field.name: field for field in FIELDS}
if len(FIELD_CONTRACTS) != len(FIELDS):
    raise RuntimeError("字段契约名称重复。")
for field in FIELDS:
    if not set(field.dependencies).issubset(FIELD_CONTRACTS):
        raise RuntimeError(f"{field.key} 引用了未登记的依赖字段。")

SECTION_FIELDS = {section: tuple(field.name for field in FIELDS if field.section == section)
                  for section in dict.fromkeys(field.section for field in FIELDS)}
FIELD_LABELS = {field.name: field.label for field in FIELDS}
WORK_FIELDS = tuple("translation_of_id" if field.name == "translation_of" else field.name
                    for field in FIELDS if field.section == "work" and field.data_type != "image")
BIBLIOGRAPHY_FIELDS = tuple(field.name for field in FIELDS
                           if field.section == "bibliography" and field.name != "journal_contents")
FIELD_DEPENDENCIES = {field.name: field.dependencies for field in FIELDS if field.dependencies}
# An operational matching check, not a second canonical field.
FIELD_DEPENDENCIES["edition_match"] = _IDENTITY
REQUIRED_FIELDS = {kind: tuple(field.name for field in FIELDS if kind in field.required_for) for kind in DOCUMENT_TYPES}


def required_fields(document_type, *, has_document=True):
    names = REQUIRED_FIELDS.get(document_type, REQUIRED_FIELDS["book"])
    return tuple(name for name in names if has_document or name != "file")
