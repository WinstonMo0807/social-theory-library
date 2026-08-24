import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const healthPanelUrl = new URL("../components/functional-health-panel.tsx", import.meta.url);
const diagnosticsUrl = new URL("../components/processing-diagnostics.tsx", import.meta.url);
const stylesUrl = new URL("../app/editorial-workspaces.css", import.meta.url);

test("Processing Center consumes persisted projection capability and provider diagnostics", async () => {
  const [healthPanel, diagnostics] = await Promise.all([
    readFile(healthPanelUrl, "utf8"),
    readFile(diagnosticsUrl, "utf8"),
  ]);

  assert.match(healthPanel, /diagnostics\?: ProcessingDiagnosticsPayload/);
  assert.match(healthPanel, /<ProcessingDiagnosticsPanel/);
  assert.match(diagnostics, /落后投影/);
  assert.match(diagnostics, /缺少能力/);
  assert.match(diagnostics, /Provider 降级/);
  assert.match(diagnostics, /人工接受表现/);
  assert.match(diagnostics, /接受率/);
  assert.match(diagnostics, /Prompt Registry/);
  assert.match(diagnostics, /missing_active_for_task_profiles/);
  assert.match(diagnostics, /page_load_performs_live_probes: false/);
});

test("each diagnostic explains impact blocking and next action", async () => {
  const diagnostics = await readFile(diagnosticsUrl, "utf8");

  for (const label of ["原因", "受影响功能", "是否阻断", "建议动作", "处理指引", "安全恢复说明"]) {
    assert.match(diagnostics, new RegExp(label));
  }
  assert.match(diagnostics, /item\.publication_blocking \? "阻断相关发布" : "不阻断发布"/);
  assert.match(diagnostics, /item\.safe_actions\.length/);
  assert.match(diagnostics, /onAction\(item, action\)/);
});

test("diagnostic recovery reuses backend-provided bounded actions and refreshes snapshot", async () => {
  const healthPanel = await readFile(healthPanelUrl, "utf8");
  const action = healthPanel.match(/async function runDiagnosticAction[\s\S]*?\n  }\n/)?.[0] ?? "";

  assert.match(action, /apiRequest\(/);
  assert.match(action, /action\.endpoint/);
  assert.match(action, /method: action\.method/);
  assert.match(action, /JSON\.stringify\(action\.body\)/);
  assert.match(action, /await loadSnapshot\(true\)/);
  assert.doesNotMatch(action, /run_probe/);
});

test("Processing Center diagnostics inherit the editorial workspace and stay responsive", async () => {
  const styles = await readFile(stylesUrl, "utf8");

  assert.match(styles, /\[data-ui-scope="editorial-v2"\] \.processing-diagnostics/);
  assert.match(styles, /var\(--stl2-paper-strong\)/);
  assert.match(styles, /var\(--stl2-line\)/);
  assert.match(styles, /@media \(max-width: 1080px\)[\s\S]*\.processing-diagnostic-sections \{ grid-template-columns: 1fr/);
  assert.match(styles, /@media \(max-width: 520px\)[\s\S]*\.processing-diagnostic-details > div \{ grid-template-columns: 1fr/);
});
