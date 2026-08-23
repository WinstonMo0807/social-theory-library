import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const primitivesUrl = new URL("../components/action-feedback.tsx", import.meta.url);
const healthUrl = new URL("../components/functional-health-panel.tsx", import.meta.url);
const processingUrl = new URL("../components/processing-center.tsx", import.meta.url);
const workflowUrl = new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url);
const researchUrl = new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url);
const previewUrl = new URL("../components/admin/preview/work-page-preview.tsx", import.meta.url);
const routeTransitionUrl = new URL("../components/route-transition.tsx", import.meta.url);
const readerShellUrl = new URL("../components/reader-shell.tsx", import.meta.url);
const theoryAdminUrl = new URL("../components/theory-system-admin.tsx", import.meta.url);
const saveWorkUrl = new URL("../components/save-work-button.tsx", import.meta.url);
const saveTopicUrl = new URL("../components/save-topic-button.tsx", import.meta.url);
const stylesUrl = new URL("../app/globals.css", import.meta.url);

test("action primitives expose controlled idle, pending, success and error states", async () => {
  const source = await readFile(primitivesUrl, "utf8");

  assert.match(source, /export type ActionState = "idle" \| "pending" \| "success" \| "error"/);
  assert.match(source, /export function ActionButton/);
  assert.match(source, /export function ActionLink/);
  assert.match(source, /export function AsyncStatus/);
  assert.match(source, /export function ToastHost/);
  assert.doesNotMatch(source, /useState|useEffect/);
});

test("buttons and links expose pressed, pending and disabled semantics", async () => {
  const source = await readFile(primitivesUrl, "utf8");

  assert.match(source, /aria-busy=\{state === "pending"\}/);
  assert.match(source, /aria-pressed=\{pressed\}/);
  assert.match(source, /aria-disabled=\{blocked\}/);
  assert.match(source, /disabled=\{blocked\}/);
  assert.match(source, /tabIndex=\{blocked \? -1 : linkProps\.tabIndex\}/);
  assert.match(source, /if \(blocked\) \{[\s\S]*event\.preventDefault\(\)/);
  assert.match(source, /onPointerDown=\{\(event\) => \{/);
  assert.match(source, /event\.key === "Enter" \|\| event\.key === " "/);
  assert.match(source, /data-physical-press="false"/);
});

test("route feedback also follows query-only navigation", async () => {
  const source = await readFile(routeTransitionUrl, "utf8");

  assert.match(source, /useSearchParams\(\)/);
  assert.match(source, /const routeKey = `\$\{pathname\}\?\$\{searchParams\.toString\(\)\}`/);
  assert.match(source, /destination\.pathname === current\.pathname && destination\.search === current\.search/);
  assert.match(source, /anchor\.dataset\.routePending = "true"/);
  assert.match(source, /\[clearPendingNavigation, pathname, routeKey, readerRoute\]/);
});

test("async status and toast host announce outcomes without duplicating business state", async () => {
  const source = await readFile(primitivesUrl, "utf8");

  assert.match(source, /role=\{state === "error" \? "alert" : "status"\}/);
  assert.match(source, /aria-live=\{assertive \|\| state === "error" \? "assertive" : "polite"\}/);
  assert.match(source, /aria-atomic="true"/);
  assert.match(source, /items: ToastItem\[\]/);
  assert.match(source, /onDismiss\?: \(id: string\) => void/);
});

test("functional health uses shared feedback for refresh, probes and recovery", async () => {
  const source = await readFile(healthUrl, "utf8");

  assert.match(source, /from "\.\/action-feedback"/);
  assert.match(source, /<ActionButton[\s\S]*pendingLabel="正在刷新"/);
  assert.match(source, /pendingLabel="探测中"/);
  assert.match(source, /pendingLabel="正在请求恢复"/);
  assert.match(source, /<AsyncStatus state="error"/);
  assert.match(source, /<ToastHost/);
  assert.match(source, /actionInFlightRef\.current = actionKey/);
  assert.match(source, /aria-busy=\{loading \|\| Boolean\(pendingAction\)\}/);
});

test("processing center shares feedback and prevents duplicate operations", async () => {
  const source = await readFile(processingUrl, "utf8");

  assert.match(source, /<ActionLink className="button secondary" href="\/admin\/publication"/);
  assert.match(source, /<ActionButton[\s\S]*pendingLabel="正在刷新"/);
  assert.match(source, /pressed=\{paused\}/);
  assert.match(source, /<ToastHost/);
  assert.match(source, /if \(operationInFlightRef\.current\) return false/);
  assert.match(source, /if \(loadRequestRef\.current\) return loadRequestRef\.current/);
  assert.match(source, /aria-busy=\{loading \|\| Boolean\(pendingOperation\)\}/);
});

test("workflow, research and page preview use shared pending and result feedback", async () => {
  const [workflow, research, preview] = await Promise.all([
    readFile(workflowUrl, "utf8"),
    readFile(researchUrl, "utf8"),
    readFile(previewUrl, "utf8"),
  ]);

  assert.match(workflow, /<ActionButton[\s\S]*pendingLabel="正在保存"/);
  assert.match(workflow, /<ActionLink className="workflow-header-preview"/);
  assert.match(workflow, /<AsyncStatus state=\{workflowMessageState\(message\)\}/);
  assert.match(workflow, /if \(operationRef\.current\) return false/);
  assert.match(research, /<ActionButton[\s\S]*pendingLabel="正在重跑"/);
  assert.match(research, /<AsyncStatus state=\{statusState\}/);
  assert.match(preview, /<AsyncStatus/);
  assert.match(preview, /<ActionButton className="button secondary"/);
});

test("interaction feedback preserves warm neutral styling and reduced motion", async () => {
  const styles = await readFile(stylesUrl, "utf8");

  assert.match(styles, /\.action-feedback\[data-action-state="success"\]/);
  assert.match(styles, /\.action-feedback\[data-action-state="error"\]/);
  assert.match(styles, /\.action-feedback\[data-pressed="true"\]/);
  assert.match(styles, /\.toast-host/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.action-feedback[\s\S]*\.toast-item/);
});

test("reader and curation mutations use synchronous action guards", async () => {
  const [reader, theory, saveWork, saveTopic] = await Promise.all([
    readFile(readerShellUrl, "utf8"),
    readFile(theoryAdminUrl, "utf8"),
    readFile(saveWorkUrl, "utf8"),
    readFile(saveTopicUrl, "utf8"),
  ]);

  assert.match(reader, /const actionKey = "save-annotation";[\s\S]*startAction\(actionKey\)/);
  assert.match(reader, /const actionKey = `toggle-bookmark:/);
  assert.match(reader, /finishAction\(actionKey\)/);
  assert.match(theory, /startAction\(actionKey\)/);
  assert.match(theory, /create-timeline-event/);
  assert.match(theory, /create-reading-path/);
  assert.match(saveWork, /pressed=\{Boolean\(effectiveSavedId\)\}/);
  assert.match(saveTopic, /usePublicSession\(\)/);
  assert.match(saveTopic, /pressed=\{Boolean\(effectiveSavedId\)\}/);
});
