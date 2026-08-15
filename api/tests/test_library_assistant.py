import json
import re

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from catalog.models import Asset, Edition, PublicationState, Work
from reading.library_assistant import (
    LibraryAssistantUnavailable,
    build_messages,
    prepare_prompt_sources,
    stream_conversation_answer,
    validated_source_rows,
)
from reading.models import LibraryConversation, LibraryMessage, LibraryMessageSource
from reading.services import decrypt_private_text, encrypt_private_text


def create_source_work(index=1):
    work = Work.objects.create(document_type="book", title=f"问答来源 {index}")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"library-answer-source-{index}",
        publication_year=2000 + index,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/library-answer-{index}.pdf",
        sha256=f"{9000 + index:064x}",
        status=Asset.Status.READY,
        is_current=True,
        page_count=100,
    )
    return work, edition, asset


def source_row(work, edition, asset, *, index=1):
    return {
        "id": f"chunk-{index}",
        "asset_id": str(asset.id),
        "edition_id": str(edition.id),
        "work_id": str(work.id),
        "title": work.title,
        "authors": ["测试作者"],
        "page_index": 48,
        "printed_label": "32",
        "chapter_title": "权力与主体",
        "snippet": f"这是第 {index} 条真实馆藏摘录。",
    }


def stream_text(response):
    return b"".join(response.streaming_content).decode("utf-8")


def event_payloads(body, event):
    payloads = []
    blocks = body.split("\n\n")
    for block in blocks:
        lines = block.splitlines()
        if f"event: {event}" not in lines:
            continue
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if data:
            payloads.append(json.loads(data))
    return payloads


@pytest.mark.django_db
def test_conversations_are_private_to_the_authenticated_reader(api_client, reader_user):
    other = User.objects.create_user(
        username="other-reader",
        email="other-reader@example.org",
        password="Safe-password-2026",
    )
    own = LibraryConversation.objects.create(user=reader_user, title="我的会话")
    foreign = LibraryConversation.objects.create(user=other, title="别人的会话")
    api_client.force_authenticate(reader_user)

    listing = api_client.get("/api/reading/library-conversations/")
    foreign_detail = api_client.get(f"/api/reading/library-conversations/{foreign.id}/")

    assert listing.status_code == 200
    rows = listing.data.get("results", listing.data)
    assert [str(row["id"]) for row in rows] == [str(own.id)]
    assert foreign_detail.status_code == 404


@pytest.mark.django_db
def test_assist_off_skips_library_retrieval_and_encrypts_messages(
    api_client,
    reader_user,
    monkeypatch,
):
    api_client.force_authenticate(reader_user)
    conversation = LibraryConversation.objects.create(
        user=reader_user,
        assist_mode=LibraryConversation.AssistMode.OFF,
    )

    def fail_retrieval(*args, **kwargs):
        raise AssertionError("关闭馆藏辅助时不应执行检索")

    monkeypatch.setattr("reading.library_assistant.retrieve_library_sources", fail_retrieval)
    monkeypatch.setattr(
        "reading.library_assistant._provider_stream",
        lambda messages: iter(["这是一般解释，未使用馆藏资料。"]),
    )

    with override_settings(
        AI_PROVIDER="openai_compatible",
        AI_BASE_URL="http://localhost:11434",
        AI_ALLOWED_HOSTS=("localhost",),
        AI_METADATA_MODEL="local-chat",
        AI_LIBRARY_MODEL="local-chat",
    ):
        response = api_client.post(
            f"/api/reading/library-conversations/{conversation.id}/messages/stream/",
            {"question": "什么是社会结构？", "assist_mode": "off"},
            format="json",
        )
        body = stream_text(response)

    assert response.status_code == 200
    assert event_payloads(body, "done")[0]["status"] == "completed"
    messages = list(conversation.messages.order_by("created_at"))
    assert len(messages) == 2
    assert "社会结构".encode("utf-8") not in bytes(messages[0].body_ciphertext)
    assert decrypt_private_text(messages[0].body_ciphertext) == "什么是社会结构？"
    assert messages[1].retrieval_used is False
    export = api_client.get("/api/reading/export/")
    assert export.status_code == 200
    assert export.data["library_conversations"][0]["messages"][0]["content"] == "什么是社会结构？"


