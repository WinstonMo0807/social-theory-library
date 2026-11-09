"""Observe role gates against the disposable loopback fixture, never production.

Only the fixture login is submitted. Business endpoints are GET and outbound
providers are fenced by local_cataloging_e2e_api --offline. Persist status and
field names only, not response data, credentials, cookies, or configuration.
"""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "output/public-visual-20261110/audit/FIXTURE_RUNTIME.json"
PATHS = [
    "/auth/me/", "/catalog/home/", "/catalog/site-config/",
    "/catalog/works/", "/catalog/scholars/", "/catalog/topics/",
    "/catalog/search/?q=fixture", "/catalog/admin/today-work/",
    "/catalog/admin/search/?q=fixture", "/catalog/admin/library/works/",
    "/catalog/admin/scholars/", "/catalog/admin/site-content/",
    "/catalog/admin/index-maintenance/", "/catalog/admin/query-lexicon/",
    "/catalog/admin/system-status/", "/catalog/admin/ocr-runtime/",
    "/ingestion/processing-workspace/", "/auth/users/workspace/",
    "/reading/reader-center/", "/reading/research-projects/",
    "/reading/lists/", "/reading/annotations/", "/reading/bookmarks/",
    "/reading/citation-audits/capabilities/", "/reading/privacy/",
    "/reading/groups/", "/reading/admin/ai-runtime-profiles/",
    "/distribution/assets/41300000-0000-4000-8000-000000000103/access/",
]


def main():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    if runtime["api_url"] != "http://127.0.0.1:18111/api" or not runtime["offline"]:
        raise RuntimeError("Only the offline visual fixture is allowed")
    directory = Path(runtime["fixture_directory"]).resolve()
    if not directory.name.startswith("stl-v305-e2e-") or not (directory / "local_fixture.sqlite3").is_file():
        raise RuntimeError("Fresh fixture provenance is missing")
    base = runtime["api_url"]
    rows = []
    for role, email in [("guest", None), ("reader", "reader"), ("editor", "curator"), ("admin", "administrator"), ("owner", "owner")]:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        owner = None
        if email:
            opener.open(base + "/auth/login/", timeout=30).read()
            csrf = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
            request = urllib.request.Request(base + "/auth/login/", method="POST", headers={
                "Content-Type": "application/json", "X-CSRFToken": csrf,
                "Origin": "http://127.0.0.1:18110",
            }, data=json.dumps({"email": email + "-v305@example.test", "password": "E2E-Local-Only-305-passphrase", "remember_me": False}).encode())
            owner = str(json.load(opener.open(request, timeout=30))["user"]["id"])
        for path in PATHS:
            headers = {}
            if owner and path.startswith("/reading/"):
                headers["X-Reader-Owner"] = owner
            if owner and path.startswith("/auth/users/"):
                headers["X-Editor-Owner"] = owner
            request = urllib.request.Request(base + path, headers=headers)
            try:
                response = opener.open(request, timeout=35)
            except urllib.error.HTTPError as error:
                response = error
            except (TimeoutError, OSError) as error:
                rows.append({"role": role, "method": "GET", "path": "/api" + path, "status": None, "error": type(error).__name__})
                continue
            status = response.status
            try:
                data = json.load(response)
            except (ValueError, UnicodeError):
                data = None
            keys = sorted(data) if isinstance(data, dict) else []
            item_keys = sorted(data["results"][0]) if isinstance(data, dict) and isinstance(data.get("results"), list) and data["results"] and isinstance(data["results"][0], dict) else []
            rows.append({"role": role, "method": "GET", "path": "/api" + path, "request_header_names": sorted(headers), "status": status, "response_keys": keys, "item_keys": item_keys})
        print(role, {code: sum(row["role"] == role and row["status"] == code for row in rows) for code in {row["status"] for row in rows if row["role"] == role}}, flush=True)
    destination = ROOT / "docs/stl4/public-visual-20261110/FIXTURE_ROLE_HTTP.json"
    destination.write_text(json.dumps({"environment": "offline loopback synthetic SQLite fixture", "scope": "GET role gates and response field names; no provider success claim", "observations": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
