import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const panelUrl = new URL("../components/functional-health-panel.tsx", import.meta.url);
const processingUrl = new URL("../components/processing-center.tsx", import.meta.url);
const stylesUrl = new URL("../app/globals.css", import.meta.url);

test("processing center leads with persisted functional health", async () => {
  const [panel, processing] = await Promise.all([
    readFile(panelUrl, "utf8"),
    readFile(processingUrl, "utf8"),
  ]);

  assert.match(panel, /"\/catalog\/admin\/functional-health\/"/);
  assert.match(panel, /page_load_performs_live_probes: boolean/);
  assert.match(panel, /页面读取最近一次探测结果，不会在打开时连接外部服务/);
  assert.match(processing, /<FunctionalHealthPanel revision=\{revision\} \/>/);
  assert.ok(
    processing.indexOf("<FunctionalHealthPanel") < processing.indexOf('<section className="processing-summary"'),
    "functional health should appear before queue totals",
  );
});

test("snapshot loading never starts a live probe", async () => {
  const panel = await readFile(panelUrl, "utf8");
  const loadSnapshot = panel.match(/const loadSnapshot = useCallback[\s\S]*?\n  }, \[\]\);/)?.[0] ?? "";

  assert.match(loadSnapshot, /apiRequest<FunctionalHealthPayload>/);
  assert.doesNotMatch(loadSnapshot, /method:\s*"POST"/);
  assert.doesNotMatch(loadSnapshot, /run_probe|recover/);
  assert.match(panel, /setInterval\(\(\) => void loadSnapshot\(\), 30000\)/);
});

test("snapshot lifecycle handles missing credentials, overlap and unmount", async () => {
  const panel = await readFile(panelUrl, "utf8");
  const loadSnapshot = panel.match(/const loadSnapshot = useCallback[\s\S]*?\n  }, \[\]\);/)?.[0] ?? "";

  assert.match(loadSnapshot, /if \(actionInFlightRef\.current && !allowDuringAction\) return Promise\.resolve\(\)/);
  assert.match(loadSnapshot, /if \(snapshotRequestRef\.current\) return snapshotRequestRef\.current/);
  assert.match(loadSnapshot, /if \(!token\) \{[\s\S]*setLoading\(false\)/);
  assert.match(loadSnapshot, /\{ signal: controller\.signal \}/);
  assert.match(loadSnapshot, /if \(!mountedRef\.current \|\| controller\.signal\.aborted\) return/);
  assert.match(panel, /mountedRef\.current = false;[\s\S]*snapshotAbortRef\.current\?\.abort\(\);[\s\S]*actionAbortRef\.current\?\.abort\(\)/);
});

test("manual probes and recovery requests follow the backend contract", async () => {
  const panel = await readFile(panelUrl, "utf8");

  assert.match(panel, /action: "run_probe", probe_key: probeKey/);
  assert.match(panel, /action: "recover"/);
  assert.match(panel, /incident_id: incident\.id/);
  assert.match(panel, /recovery_action: action/);
  assert.match(panel, /idempotency_key: `incident:\$\{incident\.id\}:occurrence:\$\{incident\.occurrence_count\}:\$\{action\}`/);
  assert.match(panel, /disabled=\{Boolean\(pendingAction\) \|\| incident\.status === "recovering"\}/);
});

test("manual actions use a synchronous lock and abort-safe state updates", async () => {
  const panel = await readFile(panelUrl, "utf8");

  assert.equal((panel.match(/if \(actionInFlightRef\.current\) return;/g) ?? []).length, 2);
  assert.equal((panel.match(/actionInFlightRef\.current = actionKey;/g) ?? []).length, 2);
  assert.equal((panel.match(/signal: controller\.signal/g) ?? []).length, 3);
  assert.equal((panel.match(/if \(!mountedRef\.current \|\| controller\.signal\.aborted\) return;/g) ?? []).length >= 5, true);
  assert.equal((panel.match(/if \(mountedRef\.current\) setPendingAction\(""\);/g) ?? []).length, 2);
  assert.match(panel, /await loadSnapshot\(true\)/);
  assert.match(panel, /state=\{loading \? "pending" : error \? "error" : "idle"\}/);
  assert.match(panel, /disabled=\{Boolean\(pendingAction\)\}/);
});

test("health cards expose the four product dimensions and actionable diagnostics", async () => {
  const panel = await readFile(panelUrl, "utf8");

  for (const label of ["已配置", "可连接", "可工作", "有产出", "可能原因", "受影响功能", "人工处理提示", "最近恢复记录"]) {
    assert.match(panel, new RegExp(label));
  }
  assert.match(panel, /dependency\.details/);
  assert.match(panel, /dependency\.last_checked_at/);
  assert.match(panel, /incident\.safe_recovery_actions/);
});

test("functional health layout remains usable on narrow screens", async () => {
  const styles = await readFile(stylesUrl, "utf8");

  assert.match(styles, /\.functional-health-capability-grid/);
  assert.match(styles, /@media \(max-width: 520px\)[\s\S]*\.functional-health-dimensions \{ grid-template-columns: repeat\(2/);
  assert.match(styles, /\.functional-health-incident\.critical/);
  assert.match(styles, /\.functional-health-recovery-status\.succeeded/);
});