@pytest.mark.django_db
def test_strict_library_mode_returns_no_evidence_message_without_calling_model(
    api_client,
    reader_user,
    monkeypatch,
):
    api_client.force_authenticate(reader_user)
    conversation = LibraryConversation.objects.create(user=reader_user, assist_mode="on")
    monkeypatch.setattr(
        "reading.library_assistant.retrieve_library_sources",
        lambda *args, **kwargs: ([], {"engine": "keyword_fallback", "fallback_used": False}),
    )

    def fail_model(*args, **kwargs):
        raise AssertionError("严格馆藏模式无证据时不应调用模型")

    monkeypatch.setattr("reading.library_assistant._provider_stream", fail_model)
    response = api_client.post(
        f"/api/reading/library-conversations/{conversation.id}/messages/stream/",
        {"question": "馆藏里完全不存在的问题", "assist_mode": "on"},
        format="json",
    )
    body = stream_text(response)

    assert response.status_code == 200
    assert "没有找到足以回答这个问题的原文证据" in body
    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    assert answer.status == LibraryMessage.Status.COMPLETED
    assert answer.retrieval_used is False
    assert answer.sources.count() == 0


@pytest.mark.django_db
def test_stream_only_preserves_real_source_markers_and_progressively_exposes_sources(
    api_client,
    reader_user,
    monkeypatch,
):
    work1, edition1, asset1 = create_source_work(1)
    work2, edition2, asset2 = create_source_work(2)
    rows = [
        source_row(work1, edition1, asset1, index=1),
        source_row(work2, edition2, asset2, index=2),
    ]
    monkeypatch.setattr(
        "reading.library_assistant.retrieve_library_sources",
        lambda *args, **kwargs: (rows, {"engine": "hybrid", "fallback_used": False}),
    )
    monkeypatch.setattr(
        "reading.library_assistant._provider_stream",
        lambda messages: iter(["第一条证据 [S", "1]。错误编号 [S99] 和 [S1234] 不应保留。"]),
    )
    api_client.force_authenticate(reader_user)
    conversation = LibraryConversation.objects.create(user=reader_user)

    with override_settings(
        AI_PROVIDER="openai_compatible",
        AI_BASE_URL="http://localhost:11434",
        AI_ALLOWED_HOSTS=("localhost",),
        AI_METADATA_MODEL="local-chat",
        AI_LIBRARY_MODEL="local-chat",
    ):
        response = api_client.post(
            f"/api/reading/library-conversations/{conversation.id}/messages/stream/",
            {"question": "解释权力与主体", "assist_mode": "auto"},
            format="json",
        )
        body = stream_text(response)

    assert "[S1]" in body
    assert "[S99]" not in body
    assert "[S1234]" not in body
    meta = event_payloads(body, "meta")[0]
    assert meta["source_count"] == 2
    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    assert answer.sources.get(source_key="S1").cited is True
    assert answer.sources.get(source_key="S2").cited is False

    source_list = api_client.get(f"/api/reading/library-messages/{answer.id}/sources/")
    assert source_list.status_code == 200
    assert source_list.data["count"] == 1
    assert "quote" not in source_list.data["results"][0]

    first = answer.sources.get(source_key="S1")
    source_detail = api_client.get(
        f"/api/reading/library-messages/{answer.id}/sources/{first.id}/"
    )
    assert source_detail.status_code == 200
    assert source_detail.data["printed_label"] == "32"
    assert source_detail.data["page_index"] == 48
    assert source_detail.data["quote"] == "这是第 1 条真实馆藏摘录。"
    assert "page=48" in source_detail.data["reader_url"]


