"""Execution/coverage contracts, not a model-quality or hardware benchmark."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services import intelligence as runner, knowledge_compilation_plan as plan
from catalog.services.intelligence_provider import fits_input, SYSTEM, TASK
from catalog.services.knowledge_compilation import run_configuration
from catalog.services.knowledge_sources import digest
from ingestion.services.ai_client import AIInvalidOutput, AIResult, structured_messages
from tests.test_knowledge_core import source


def config():
    return run_configuration(SimpleNamespace(execution_mode="agent"))


@pytest.mark.django_db
def test_ordered_chapter_batches_preserve_all_windows_and_reuse_unaffected_chapters(source, admin_user, monkeypatch):
    run = m.CurationRun.objects.create(work=source.asset.edition.work, edition=source.asset.edition,
        document_revision=source, created_by=admin_user, request_id=uuid4(), plan_version=2,
        coverage={"window_groups":[{"node_id":str(i//3), "kind":"chapter", "title":"同名章"} for i in range(9)]})
    analyses = []
    for i in range(9):
        output = {"summary":f"论证{i}", "questions":[], "entities":[],
            "assertions":[{"text":f"限定{i}", "evidence":[{"stance":"opposes", "exact":f"原文{i}"}]}]}
        analyses.append(SimpleNamespace(unit=f"window:{i}", output=output, output_hash=digest(output)))
    calls = []
    def model(cfg, prompt, text, schema):
        data = json.loads(text)
        assert fits_input(cfg, prompt, data, schema)
        calls.append(data)
        output = {"summary":digest(data), "development":data["source_units"], "limitations":["fixture"],
            "covered_units":data["source_units"]}
        return AIResult(output, cfg.provider, cfg.model, runner.PROMPT_VERSION, 1, 1, {})
    monkeypatch.setattr(runner, "map_analysis", model)
    result = plan.synthesize(run, analyses, config(), None)
    assert result.unit == "fold:8" and len(calls) == 4  # 3 independent chapters + 1 ordered fold
    assert [s["unit"] for d in calls[:3] for s in d["sources_in_order"]] == [a.unit for a in analyses]
    assert [d["chapter"]["node_id"] for d in calls[:3]] == ["0", "1", "2"]
    assert all(s["output"] == analyses[s["window"]].output for d in calls[:3] for s in d["sources_in_order"])
    assert calls[-1]["source_units"] == ["chapter:0:2", "chapter:3:5", "chapter:6:8"]
    calls.clear(); run._artifact_cache = {}
    assert plan.synthesize(run, analyses, config(), None).pk == result.pk
    assert calls == []
    # A changed first chapter invalidates its own synthesis and the book fold,
    # never the independent later chapter products.
    analyses[0].output["summary"] = "修订后的论证"
    analyses[0].output_hash = digest(analyses[0].output)
    run._artifact_cache = {}
    updated = plan.synthesize(run, analyses, config(), None)
    assert len(calls) == 2 and calls[0]["chapter"]["node_id"] == "0"
    assert updated.output_hash != result.output_hash


def test_synthesis_rejects_missing_reordered_coverage_and_oversized_whole_output(monkeypatch):
    data = {"source_units":["window:0", "window:1"]}
    for units in (["window:0"], ["window:1", "window:0"], ["window:0", "window:0"]):
        with pytest.raises(ValidationError, match="覆盖"):
            plan.validate_synthesis({"covered_units":units}, data)
    run = SimpleNamespace(coverage={"window_groups":[{"node_id":"chapter"}]})
    output = {"summary":"超长😀"*20000}
    monkeypatch.setattr(runner, "_model_artifact", lambda *a, **k:pytest.fail("Oversized input reached model"))
    with pytest.raises(ValidationError, match="预算"):
        plan.synthesize(run, [SimpleNamespace(unit="window:0", output=output, output_hash=digest(output))], config(), None)


def test_wiki_packets_use_transport_budget_and_account_for_every_claim_and_block():
    cfg = config()
    cfg.max_input_chars = 9000
    base = {"destination":{"title":"作品"}, "assertions":[], "argument_context":{"summary":"全书限定"}}
    assertions = [{"id":str(i), "text":"支持、反对与适用条件😀"*100} for i in range(12)]
    contexts = [{"block":{"id":str(i), "type":"analysis", "text":"人工正文"*100}} for i in range(10)]
    packets = list(plan.wiki_inputs(base, assertions, contexts, cfg))
    assert len(packets) > 1
    assert [a for packet in packets for a in packet["assertions"]] == assertions
    for packet in packets:
        assert fits_input(cfg, plan.WIKI_PROMPT, packet, plan.wiki_schema())
        read = {c["block"]["id"] for c in packet["existing_blocks"]}
        omitted = set(packet["omitted_context_blocks"])
        assert not read & omitted and read | omitted == {str(i) for i in range(10)}
        plan.validate_wiki_batch({"patches":[], "covered_assertion_ids":[a["id"] for a in packet["assertions"]]}, packet)


@pytest.mark.django_db
def test_multiple_wiki_patches_share_one_call_and_keep_protection_and_source_dependencies(source, admin_user, monkeypatch):
    from catalog.services.editorial_revision import create_editorial_revision
    page = m.KnowledgePage.objects.create(work=source.asset.edition.work, slug="batch", title="作品")
    entity = m.Entity.objects.create(kind="concept", label="已有人工作品概念")
    block = {"id":str(uuid4()), "type":"analysis", "text":"人工正文", "origin":"human", "human_edited":True,
        "references":[{"type":"entity", "id":str(entity.pk)}]}
    create_editorial_revision(target_type="knowledge_page", target_id=page.pk, patch={"body_blocks":[block]},
        actor=admin_user, idempotency_key="batch-base")
    run = m.CurationRun.objects.create(work=source.asset.edition.work, edition=source.asset.edition,
        document_revision=source, created_by=admin_user, request_id=uuid4(), plan_version=2)
    assertions = [{"id":str(uuid4()), "kind":"assertion", "payload":{"text":f"有来源陈述{i}", "evidence":[]},
        "dependencies":[]} for i in range(4)]
    calls = []
    def model(run, stage, unit, data, *args, **kwargs):
        calls.append(data)
        refs = [a["id"] for a in data["assertions"]]
        output = {"covered_assertion_ids":refs, "patches":[
            {"operation":"add", "text":"相关论证集中说明", "reason":"新来源", "assertion_ids":refs[:2]},
            {"operation":"replace", "block_id":block["id"], "text":"新增限定", "reason":"相反证据", "assertion_ids":refs[2:]}]}
        kwargs["validate"](output)
        from catalog.services.intelligence_remote import validate_result
        validate_result(SimpleNamespace(stage=6, input_manifest=data), output)
        for invalid in ({**output, "covered_assertion_ids":refs[:1]},
                {**output, "patches":[output["patches"][1], output["patches"][1]]},
                {**output, "patches":[{**output["patches"][0], "assertion_ids":["foreign"]}]}):
            with pytest.raises(ValidationError):
                validate_result(SimpleNamespace(stage=6, input_manifest=data), invalid)
        return SimpleNamespace(pk=uuid4(), output=output)
    monkeypatch.setattr(runner, "_model_artifact", model)
    patches = runner.compile_wiki(run, assertions, config(), None)
    assert len(calls) == 1 and len(patches) == 2
    assert patches[1]["payload"]["human_protected"]
    from catalog.services.knowledge_core import page_content
    assert patches[1]["payload"]["base_hash"] == digest(page_content(page)[0][0])
    assert patches[0]["dependencies"] == sorted(a["id"] for a in assertions[:2])
    assert len({p["payload"]["block_id"] for p in patches}) == 2
    assert m.KnowledgePage.objects.get(pk=page.pk).body_blocks == []  # only suggestions, no canonical writes


def test_budget_matches_transport_including_unicode_schema_and_output(settings):
    cfg = config()
    data = {"text":"😀中文"*100}
    prompt, schema = "完整阅读", plan.summary_schema()
    assert fits_input(cfg, prompt, data, schema)
    settings.INTELLIGENCE_CONTEXT_TOKENS = cfg.max_output_tokens + 50
    assert not fits_input(cfg, prompt, data, schema)
    with pytest.raises(AIInvalidOutput):
        structured_messages(config=cfg, task=TASK, system_prompt=SYSTEM,
            document_text=prompt+"\n<source_data>"+json.dumps(data, ensure_ascii=False)+"</source_data>", schema=schema, strict=True)


@pytest.mark.django_db
def test_new_runs_pin_new_plan_and_old_runs_keep_legacy(source, admin_user, monkeypatch):
    monkeypatch.setattr(runner, "schedule", lambda run:None)
    old = m.CurationRun.objects.create(work=source.asset.edition.work, edition=source.asset.edition,
        document_revision=source, created_by=admin_user, request_id=uuid4())
    new = runner.create_run(source, admin_user, request_id=uuid4(), execution_mode="agent")
    old.refresh_from_db()
    assert old.plan_version == 1 and new.plan_version == 2
    assert runner.create_run(source, admin_user, request_id=new.request_id, execution_mode="agent").pk == new.pk


@pytest.mark.django_db
def test_runtime_report_is_read_only_and_does_not_call_unmeasured_agent_time_zero(source, admin_user):
    from io import StringIO
    from django.core.management import call_command
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    run = m.CurationRun.objects.create(work=source.asset.edition.work, edition=source.asset.edition,
        document_revision=source, created_by=admin_user, request_id=uuid4(), plan_version=2)
    for i, usage in enumerate([{"model_calls":0,"agent_responses":1},
            {"model_calls":0,"reused_from_artifact_id":"previous"}, {"model_calls":None}]):
        m.CurationArtifact.objects.create(run=run, stage=2, unit=f"window:{i}", usage=usage)
    out = StringIO()
    with CaptureQueriesContext(connection) as queries:
        call_command("inspect_knowledge_runtime", run_id=run.pk, stdout=out)
    report = json.loads(out.getvalue())
    assert report["status"] == "schema_current" and report["pending_migrations"] == []
    stage = report["run"]["metrics"]["stages"][0]
    assert stage["known_model_calls"] == 0 and stage["unknown_model_call_units"] == 1
    assert stage["agent_responses"] == 1 and stage["reused_units"] == 1 and stage["unmeasured_units"] == 2
    assert not any(q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE", "CREATE", "ALTER")) for q in queries)
    assert all(key not in out.getvalue().lower() for key in ("api_key", "password", "base_url", "input_manifest"))


def test_worker_timeout_diagnostics_do_not_inspect_request_or_local_variables(monkeypatch):
    from config import gunicorn
    import faulthandler
    calls = []
    monkeypatch.setattr(faulthandler, "dump_traceback", lambda **kwargs:calls.append(kwargs))
    gunicorn.worker_abort(None)
    assert calls == [{"all_threads":True}]
