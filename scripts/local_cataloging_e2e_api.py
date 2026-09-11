"""Start an isolated, disposable Django fixture server for cataloging E2E.

Never accepts a database URL or production directory. The temporary database
and fixture account are local-only and must never be used for deployment.
"""
import os
from pathlib import Path
import sys
import tempfile


def main():
    repository = Path(__file__).resolve().parents[1]
    fixture_directory = Path(tempfile.mkdtemp(prefix="stl-v305-e2e-")).resolve()
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DATABASE_URL": f"sqlite:///{(fixture_directory / 'local_fixture.sqlite3').as_posix()}",
        "NAS_LIBRARY_ROOT": str(fixture_directory / "media"),
        "NAS_INCOMING_ROOT": str(fixture_directory / "incoming"),
        "DJANGO_DEBUG": "true", "PUBLIC_DEPLOYMENT_MODE": "false",
        "DJANGO_SECURE_COOKIES": "false", "DJANGO_SSL_REDIRECT": "false",
        "DJANGO_SECRET_KEY": "local-e2e-fixture-only-not-for-production-305",
        "LIBRARY_OWNER_EMAIL": "owner-v305@example.test",
        # Match the existing internal SSR request contract. This public dummy
        # value belongs only to the disposable loopback fixture, never a user
        # session or a production setting. Browser requests do not receive it.
        "INTERNAL_API_TOKEN": "local-e2e-server-token-305-not-for-production",
        # This suite creates more login sessions per minute than a human run.
        # Throttle enforcement is tested separately; permission checks stay on.
        "AUTH_LOGIN_RATE": "60/min",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
        "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:3105",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "http://127.0.0.1:3105",
        "CELERY_BROKER_URL": "memory://", "CELERY_TASK_ALWAYS_EAGER": "false",
        "PROCESS_INGESTION_INLINE": "false", "PYTHONIOENCODING": "utf-8",
    })
    sys.path.insert(0, str(repository / "api"))
    import django
    from django.conf import settings

    # This disposable SQLite server has concurrent browser requests. Acquire
    # write intent up front instead of racing a deferred read-to-write upgrade.
    # Production PostgreSQL settings and transaction/row locks are unchanged.
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.sqlite3" or Path(database["NAME"]).resolve() != fixture_directory / "local_fixture.sqlite3":
        raise RuntimeError("E2E database is not the newly created isolated SQLite file")
    database.setdefault("OPTIONS", {}).update(timeout=20, transaction_mode="IMMEDIATE")
    django.setup()
    from django.core.management import call_command
    from accounts.models import User
    call_command("migrate", interactive=False, verbosity=0)
    for email, role in (("curator-v305@example.test", "editor"), ("reader-v305@example.test", "reader"), ("administrator-v305@example.test", "admin"), ("owner-v305@example.test", "admin")):
        User.objects.create_user(
            username=email, email=email, display_name="Local E2E",
            role=role, password="E2E-Local-Only-305-passphrase",
        )
    from catalog.models import Contribution, Edition, Person, PersonNameVariant, ScholarProfile, Work
    from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
    ensure_query_lexicon_state()
    # Dedicated, deterministic local records for permission, conflict, retry
    # and rollback browser checks. Nothing points at production holdings.
    for index, label in enumerate(("完整操作", "双档案", "网络重试", "过期预览", "撤回中断"), start=1):
        source = Person.objects.create(id=f"30500000-0000-4000-8000-{index:011d}1", preferred_name=f"E2E{label}来源",
                                       original_name=f"E2E Identity {index}", authority_status="verified", birth_year=1930)
        target = Person.objects.create(id=f"30500000-0000-4000-8000-{index:011d}2", preferred_name=f"E2E{label}保留",
                                       original_name=f"E2E Identity {index}", authority_status="verified", birth_year=1930)
        PersonNameVariant.objects.create(person=source, name=f"E2E{label}旧译名", variant_type="alias", source_kind="editorial", is_verified=True)
        work = Work.objects.create(title=f"E2E{label}作品", document_type="book", language="zh-CN")
        edition = Edition.objects.create(work=work, publication_mode="bibliographic")
        Contribution.objects.create(edition=edition, person=source, role="author", approved=True, source="local-e2e")
        if index in (1, 2):
            ScholarProfile.objects.create(person=source, slug=f"e2e-person-source-{index}", short_description="来源档案保留")
        if index == 2:
            ScholarProfile.objects.create(person=target, slug="e2e-person-target-2", short_description="目标档案也保留")
    print(f"Isolated local E2E database: {fixture_directory}", flush=True)
    call_command("runserver", "127.0.0.1:8105", use_reloader=False)


if __name__ == "__main__":
    main()