@pytest.mark.django_db
def test_withdrawn_source_is_not_revealed_as_available(api_client, reader_user):
    work, edition, asset = create_source_work(3)
    conversation = LibraryConversation.objects.create(user=reader_user)
    answer = LibraryMessage.objects.create(
        conversation=conversation,
        role=LibraryMessage.Role.ASSISTANT,
        status=LibraryMessage.Status.COMPLETED,
    )
    source = LibraryMessageSource.objects.create(
        message=answer,
        source_key="S1",
        ordinal=1,
        work=work,
        edition=edition,
        asset=asset,
        title_snapshot=work.title,
        page_index=10,
        quote_ciphertext=b"",
        cited=True,
    )
    edition.state = PublicationState.WITHDRAWN
    edition.save(update_fields=["state", "updated_at"])
    api_client.force_authenticate(reader_user)

    response = api_client.get(
        f"/api/reading/library-messages/{answer.id}/sources/{source.id}/"
    )

    assert response.status_code == 200
    assert response.data["available"] is False
    assert response.data["reader_url"] is None
    assert response.data["quote"] is None


@pytest.mark.django_db
def test_cross_linked_source_is_not_revealed(api_client, reader_user):
    work, edition, asset = create_source_work(31)
    other_work = Work.objects.create(document_type="book", title="错误关联作品")
    conversation = LibraryConversation.objects.create(user=reader_user)
    answer = LibraryMessage.objects.create(
        conversation=conversation,
        role=LibraryMessage.Role.ASSISTANT,
        status=LibraryMessage.Status.COMPLETED,
    )
    source = LibraryMessageSource.objects.create(
        message=answer,
        source_key="S1",
        ordinal=1,
        work=other_work,
        edition=edition,
        asset=asset,
        title_snapshot=work.title,
        quote_ciphertext=encrypt_private_text("不应泄露的错配摘录"),
        cited=True,
    )
    api_client.force_authenticate(reader_user)

    response = api_client.get(
        f"/api/reading/library-messages/{answer.id}/sources/{source.id}/"
    )

    assert response.status_code == 200
    assert response.data["available"] is False
    assert response.data["reader_url"] is None
    assert response.data["quote"] is None


