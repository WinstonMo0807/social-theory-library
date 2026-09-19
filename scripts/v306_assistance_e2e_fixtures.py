"""Synthetic candidates and dated observations, never real external results."""
from datetime import timedelta
from hashlib import sha256


def seed_assistance(owner):
    from django.conf import settings
    from django.utils import timezone
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3" or "stl-v305-e2e-" not in settings.DATABASES["default"]["NAME"]:
        raise RuntimeError("Assistance fixtures require the disposable E2E database")
    from catalog.models import Contribution, EnrichmentCandidate, EnrichmentEvidence, Person, PublisherAuthority, ScholarProfile, HealthCheckRun
    from catalog.services.field_enrichment.policies import FIELD_POLICIES
    from catalog.services.field_enrichment.targets import current_field_value
    from catalog.services.system_health import HEALTH_CHECKS
    from catalog.services.cataloging_sessions import open_cataloging_session
    from ingestion.models import FieldLock, MetadataCandidate

    person = Person.objects.create(id="30600000-0000-4000-8000-000000000610", preferred_name="V306建议复核学者", authority_status="verified")
    ScholarProfile.objects.create(id="30600000-0000-4000-8000-000000000611", person=person, slug="v306-assistance", editorial_status="published", short_description="隔离候选操作测试")
    policy = FIELD_POLICIES.get("person", "affiliation")
    for index, name in enumerate(("待采用测试单位", "待拒绝测试单位", "暂缓测试单位"), start=1):
        candidate = EnrichmentCandidate.objects.create(
            id=f"30600000-0000-4000-8000-00000000062{index}", target_type="person", target_id=person.pk,
            field_name="affiliation", candidate_kind=policy.candidate_kind, proposed_value={"name": name},
            current_value=current_field_value("person", person, "affiliation"), source_class="university", confidence=.9,
            identity_status="confirmed", policy_version=policy.policy_version, refresh_after=timezone.now()+timedelta(days=1),
            fingerprint=sha256(f"v306-assistance-{index}".encode()).hexdigest(), conflict_group=f"v306-assistance-{index}", created_by=owner,
        )
        for source in (1, 2):
            url = f"https://isolated-{source}.example.test/affiliation/{index}"
            EnrichmentEvidence.objects.create(candidate=candidate, source_url=url, canonical_url=url, source_title="合成学校档案",
                source_domain=f"isolated-{source}.example.test", source_class="university", provider="isolated_fixture",
                supporting_text=f"隔离测试资料：V306建议复核学者在{name}工作。此文本不是真实外部服务结果。",
                retrieved_at=timezone.now(), content_checksum="a"*64, fingerprint=sha256(url.encode()).hexdigest(), extraction_method="fixture")

    session, _ = open_cataloging_session(actor=owner, source_type="manual", title="V306人工锁与建议", document_type="report")
    session.edition.work.abstract = "人工保留的简介"
    session.edition.work.save(update_fields=["abstract", "updated_at"])
    FieldLock.objects.create(edition=session.edition, field_name="abstract", locked_value="人工保留的简介", locked_by=owner, reason="管理员依据原文确认")
    MetadataCandidate.objects.create(id="30600000-0000-4000-8000-000000000631", cataloging_session=session, field_name="abstract", value="来源未支持的新简介", source="isolated_fixture")

    assisted, _ = open_cataloging_session(actor=owner, source_type="manual", title="V306智能填写演练", document_type="report")
    MetadataCandidate.objects.create(id="30600000-0000-4000-8000-000000000632", cataloging_session=assisted, field_name="abstract", value="用于验证先填表再保存的合成简介。", source="isolated_fixture")

    identity, _ = open_cataloging_session(actor=owner, source_type="manual", title="V306身份建议演练", document_type="report")
    people = [Person.objects.create(preferred_name=name, authority_status="verified") for name in ("V306保留原作者", "V306预填作者甲", "V306预填作者乙")]
    Contribution.objects.create(edition=identity.edition, person=people[0], role="author", approved=True)
    MetadataCandidate.objects.create(cataloging_session=identity, field_name="authors", value=[p.preferred_name for p in people[1:]], source="isolated_fixture")
    MetadataCandidate.objects.create(cataloging_session=identity, field_name="translators", value=[people[1].preferred_name], source="isolated_fixture")
    publisher = PublisherAuthority.objects.create(canonical_name="V306预填出版社", editorial_status="published")
    MetadataCandidate.objects.create(cataloging_session=identity, field_name="publisher", value=publisher.canonical_name, source="isolated_fixture")
    unknown, _ = open_cataloging_session(actor=owner, source_type="manual", title="V306未识别姓名演练", document_type="report")
    MetadataCandidate.objects.create(cataloging_session=unknown, field_name="authors", value=["V306待核对新人物"], source="isolated_fixture")
    ambiguous, _ = open_cataloging_session(actor=owner, source_type="manual", title="V306同名身份演练", document_type="report")
    for year in (1960, 1980):
        Person.objects.create(preferred_name="V306同名人物", birth_year=year, authority_status="verified", biography=f"隔离测试的{year}年出生人物，不是真实学者资料。")
    MetadataCandidate.objects.create(cataloging_session=ambiguous, field_name="authors", value=["V306同名人物"], source="isolated_fixture")

    for probe in HEALTH_CHECKS.all():
        HealthCheckRun.objects.create(probe_key=probe.key, capability=probe.capability, status="healthy", source="manual",
            configured=True, reachable=True, functional=True, productive=True,
            started_at=timezone.now()-timedelta(seconds=2*probe.interval_seconds+1))
