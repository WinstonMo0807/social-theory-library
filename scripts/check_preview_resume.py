"""Small offline checks for the fixture-resume boundary; never starts a server."""
import json
from pathlib import Path
import sqlite3
import tempfile

from local_cataloging_e2e_api import main


def rejected(**options):
    try:
        main(api_port=18111, web_port=18110, **options)
    except ValueError:
        return
    raise AssertionError("Unsafe resume was accepted")


rejected(resume_ready_file="unused.json")
with tempfile.TemporaryDirectory(prefix="stl-v305-e2e-") as directory:
    root = Path(directory)
    record = root / "runtime.json"
    data = {"fixture_directory": directory, "api_url": "http://127.0.0.1:18111/api",
            "web_url": "http://127.0.0.1:18110", "offline": True}
    record.write_text(json.dumps({**data, "api_url": "http://127.0.0.1:18112/api"}), encoding="utf-8")
    rejected(offline=True, resume_ready_file=record)
    record.write_text(json.dumps(data), encoding="utf-8")
    rejected(offline=True, resume_ready_file=record)  # Missing DB must not be created.
    assert not (root / "local_fixture.sqlite3").exists()
    with sqlite3.connect(root / "local_fixture.sqlite3") as connection:
        connection.execute("CREATE TABLE accounts_user (email TEXT)")
        connection.execute("INSERT INTO accounts_user VALUES ('fixture@not-allowed.invalid')")
    connection.close()
    rejected(offline=True, resume_ready_file=record)
print("PASS: online mode, mismatched endpoint, missing DB and non-fixture account are rejected before Django setup.")