@pytest.mark.django_db
def test_assistant_status_reports_disabled_without_exposing_secret(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    with override_settings(AI_PROVIDER="none", AI_API_KEY="top-secret"):
        response = api_client.get("/api/reading/library-assistant/status/")

    assert response.status_code == 200
    assert response.data["status"] == "disabled"
    assert "top-secret" not in str(response.data)


@pytest.mark.django_db
def test_disconnect_after_meta_cancels_answer_and_releases_conversation_slot(
    reader_user,
    monkeypatch,
):
    conversation = LibraryConversation.objects.create(user=reader_user, assist_mode="off")
    monkeypatch.setattr(
        "reading.library_assistant._provider_stream",
        lambda messages: iter(["不应在断开后继续生成"]),
    )
    first = stream_conversation_answer(
        conversation=conversation,
        question="第一个问题",
        assist_mode="off",
    )
    assert "event: meta" in next(first)

    second = stream_conversation_answer(
        conversation=conversation,
        question="并发问题",
        assist_mode="off",
    )
    busy = next(second)
    assert "conversation_busy" in busy
    with pytest.raises(StopIteration):
        next(second)

    first.close()
    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    answer.refresh_from_db()
    assert answer.status == LibraryMessage.Status.CANCELED
    assert answer.error_code == "client_disconnected"
    assert conversation.messages.count() == 2


@pytest.mark.django_db
def test_disconnect_preserves_cited_sources_and_removes_partial_marker(reader_user, monkeypatch):
    work, edition, asset = create_source_work(7)
    conversation = LibraryConversation.objects.create(user=reader_user)
    monkeypatch.setattr(
        "reading.library_assistant.retrieve_library_sources",
        lambda *args, **kwargs: (
            [source_row(work, edition, asset, index=1)],
            {"engine": "hybrid", "fallback_used": False},
        ),
    )
    monkeypatch.setattr(
        "reading.library_assistant._provider_stream",
        lambda messages: iter(["已取得证据 [S1]，末尾残片 [S"]),
    )
    stream = stream_conversation_answer(
        conversation=conversation,
        question="断流来源测试",
        assist_mode="auto",
    )
    assert "event: meta" in next(stream)
    assert "event: delta" in next(stream)
    stream.close()

    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    body = decrypt_private_text(answer.body_ciphertext)
    assert answer.status == LibraryMessage.Status.CANCELED
    assert "[S1]" in body
    assert not body.endswith("[S")
    assert answer.sources.get(source_key="S1").cited is True


@pytest.mark.django_db
def test_cancel_requested_after_last_delta_wins_over_completion(reader_user, monkeypatch):
    conversation = LibraryConversation.objects.create(user=reader_user, assist_mode="off")

    def provider(messages):
        yield "已经生成的部分"
        LibraryMessage.objects.filter(
            conversation=conversation,
            role=LibraryMessage.Role.ASSISTANT,
        ).update(cancel_requested_at=timezone.now())

    monkeypatch.setattr("reading.library_assistant._provider_stream", provider)
    body = "".join(
        stream_conversation_answer(
            conversation=conversation,
            question="停止边界测试",
            assist_mode="off",
        )
    )

    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    assert answer.status == LibraryMessage.Status.CANCELED
    assert event_payloads(body, "done")[0]["status"] == "canceled"


@pytest.mark.django_db
def test_provider_failure_finalizes_partial_answer_and_real_citation(reader_user, monkeypatch):
    work, edition, asset = create_source_work(32)
    conversation = LibraryConversation.objects.create(user=reader_user)
    monkeypatch.setattr(
        "reading.library_assistant.retrieve_library_sources",
        lambda *args, **kwargs: (
            [source_row(work, edition, asset, index=1)],
            {"engine": "hybrid", "fallback_used": False},
        ),
    )

    def provider(messages):
        yield "已取得证据 [S1]。"
        raise LibraryAssistantUnavailable("private endpoint must not reach reader")

    monkeypatch.setattr("reading.library_assistant._provider_stream", provider)
    body = "".join(
        stream_conversation_answer(
            conversation=conversation,
            question="失败收尾测试",
            assist_mode="auto",
        )
    )

    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    assert answer.status == LibraryMessage.Status.FAILED
    assert decrypt_private_text(answer.body_ciphertext) == "已取得证据 [S1]。"
    assert answer.sources.get(source_key="S1").cited is True
    assert "private endpoint" not in body


@pytest.mark.django_db
def test_reader_export_excludes_uncited_retrieval_candidates(api_client, reader_user):
    work1, edition1, asset1 = create_source_work(33)
    work2, edition2, asset2 = create_source_work(34)
    conversation = LibraryConversation.objects.create(user=reader_user)
    answer = LibraryMessage.objects.create(
        conversation=conversation,
        role=LibraryMessage.Role.ASSISTANT,
        status=LibraryMessage.Status.COMPLETED,
    )
    for ordinal, (work, edition, asset, cited) in enumerate(
        [(work1, edition1, asset1, True), (work2, edition2, asset2, False)],
        start=1,
    ):
        LibraryMessageSource.objects.create(
            message=answer,
            source_key=f"S{ordinal}",
            ordinal=ordinal,
            work=work,
            edition=edition,
            asset=asset,
            title_snapshot=work.title,
            quote_ciphertext=encrypt_private_text(f"摘录 {ordinal}"),
            cited=cited,
        )
    api_client.force_authenticate(reader_user)

    response = api_client.get("/api/reading/export/")

    exported = response.data["library_conversations"][0]["messages"][0]["sources"]
    assert [row["source_key"] for row in exported] == ["S1"]


@pytest.mark.django_db
def test_history_citations_are_removed_and_prompt_respects_input_budget(reader_user):
    conversation = LibraryConversation.objects.create(user=reader_user)
    LibraryMessage.objects.create(
        conversation=conversation,
        role=LibraryMessage.Role.ASSISTANT,
        status=LibraryMessage.Status.COMPLETED,
        body_ciphertext=encrypt_private_text("上一轮回答使用旧来源 [S1]。" * 120),
    )
    sources = [
        {
            "source_key": "S1",
            "title": "本轮来源",
            "authors": ["作者"],
            "page_index": 12,
            "snippet": "本轮真实原文。" * 300,
        }
    ]

    with override_settings(AI_MAX_INPUT_CHARS=1000):
        messages = build_messages(
            conversation=conversation,
            question="请解释这个问题" * 300,
            sources=sources,
            assist_mode="auto",
        )

    assert sum(len(message["content"]) for message in messages) <= 1000
    historical = [message["content"] for message in messages[1:-1]]
    assert all("[S1]" not in content for content in historical)
    assert "[S1]" in messages[-1]["content"]


@pytest.mark.django_db
def test_only_sources_that_fit_the_prompt_remain_citable(reader_user):
    conversation = LibraryConversation.objects.create(user=reader_user)
    sources = [
        {
            "source_key": f"S{index}",
            "title": f"来源 {index}",
            "authors": ["作者"],
            "page_index": index,
            "snippet": (f"第 {index} 条摘录包含不可信编号 [S8]。" * 180),
        }
        for index in range(1, 9)
    ]

    with override_settings(AI_MAX_INPUT_CHARS=1000):
        included, messages = prepare_prompt_sources(
            conversation=conversation,
            question="请比较这些来源" * 120,
            sources=sources,
            assist_mode="auto",
        )

    prompt_keys = set(
        match.group(1)
        for match in re.finditer(r"\[(S\d+)\]", messages[-1]["content"])
    )
    assert 0 < len(included) < len(sources)
    assert {source["source_key"] for source in included} == prompt_keys
    assert "[S8]" not in messages[-1]["content"]
    assert "[摘录编号已移除]" in messages[-1]["content"]


@pytest.mark.django_db
def test_stale_or_non_reader_asset_is_filtered_before_prompt():
    work = Work.objects.create(document_type="book", title="原始文件不能直接作为问答来源")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="original-only-source",
        is_primary=True,
    )
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="archive/original-only.pdf",
        sha256=f"{9901:064x}",
        status=Asset.Status.READY,
        is_current=True,
    )

    assert validated_source_rows([source_row(work, edition, original)]) == []


