"""Start an isolated, disposable Django fixture server for cataloging E2E.

Never accepts a database URL or production directory. The temporary database
and fixture account are local-only and must never be used for deployment.
"""
import os
from pathlib import Path
import sys
import tempfile


def main(*, api_port=8105, web_port=3105, offline=False, ready_file=None, resume_ready_file=None):
    if not all(isinstance(port, int) and 1024 <= port <= 65535 for port in (api_port, web_port)):
        raise ValueError("Fixture ports must be unprivileged local ports")
    if offline:
        # Only this fixture process is fenced; incoming loopback requests work.
        # Existing production providers, mail and local model services cannot
        # accidentally be called by synthetic tasks or source checks.
        import socket
        def deny_connect(*args, **kwargs):
            raise OSError("Outbound connections are disabled in the isolated visual fixture")
        socket.socket.connect = deny_connect
        socket.socket.connect_ex = deny_connect
    repository = Path(__file__).resolve().parents[1]
    if resume_ready_file:
        from contextlib import closing
        import json
        import sqlite3
        if not offline:
            raise ValueError("Resuming a preview requires --offline")
        runtime = json.loads(Path(resume_ready_file).read_text(encoding="utf-8"))
        fixture_directory = Path(runtime["fixture_directory"]).resolve()
        if (runtime.get("offline") is not True
                or runtime.get("api_url") != f"http://127.0.0.1:{api_port}/api"
                or runtime.get("web_url") != f"http://127.0.0.1:{web_port}"
                or fixture_directory.parent != Path(tempfile.gettempdir()).resolve()
                or not fixture_directory.name.startswith("stl-v305-e2e-")):
            raise ValueError("Only the recorded offline temporary fixture can be resumed")
        fixture_database = fixture_directory / "local_fixture.sqlite3"
        if not fixture_database.is_file() or fixture_database.is_symlink():
            raise ValueError("The recorded fixture database must already exist")
        with closing(sqlite3.connect(f"{fixture_database.as_uri()}?mode=ro", uri=True)) as connection:
            accounts = connection.execute("SELECT email FROM accounts_user").fetchall()
            if not accounts or any(not email.endswith("@example.test") for (email,) in accounts):
                raise ValueError("Only synthetic fixture accounts may be resumed")
    else:
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
        # The layout suite loads a 1001-page PDF across five browser contexts
        # and many admin routes within a minute. Keep production throttles
        # unchanged; rate-limit behavior has independent failure-injection tests.
        "API_ANON_RATE": "2000/min", "API_USER_RATE": "4000/min",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
        "CORS_ALLOWED_ORIGINS": f"http://127.0.0.1:{web_port}",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"http://127.0.0.1:{web_port}",
        "CELERY_BROKER_URL": "memory://", "CELERY_TASK_ALWAYS_EAGER": "true" if os.environ.get("STL_E2E_V307") == "1" else "false",
        "PROCESS_INGESTION_INLINE": "false", "PYTHONIOENCODING": "utf-8",
        "THEORY_SYSTEM_ENABLED": "true",
        "CACHE_URL": "",
        "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
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
    if resume_ready_file:
        print("Resuming existing offline fixture; no migration, reseeding or credential reset.", flush=True)
        call_command("runserver", f"127.0.0.1:{api_port}", use_reloader=False)
        return
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
    portrait_person = Person.objects.create(id="30500000-0000-4000-8000-000000000092", preferred_name="E2E肖像学者", authority_status="verified")
    ScholarProfile.objects.create(id="30500000-0000-4000-8000-000000000091", person=portrait_person, slug="e2e-portrait-scholar", editorial_status="published", short_description="已发布简介")
    from catalog.models import KnowledgeNode, ReadingPath, ReadingPathStage
    KnowledgeNode.objects.create(id="30500000-0000-4000-8000-000000000101", canonical_name_zh="E2E理论配图", node_type="theory_tradition", slug="e2e-node-image", status="published")
    image_path = ReadingPath.objects.create(id="30500000-0000-4000-8000-000000000102", title="E2E路径配图", slug="e2e-path-image", status="published")
    ReadingPathStage.objects.create(id="30500000-0000-4000-8000-000000000103", reading_path=image_path, name="保留原阅读阶段", position=0)
    from v306_e2e_fixtures import seed_v306
    seed_v306(User.objects.get(email="owner-v305@example.test"))
    from reader_v306_e2e_fixtures import seed_reader_v306
    seed_reader_v306()
    from parallel_reader_e2e_fixtures import seed_parallel_reader
    seed_parallel_reader()
    from theory_e2e_fixtures import seed_theory
    seed_theory(User.objects.get(email="owner-v305@example.test"))
    from subdiscipline_e2e_fixtures import seed_subdisciplines
    seed_subdisciplines(User.objects.get(email="owner-v305@example.test"))
    from timeline_e2e_fixtures import seed_timeline
    seed_timeline(User.objects.get(email="owner-v305@example.test"))
    from graph_e2e_fixtures import seed_graph
    seed_graph(User.objects.get(email="owner-v305@example.test"))
    from reading_path_e2e_fixtures import seed_reading_paths
    seed_reading_paths(User.objects.get(email="owner-v305@example.test"))
    from scholar_e2e_fixtures import seed_scholars
    seed_scholars(User.objects.get(email="owner-v305@example.test"))
    from topic_e2e_fixtures import seed_topics
    seed_topics(User.objects.get(email="owner-v305@example.test"))
    from editorial_e2e_fixtures import seed_editorial
    seed_editorial(User.objects.get(email="owner-v305@example.test"))
    from v306_assistance_e2e_fixtures import seed_assistance
    seed_assistance(User.objects.get(email="owner-v305@example.test"))
    if os.environ.get("STL_E2E_V307") == "1":
        from v307_e2e_fixtures import seed_v307
        seed_v307(User.objects.get(email="owner-v305@example.test"))
    print(f"Isolated local E2E database: {fixture_directory}", flush=True)
    if ready_file:
        import json
        Path(ready_file).write_text(json.dumps({"fixture_directory": str(fixture_directory),
            "api_url": f"http://127.0.0.1:{api_port}/api", "web_url": f"http://127.0.0.1:{web_port}",
            "offline": offline, "data": "synthetic fixtures; no production data"}), encoding="utf-8")
    call_command("runserver", f"127.0.0.1:{api_port}", use_reloader=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8105)
    parser.add_argument("--web-port", type=int, default=3105)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--ready-file")
    parser.add_argument("--resume-ready-file", help="Resume only an existing recorded offline temporary fixture")
    arguments = parser.parse_args()
    main(api_port=arguments.api_port, web_port=arguments.web_port,
         offline=arguments.offline, ready_file=arguments.ready_file, resume_ready_file=arguments.resume_ready_file)
