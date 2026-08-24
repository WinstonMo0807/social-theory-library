from __future__ import annotations

from io import StringIO
import json

import pytest
from django.core.management import call_command

from accounts.models import User
from catalog.models import (
    DebateCandidate,
    IntelligenceFeedback,
    KnowledgeNode,
    KnowledgePublicationStatus,
    PromptRegistryEntry,
    ReadingPathCandidate,
    ResearchTaskProfile,
    Work,
)
from catalog.services.claim_benchmark import (
    aggregate_claim_benchmark,
    score_claim_query,
    viewpoint_ranking_gate,
)
from catalog.services.research.candidate_adoption import (
    decide_debate_candidate,
    decide_reading_path_candidate,
)
from catalog.services.research.evidence_pack import create_evidence_pack
from catalog.services.research.prompt_registry import (
    activate_prompt_revision,
    create_prompt_revision,
)
from catalog.services.research.task_profiles import BUILTIN_TASK_PROFILES, builtin_task_profile


def _user(*, role=User.Role.EDITOR, superuser=False, suffix="editor"):
    return User.objects.create_user(
        username=f"v3-{suffix}@example.test",
        email=f"v3-{suffix}@example.test",
        password="V3-Research-2026",
        role=role,
        is_staff=True,
        is_superuser=superuser,
    )


@pytest.mark.django_db
def test_intelligence_registry_seeds_all_contracts_and_evidence_bound_prompts():
    call_command("seed_v3_intelligence_registry")

    assert set(ResearchTaskProfile.objects.filter(is_active=True).values_list("key", flat=True)) == set(
        BUILTIN_TASK_PROFILES
    )
    assert PromptRegistryEntry.objects.filter(status=PromptRegistryEntry.Status.ACTIVE).count() == len(
        BUILTIN_TASK_PROFILES
    )
    prompt = PromptRegistryEntry.objects.get(key="research.claim_stance", status="active")
    assert "EvidencePack" in prompt.content
    assert "SearXNG snippet" in prompt.content
    assert prompt.provider_guidance["canonical_write"] == "forbidden"


@pytest.mark.django_db
def test_prompt_registry_is_owner_only_and_activation_retires_previous_revision(settings):
    editor = _user(suffix="prompt-editor")
    superadmin = _user(superuser=True, suffix="prompt-superadmin")
    settings.LIBRARY_OWNER_EMAIL = superadmin.email
    with pytest.raises(PermissionError):
        create_prompt_revision(
            key="research.claim_stance",
            capability="claim_stance",
            content="editor attempt",
            output_schema={},
            actor=editor,
        )
    first = create_prompt_revision(
        key="research.claim_stance",
        capability="claim_stance",
        content="first",
        output_schema={"type": "object"},
        actor=superadmin,
    )
    activate_prompt_revision(prompt=first, actor=superadmin)
    second = create_prompt_revision(
        key="research.claim_stance",
        capability="claim_stance",
        content="second",
        output_schema={"type": "object"},
        actor=superadmin,
    )
    activate_prompt_revision(prompt=second, actor=superadmin)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == PromptRegistryEntry.Status.RETIRED
    assert second.status == PromptRegistryEntry.Status.ACTIVE


