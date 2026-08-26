import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    ClaimBenchmarkJudgment,
    DocumentRevision,
    DocumentType,
    Edition,
    EvidenceSpan,
    Page,
    SearchEvaluationQuery,
    SearchEvaluationSet,
    Work,
)
from catalog.services.claim_benchmark import claim_benchmark_gold_summary
from catalog.services.processing_center_diagnostics import processing_center_diagnostics


pytestmark = pytest.mark.django_db


def _gold_fixture(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="Gold Evidence 样本")
    edition = Edition.objects.create(work=work, version_label="第一版")
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="archive/gold-evidence.pdf",
        sha256="a" * 64,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    page = Page.objects.create(
        asset=asset,
        index=7,
        printed_label="5",
        text="国家分类会改变它试图描述的社会现实。",
        normalized_text="国家分类会改变它试图描述的社会现实。",
        text_source=Page.TextSource.EMBEDDED,
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        source_checksum=asset.sha256,
        text_checksum="b" * 64,
        is_active=True,
    )
    span = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        page_number=page.index,
        printed_page_label=page.printed_label,
        original_text=page.text,
        normalized_text=page.normalized_text,
        content_hash="c" * 64,
        quality=0.95,
    )
    evaluation_set = SearchEvaluationSet.objects.create(
        name="观点检索人工 Gold",
        language="zh-CN",
        created_by=admin_user,
    )
    query = SearchEvaluationQuery.objects.create(
        evaluation_set=evaluation_set,
        query_text="国家分类是否改变社会现实？",
        normalized_query="国家分类是否改变社会现实",
    )
    return evaluation_set, query, span


def test_admin_can_create_update_list_and_delete_real_gold_judgment(
    api_client,
    admin_user,
):
    evaluation_set, query, span = _gold_fixture(admin_user)
    endpoint = "/api/catalog/admin/claim-benchmark/judgments/"
    api_client.force_authenticate(admin_user)

    created = api_client.post(
        endpoint,
        {
            "query_id": str(query.id),
            "evidence_span_id": str(span.id),
            "expected_relation": "support",
            "expected_attribution": "author_claim",
            "relevance": 3,
            "locator_verified": True,
            "notes": "管理员核对 PDF 第 7 页。",
        },
        format="json",
    )

    assert created.status_code == 201
    assert created.data["created"] is True
    assert created.data["judgment"]["evidence"]["locator"] == {
        "page": 7,
        "printed_page_label": "5",
    }
    row = ClaimBenchmarkJudgment.objects.get()
    assert row.created_by == admin_user
    assert row.work_id == span.document_revision.asset.edition.work_id
    assert row.document_revision_id == span.document_revision_id

    updated = api_client.post(
        endpoint,
        {
            "query_id": str(query.id),
            "evidence_span_id": str(span.id),
            "expected_relation": "qualify",
            "relevance": 2,
            "locator_verified": True,
            "notes": "复核后改为限定。",
        },
        format="json",
    )
    listed = api_client.get(endpoint, {"evaluation_set": str(evaluation_set.id)})

    assert updated.status_code == 200
    assert updated.data["created"] is False
    assert ClaimBenchmarkJudgment.objects.count() == 1
    assert listed.status_code == 200
    assert listed.data["count"] == 1
    assert listed.data["results"][0]["expected_relation"] == "qualify"
    assert listed.data["summary"]["ranking"] == {
        "default": "semantic_v2_baseline",
        "claim_mode": "shadow",
        "changed": False,
    }

    deleted = api_client.delete(f"{endpoint}{row.id}/")
    assert deleted.status_code == 204
    assert not ClaimBenchmarkJudgment.objects.exists()


def test_gold_api_is_admin_only_and_rejects_stale_evidence(
    api_client,
    admin_user,
):
    _evaluation_set, query, span = _gold_fixture(admin_user)
    endpoint = "/api/catalog/admin/claim-benchmark/judgments/"
    editor = User.objects.create_user(
        username="gold-editor@example.org",
        email="gold-editor@example.org",
        role=User.Role.EDITOR,
        password="Editor-Secure-Password-2026",
    )
    api_client.force_authenticate(editor)
    assert api_client.get(endpoint).status_code == 403

    span.is_stale = True
    span.stale_reason = "selective OCR produced a newer span"
    span.save(update_fields=["is_stale", "stale_reason", "updated_at"])
    api_client.force_authenticate(admin_user)
    rejected = api_client.post(
        endpoint,
        {
            "query_id": str(query.id),
            "evidence_span_id": str(span.id),
            "expected_relation": "support",
            "relevance": 3,
            "locator_verified": True,
        },
        format="json",
    )

    assert rejected.status_code == 400
    assert "EvidenceSpan" in str(rejected.data)
    assert not ClaimBenchmarkJudgment.objects.exists()


def test_processing_center_reports_gold_readiness_without_changing_baseline(admin_user):
    evaluation_set, first_query, span = _gold_fixture(admin_user)
    relations = ["direct", "support", "oppose", "qualify"]
    queries = [first_query]
    for index in range(1, 10):
        queries.append(
            SearchEvaluationQuery.objects.create(
                evaluation_set=evaluation_set,
                query_text=f"人工命题 {index}",
                normalized_query=f"人工命题 {index}",
                order=index,
            )
        )
    for index, query in enumerate(queries):
        ClaimBenchmarkJudgment.objects.create(
            query=query,
            evidence_span=span,
            expected_relation=relations[index % len(relations)],
            expected_attribution=ClaimBenchmarkJudgment.Attribution.AUTHOR_CLAIM,
            relevance=3,
            locator_verified=True,
            created_by=admin_user,
        )

    summary = claim_benchmark_gold_summary()
    diagnostics = processing_center_diagnostics()

    assert summary["gold_query_count"] == 10
    assert summary["benchmark_ready"] is True
    assert summary["stance_coverage"]["missing_required"] == []
    assert summary["ranking"]["default"] == "semantic_v2_baseline"
    assert summary["ranking"]["claim_mode"] == "shadow"
    assert diagnostics["summary"]["claim_gold_query_count"] == 10
    assert diagnostics["summary"]["claim_benchmark_ready"] is True
    assert diagnostics["claim_benchmark"] == summary


def test_gold_summary_explains_missing_human_labels():
    summary = claim_benchmark_gold_summary()

    assert summary["gold_query_count"] == 0
    assert summary["benchmark_ready"] is False
    assert summary["stance_coverage"]["counts"] == {
        "direct": 0,
        "support": 0,
        "oppose": 0,
        "qualify": 0,
        "critique": 0,
        "extend": 0,
        "reframe": 0,
    }
    assert {row["code"] for row in summary["blockers"]} == {
        "insufficient_gold_queries",
        "missing_required_stance_coverage",
    }
    assert summary["ranking"]["changed"] is False
