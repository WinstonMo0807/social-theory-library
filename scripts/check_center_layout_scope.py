"""Prove the visual candidate leaves business code and the inherited CSS intact."""
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "7b8963fe"

def git(*args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", "-c", "core.safecrlf=false", *args], cwd=ROOT, text=True, encoding="utf-8")

paths = set(git("diff", "--name-only", BASE, "--", "web").splitlines())
paths.update(git("ls-files", "--others", "--exclude-standard", "--", "web").splitlines())
allowed = {
    "display", "min-width", "max-width", "width", "min-height", "max-height", "height",
    "padding", "padding-inline", "padding-block", "padding-left", "padding-top",
    "margin", "margin-top", "margin-bottom", "margin-block", "margin-block-end", "margin-inline",
    "gap", "column-gap", "row-gap", "grid-template-columns", "grid-column", "align-items",
    "border-radius", "box-shadow", "vertical-align", "overflow-x", "flex-wrap", "flex",
}
markers = ["/* Center layout candidate boundary. */", "/* Layout-only public candidate;", "/* Current public candidate:"]
checked = []
for name in sorted(paths):
    current = (ROOT / name).read_text(encoding="utf-8")
    if name == "web/app/account/layout.tsx":
        assert current.strip() == '''import type { ReactNode } from "react";
import "@/styles/features/center-layout.css";

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <div data-stl-page-layout="account">{children}</div>;
}'''
    elif name == "web/app/admin/layout.tsx":
        assert current.replace('import "@/styles/features/center-layout.css";\n', "").strip() == git("show", f"{BASE}:{name}").strip()
    elif name.endswith(".css"):
        if name == "web/styles/features/center-layout.css":
            added = current
            assert '@scope (.admin-content, [data-stl-page-layout="account"]) to (' in current
        else:
            cut = min(current.index(marker) for marker in markers if marker in current)
            without_comments = lambda text: re.sub(r"/\*.*?\*/", "", text, flags=re.S).strip()
            assert without_comments(current[:cut]) == without_comments(git("show", f"{BASE}:{name}")), f"Inherited CSS modified: {name}"
            added = current[cut:]
        properties = set(re.findall(r"(?:^|[;{])\s*([\w-]+)\s*:", added, re.M))
        assert properties <= allowed, f"Non-layout declarations in {name}: {properties - allowed}"
        assert "@keyframes" not in added and "!important" not in added
        checked.append({"file": name, "properties": sorted(properties)})
    else:
        raise AssertionError(f"Out-of-scope frontend file: {name}")
report = {"baseline": BASE, "passed": True, "changed_frontend_files": len(paths), "css": checked,
          "business_tsx_changes": "admin CSS import and account display:contents wrapper only",
          "protected": "brand, fonts, text colors, navigation, login, overlays, loading, routes, API and handlers unchanged"}
out = ROOT / "output/public-visual-20261110/runtime/scope-check.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS: {len(paths)} frontend files; {len(checked)} CSS files, layout properties only; inherited source unchanged.")