@pytest.mark.django_db
def test_prompt_registry_admin_api_creates_and_activates_immutable_revision(
    api_client,
    admin_user,
    superadmin_user,
):
    api_client.force_authenticate(admin_user)
    denied = api_client.get("/api/catalog/admin/prompt-registry/")
    assert denied.status_code == 403

    api_client.force_authenticate(superadmin_user)
    created = api_client.post(
        "/api/catalog/admin/prompt-registry/",
        {
            "action": "create_revision",
            "key": "research.claim_stance",
            "capability": "claim_stance",
            "task_profile_key": "claim_stance",
            "content": "只根据 EvidencePack 判断立场。",
            "output_schema": {"type": "object"},
            "provider_guidance": {"temperature": 0},
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["version"] == 1
    assert created.data["status"] == "draft"

    activated = api_client.post(
        "/api/catalog/admin/prompt-registry/",
        {"action": "activate", "prompt_id": created.data["id"]},
        format="json",
    )
    assert activated.status_code == 200
    assert activated.data["status"] == "active"

    inventory = api_client.get(
        "/api/catalog/admin/prompt-registry/?key=research.claim_stance"
    )
    assert inventory.status_code == 200
    assert inventory.data["immutable_revisions"] is True
    assert inventory.data["activation_requires_superadmin"] is True
    assert inventory.data["results"][0]["content_hash"]


@pytest.mark.django_db
def test_evidence_pack_is_locator_bound_and_content_idempotent():
    profile = builtin_task_profile("claim_extraction").payload()
    envelope = {
        "kind": "collection_text",
        "source": {"document_revision_id": "revision-1", "work_id": "work-1"},
        "text": "制度约束会改变行动者的策略。",
        "locator": {"page": 12},
        "quality": {"score": 0.9},
        "provenance": {"parser_version": "test"},
        "reader_url": "/reader/asset-1?page=12",
        "pdf_url": "/api/catalog/assets/asset-1/manifest/",
    }
    first = create_evidence_pack(
        task_profile=profile,
        envelopes=[envelope],
        retrieval_snapshot={"query": "制度约束"},
    )
    second = create_evidence_pack(
        task_profile=profile,
        envelopes=[envelope],
        retrieval_snapshot={"query": "制度约束"},
    )
    assert first.pk == second.pk
    assert first.document_revisions == ["revision-1"]

    broken = {**envelope, "locator": {}}
    with pytest.raises(ValueError, match="页码"):
        create_evidence_pack(
            task_profile=profile,
            envelopes=[broken],
            retrieval_snapshot={},
        )


@pytest.mark.django_db
def test_candidate_adoption_creates_complete_drafts_and_records_human_feedback():
    editor = _user(suffix="candidate-editor")
    work = Work.objects.create(title="国家与社会", document_type="book", language="zh-CN")
    debate = DebateCandidate.objects.create(
        title="国家能力是否必然促进发展",
        canonical_question="国家能力是否必然促进经济与社会发展？",
        summary="候选摘要",
    )
    decided_debate = decide_debate_candidate(
        candidate=debate,
        decision=IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT,
        actor=editor,
        summary="经编辑确认的摘要",
    )
    node = decided_debate.suggested_node
    assert node.node_type == KnowledgeNode.NodeType.DEBATE
    assert node.status == KnowledgePublicationStatus.DRAFT
    assert node.core_questions == ["国家能力是否必然促进经济与社会发展？"]

    reading = ReadingPathCandidate.objects.create(
        title="国家理论入门",
        target_audience="初学者",
        learning_goal="理解国家与社会关系",
        stages=[
            {
                "name": "问题起点",
                "goal": "建立基本问题",
                "works": [
                    {
                        "work_id": str(work.id),
                        "reason": "从基本概念进入",
                        "prerequisite": "无",
                    }
                ],
            }
        ],
    )
    decided_path = decide_reading_path_candidate(
        candidate=reading,
        decision=IntelligenceFeedback.Decision.ACCEPT,
        actor=editor,
    )
    path = decided_path.adopted_reading_path
    assert path.status == KnowledgePublicationStatus.DRAFT
    assert path.learning_goal == "理解国家与社会关系"
    assert path.introduction == path.learning_goal
    assert path.stages.count() == 1
    adopted_item = path.items.get()
    assert adopted_item.work_id == work.id
    assert adopted_item.prerequisite == "无"
    assert adopted_item.editorial_note == adopted_item.prerequisite
    assert IntelligenceFeedback.objects.filter(reviewed_by=editor).count() == 2


def test_claim_benchmark_scores_opposition_qualification_and_blocks_weak_shadow_candidate():
    gold = [
        {
            "evidence_span_id": "support-1",
            "work_id": "work-a",
            "relation": "support",
            "attribution": "author_claim",
            "relevance": 3,
            "locator_verified": True,
            "page": 10,
        },
        {
            "evidence_span_id": "oppose-1",
            "work_id": "work-b",
            "relation": "oppose",
            "attribution": "author_claim",
            "relevance": 3,
            "locator_verified": True,
            "page": 20,
        },
        {
            "evidence_span_id": "qualify-1",
            "work_id": "work-c",
            "relation": "qualify",
            "attribution": "reported_claim",
            "relevance": 2,
            "locator_verified": True,
            "page": 30,
        },
    ]
    predictions = [
        {**gold[0], "attribution": "author_claim"},
        {**gold[1], "relation": "oppose"},
        {**gold[2], "relation": "support"},
        {"evidence_span_id": "wrong", "work_id": "work-z", "relation": "support", "page": 1},
    ]
    scored = score_claim_query(gold=gold, predictions=predictions)
    aggregate = aggregate_claim_benchmark([scored])

    assert scored.opposing_evidence_recall == 1
    assert scored.qualification_recall == 0
    assert scored.claim_stance_accuracy == pytest.approx(2 / 3)
    assert scored.wrong_work_rate == 0.25
    gate = viewpoint_ranking_gate(baseline=aggregate, candidate=aggregate)
    assert gate["passed"] is False
    assert {row["metric"] for row in gate["blockers"]} >= {"query_count", "qualification_recall"}


@pytest.mark.django_db
def test_claim_benchmark_command_keeps_default_ranking_when_gold_is_missing():
    output = StringIO()

    call_command("benchmark_claim_viewpoint_v3", stdout=output)

    report = json.loads(output.getvalue())
    assert report["gold_query_count"] == 0
    assert report["gate"]["passed"] is False
    assert report["default_ranking_changed"] is False
