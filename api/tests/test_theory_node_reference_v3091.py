import pytest
from django.utils import timezone

from catalog.models import (
    Discipline, KnowledgeNode, KnowledgeNodeAlias, KnowledgeNodeDiscipline,
    KnowledgeNodeSubdiscipline, KnowledgeNodeTopic, Subdiscipline, Topic,
)
from .editorial_fixtures import editorial_request

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("original_name", ["Reference Theory", ""])
def test_reference_creation_assigns_address_without_an_extra_visible_field(api_client, admin_user, original_name):
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/theory-system/nodes/", {
        "node_type": "theory_tradition", "canonical_name_zh": "参考图建档", "canonical_name_en": original_name, "status": "draft",
    }, format="json")
    assert response.status_code == 201, response.data
    assert response.data["slug"] and response.data["status"] == "draft"
    if original_name:
        assert response.data["slug"] == "reference-theory"


def make_node(published, actor):
    discipline = Discipline.objects.create(name="保留学科", code="reference-keep", slug="reference-keep")
    subdiscipline = Subdiscipline.objects.create(name="保留子学科", slug="reference-keep-sub", discipline=discipline)
    topic = Topic.objects.create(name="保留主题", slug="reference-keep-topic")
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition", canonical_name_zh="保留理论", slug="reference-keep-node",
        summary="原简介", definition="原定义", theoretical_boundary="原边界",
        core_questions=["原问题"], basic_propositions=["原命题"],
        start_year=1920, end_year=1980, period_label="原时期", sort_order=9,
        primary_discipline=discipline, status="published" if published else "draft",
        published_at=timezone.now() if published else None,
    )
    alias = KnowledgeNodeAlias.objects.create(
        node=node, alias="保留来源别名", language="de", source_kind="pdf_evidence", is_verified=False,
    )
    reviewed_at = timezone.now()
    links = {
        "discipline_links": KnowledgeNodeDiscipline.objects.create(
            node=node, discipline=discipline, relation_type="primary", discipline_specific_summary="人工学科说明",
            sort_order=7, status="published", reviewed_by=actor, reviewed_at=reviewed_at,
        ),
        "subdiscipline_links": KnowledgeNodeSubdiscipline.objects.create(
            node=node, subdiscipline=subdiscipline, is_primary=True, relation_role="home",
            source="人工确认来源", confidence=.73, sort_order=8, status="published",
            reviewed_by=actor, reviewed_at=reviewed_at,
        ),
        "topic_links": KnowledgeNodeTopic.objects.create(
            node=node, topic=topic, relation_label="人工主题关系", source="人工确认来源",
            confidence=.68, sort_order=6, status="published", reviewed_by=actor, reviewed_at=reviewed_at,
        ),
    }
    return node, alias, links


def save_and_publish(api_client, node, payload, published):
    url = f"/api/catalog/admin/theory-system/nodes/{node.pk}/"
    saved = editorial_request(api_client, "patch", url, payload, format="json")
    assert saved.status_code == (202 if published else 200), saved.data
    if published:
        response = api_client.post(
            f"/api/catalog/admin/editorial-revisions/{saved.data['editorial_revision']['id']}/publish/",
            {}, format="json",
        )
        assert response.status_code == 200, response.data
    return saved


@pytest.mark.parametrize("published", [False, True])
def test_basic_fields_preserve_hidden_node_and_relation_data(api_client, admin_user, published):
    node, alias, links = make_node(published, admin_user)
    protected = {row.pk: type(row).objects.filter(pk=row.pk).values().get() for row in [alias, *links.values()]}
    api_client.force_authenticate(admin_user)
    save_and_publish(api_client, node, {"canonical_name_zh": "已改名称", "summary": "已改简介"}, published)
    node.refresh_from_db()
    assert node.canonical_name_zh == "已改名称" and node.summary == "已改简介"
    assert (node.definition, node.theoretical_boundary, node.period_label, node.sort_order) == ("原定义", "原边界", "原时期", 9)
    assert node.core_questions == ["原问题"] and node.basic_propositions == ["原命题"]
    assert (node.start_year, node.end_year) == (1920, 1980)
    for row in [alias, *links.values()]:
        assert type(row).objects.filter(pk=row.pk).values().get() == protected[row.pk]


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("field", ["aliases", "discipline_links", "subdiscipline_links", "topic_links"])
def test_adding_one_relation_preserves_existing_identity_provenance_and_review(api_client, admin_user, published, field):
    node, alias, links = make_node(published, admin_user)
    existing = alias if field == "aliases" else links[field]
    before = type(existing).objects.filter(pk=existing.pk).values().get()
    if field == "aliases":
        rows = [{"alias": alias.alias, "language": alias.language, "alias_type": alias.alias_type}, {"alias": "新增别名"}]
    elif field == "discipline_links":
        other = Discipline.objects.create(name="新增学科", code="reference-add", slug="reference-add")
        rows = [{"discipline_id": str(existing.discipline_id)}, {"discipline_id": str(other.pk), "relation_type": "related"}]
    elif field == "subdiscipline_links":
        other = Subdiscipline.objects.create(name="新增子学科", slug="reference-add-sub", discipline=node.primary_discipline)
        rows = [{"subdiscipline_id": str(existing.subdiscipline_id)}, {"subdiscipline_id": str(other.pk)}]
    else:
        other = Topic.objects.create(name="新增主题", slug="reference-add-topic")
        rows = [{"topic_id": str(existing.topic_id)}, {"topic_id": str(other.pk)}]
    api_client.force_authenticate(admin_user)
    saved = save_and_publish(api_client, node, {field: rows}, published)
    assert type(existing).objects.filter(pk=existing.pk).values().get() == before
    assert getattr(node, field).count() == 2
    if published:
        retained = next(row for row in saved.data[field] if row.get("id") == str(existing.pk))
        assert retained["id"] == str(existing.pk)


@pytest.mark.parametrize("field", ["discipline_links", "subdiscipline_links", "topic_links"])
def test_duplicate_link_is_rejected_without_losing_original_data(api_client, admin_user, field):
    node, _alias, links = make_node(False, admin_user)
    existing = links[field]
    before = type(existing).objects.filter(pk=existing.pk).values().get()
    foreign_key = field.removesuffix("_links")
    row = {f"{foreign_key}_id": str(getattr(existing, f"{foreign_key}_id"))}
    api_client.force_authenticate(admin_user)
    response = editorial_request(api_client, "patch", f"/api/catalog/admin/theory-system/nodes/{node.pk}/", {field: [row, row], "summary": "不应保存"}, format="json")
    assert response.status_code == 400, response.data
    assert type(existing).objects.filter(pk=existing.pk).values().get() == before
    node.refresh_from_db()
    assert node.summary == "原简介"