@pytest.mark.django_db
def test_output_is_bounded_and_reader_health_hides_internal_reason(
    api_client,
    reader_user,
    monkeypatch,
    caplog,
):
    api_client.force_authenticate(reader_user)
    conversation = LibraryConversation.objects.create(user=reader_user, assist_mode="off")
    monkeypatch.setattr(
        "reading.library_assistant._provider_stream",
        lambda messages: iter(["很长的模型输出" * 100]),
    )
    with override_settings(
        AI_PROVIDER="openai_compatible",
        AI_BASE_URL="http://localhost:11434",
        AI_ALLOWED_HOSTS=("localhost",),
        AI_METADATA_MODEL="local-chat",
        AI_LIBRARY_MODEL="local-chat",
        AI_LIBRARY_MAX_OUTPUT_CHARS=20,
    ):
        response = api_client.post(
            f"/api/reading/library-conversations/{conversation.id}/messages/stream/",
            {"question": "输出限制测试", "assist_mode": "off"},
            format="json",
        )
        stream_text(response)

    answer = conversation.messages.get(role=LibraryMessage.Role.ASSISTANT)
    assert len(decrypt_private_text(answer.body_ciphertext)) <= 20

    monkeypatch.setattr(
        "ingestion.services.ai_client.AIClient.health_check",
        lambda self: {
            "configured": True,
            "available": False,
            "status": "down",
            "reason": "failed at http://private-model.internal/v1/models?key=secret",
        },
    )
    with override_settings(
        AI_PROVIDER="openai_compatible",
        AI_BASE_URL="http://localhost:11434",
        AI_ALLOWED_HOSTS=("localhost",),
        AI_METADATA_MODEL="local-chat",
        AI_LIBRARY_MODEL="local-chat",
    ):
        health = api_client.get("/api/reading/library-assistant/status/")

    assert health.status_code == 200
    assert health.data["status"] == "down"
    assert "private-model" not in str(health.data)
    assert "secret" not in str(health.data)
    assert "private-model" not in caplog.text
    assert "secret" not in caplog.text
