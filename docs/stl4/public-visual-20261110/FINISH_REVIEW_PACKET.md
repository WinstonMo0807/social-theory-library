# Finish review packet

This is a code-led refinement of an existing deployed application, not a replacement visual world. Review only the allowed center-body layout. The earlier whole-site image brief was superseded by the user: “只去变动读者中心、管理中心的排版视效等，他们的任务分类栏、端口设计、其余前端内容，均不要变动”; “登录页不要改”; login dialogs, all other dialogs/drawers and loading animation unchanged. Exact existing brand, fonts and font colors required. User said no more mobile Image Gen; responsive code only. Do not request new assets or rewrite nav/type/color/content/functionality. Existing generated comps are spatial critique references only where consistent with these instructions. No comp-diff or concept-seed run is claimed; user pinned the incumbent design.

Root: C:/Users/12297/.codex/worktrees/stl-public-visual-20261110/书库开发3
Product: PRODUCT.md
Direction contract: docs/stl4/public-visual-20261110/DIRECTION.md
Scope: docs/stl4/public-visual-20261110/SCOPE.json
Artifact: web/styles/features/center-layout.css, web/app/account/layout.tsx, web/app/admin/layout.tsx, appended module rules in web/components/admin and web/components/research. Compare to commit 7c4e4a0d. No business handlers/API changes.
Craft floor: C:/Users/12297/.codex/skills/impeccable/reference/craft-floor.md
Role contract: C:/Users/12297/.codex/skills/impeccable/reference/degraded/finish-reviewer.md (use actual subagent role; ignore its no-subagent preamble, because this is a real fresh subagent).

No separate new-world QUALITY BAR card: the user pins the existing brand and asks award-quality execution within the allowed scope. Brand reference: F:/agent skills/书库开发3/output/reference/brand-board-20261027.png. Spatial critique refs: output/public-visual-20261110/design/A01-v1.png (if absent use DESIGN_IMAGES exact A01 path), R01-v1.png (same rule), A08-v1.png. Their invented logo/nav/type/data are explicitly overridden. Do not treat them as a whole-page pixel reproduction spec.

Required captures, all in .impeccable/review/: desktop.png, mobile.png, user-320.png, reader-desktop.png, reader-mobile.png, reader-user-320.png, catalog-desktop.png, ocr-desktop.png, citation-desktop.png, citation-tablet.png, privacy-desktop.png, sharing-mobile.png, accounts-desktop.png. View these first. They are synthetic fixture browser screenshots, not production/private content. Synthetic names are not new product copy. Code did not add demo data to production.

Verification: output/public-visual-20261110/runtime/accepted.json has 80 real entry captures with global stylesheet and module baseline toggling; all UI text/type/color/protected-style checks pass. PDF rendering changes with available width and is measured separately from UI type. Six targeted interaction cases passed (interactions.json): actual booklist save/refresh, explicit 503 recovery preserving input, catalog draft preview/diff/save, list query/pagination/return, live website-draft preview tab retention, public/login unchanged styles. Preferences 16 cases passed including dark/large/serif/reduced motion (preferences/report.json). Build and tsc exit0. Scope guard passes: 38 frontend files, 36 layout-only CSS files, import/wrapper only. Detector ran once, 23 findings all in unchanged incumbent CSS; no added-rule findings (detector-triage.json). Preserve those pinned inherited styles; no second detector.

Known bounds: PV072 scholar overflow is identical baseline/candidate, comes from incumbent protected structure; not newly introduced and not authorized for nav/overlay redesign. PV098 topic preview returns400 under current fixture/type contract, recorded existing behavior. PV035 existing three-pane public-layout editor spatial structure retained, PV050 private fullPreview uses the unchanged public EvidenceCurationView. Do not call unconfigured model/OCR tasks a successful real service test. No production writes or deployment.

Return required disposition and five sections from the role contract. Review is read-only: no browser/server, no code writes. Need actual visible findings tied to the allowed scope, not generic requests for missing new-world machinery. Parent will apply authorized corrections and request verdict if needed.
