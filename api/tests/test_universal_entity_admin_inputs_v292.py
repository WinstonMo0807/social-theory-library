from __future__ import annotations

from unittest.mock import patch

import pytest

from accounts.models import User
from catalog.models import (
    Discipline,
    DocumentType,
    Edition,
    Person,
    PublicationState,
    ScholarProfile,
    Work,
)
from catalog.services.research.contracts import (
    RESEARCH_CONTRACTS,
    ResearchImplementation,
    ResearchMutationPolicy,
)
from ingestion.models import EntityResolutionCandidate, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


MAINTENANCE_ENTITY_FIELDS = {
    "maintenance_subdisciplines": {
        "discipline": ("discipline",),
        "parent": ("subdiscipline",),
    },
    "maintenance_theory_nodes": {
        "filter_discipline": ("discipline",),
        "parent": ("knowledge_node",),
        "primary_discipline": ("discipline",),
        "related_disciplines": ("discipline",),
        "merge_target": ("knowledge_node",),
    },
    "maintenance_theory_relations": {
        "review_candidate": ("knowledge_node",),
        "new_node_discipline": ("discipline",),
        "source_node": ("knowledge_node",),
        "target_node": ("knowledge_node",),
    },
    "maintenance_theory_timeline": {
        "filter_discipline": ("discipline",),
        "nodes": ("knowledge_node",),
        "disciplines": ("discipline",),
        "scholar": ("person",),
        "work": ("work",),
    },
}


def test_active_admin_entity_inputs_have_exact_read_only_contracts():
    for step, fields in MAINTENANCE_ENTITY_FIELDS.items():
        assert {contract.field for contract in RESEARCH_CONTRACTS.for_step(step)} == set(fields)
        for field, entity_types in fields.items():
            contract = RESEARCH_CONTRACTS.get(step, field)
            assert contract.implementation == ResearchImplementation.ENTITY_DISCOVERY
            assert contract.entity_types == entity_types
            assert contract.allow_direct_use is True
            assert contract.allow_create_draft is False
            assert contract.mutation_policy == ResearchMutationPolicy.NEVER_DIRECT


def test_backoffice_reviewer_can_discover_maintenance_entities_without_work_context(api_client):
    reviewer = User.objects.create_user(
        username="maintenance-reviewer@example.org",
        email="maintenance-reviewer@example.org",
        role=User.Role.REVIEWER,
        password="Maintenance-Reviewer-Password-2026",
    )
    discipline = Discipline.objects.create(
        code="sociology-maintenance",
        name="社会学维护测试",
        slug="sociology-maintenance",
        editorial_status="published",
    )
    api_client.force_authenticate(reviewer)

    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "step": "maintenance_subdisciplines",
            "field": "discipline",
            "entity_type": "discipline",
            "query": "社会学维护测试",
            "include_external": False,
            "include_web": False,
        },
        format="json",
    )

    assert response.status_code == 200
    local = next(row for row in response.data["results"] if row.get("entity_id"))
    assert local["entity_id"] == str(discipline.id)
    assert local["available_actions"] == ["inspect", "apply_to_draft"]
    assert local["action_descriptors"][1]["method"] == "CLIENT"
    assert local["action_descriptors"][1]["label"] == "关联馆内实体"
    assert not EntityResolutionCandidate.objects.exists()


def test_reader_cannot_use_maintenance_entity_discovery(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "step": "maintenance_theory_nodes",
            "field": "primary_discipline",
            "entity_type": "discipline",
            "query": "社会学",
            "include_external": False,
            "include_web": False,
        },
        format="json",
    )
    assert response.status_code == 403


def test_maintenance_contract_rejects_cross_field_entity_type(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "step": "maintenance_theory_relations",
            "field": "source_node",
            "entity_type": "work",
            "query": "社会秩序",
            "include_external": False,
            "include_web": False,
        },
        format="json",
    )
    assert response.status_code == 400


def test_timeline_scholar_discovery_preserves_scholar_profile_foreign_key(api_client, admin_user):
    person = Person.objects.create(
        preferred_name="时间轴学者测试",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    profile = ScholarProfile.objects.create(
        person=person,
        slug="timeline-scholar-test",
        editorial_status="published",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "step": "maintenance_theory_timeline",
            "field": "scholar",
            "entity_type": "person",
            "query": "时间轴学者测试",
            "include_external": False,
            "include_web": False,
        },
        format="json",
    )

    assert response.status_code == 200
    local = next(row for row in response.data["results"] if row.get("entity_id"))
    assert local["entity_id"] == str(profile.id)
    assert local["metadata"]["person_id"] == str(person.id)
    assert local["entity_type"] == "person"


def test_maintenance_contract_cannot_drive_entity_decision_mutation(api_client, admin_user):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="只读维护合约测试",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.DRAFT,
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="maintenance-read-only.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )
    api_client.force_authenticate(admin_user)

    with patch("catalog.research_views.UniversalEntityDiscovery.discover") as discover:
        response = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            {
                "item_id": str(item.id),
                "work_id": str(work.id),
                "edition_id": str(edition.id),
                "step": "maintenance_theory_relations",
                "field": "source_node",
                "entity_type": "knowledge_node",
                "query": "符号互动论",
                "candidate_id": "web:maintenance:test",
                "action": "keep_unresolved",
            },
            format="json",
        )

    assert response.status_code == 400
    assert "只读实体发现" in response.data["detail"]
    discover.assert_not_called()
    assert not EntityResolutionCandidate.objects.exists()
