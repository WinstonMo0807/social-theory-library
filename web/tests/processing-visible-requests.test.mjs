import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

// Exercise the component's actual loader without mounting a browser or a server.
const hooks = { slots: [], cursor: 0, effects: [], callbacks: [] };
globalThis.__processingTestHooks = hooks;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.split("?")[0].endsWith("/components/processing-center.tsx")) {
      let source;
      if (specifier === "react") source = `
        const h = globalThis.__processingTestHooks;
        export function useState(initial) { const i = h.cursor++; if (!(i in h.slots)) h.slots[i] = initial; return [h.slots[i], value => { h.slots[i] = typeof value === 'function' ? value(h.slots[i]) : value; }]; }
        export function useRef(initial) { const i = h.cursor++; return h.slots[i] ??= {current: initial}; }
        export function useEffect(effect) { h.effects.push(effect); }
        export function useMemo(read) { return read(); }
        export function useCallback(callback) { h.callbacks.push(callback); return callback; }
      `;
      if (specifier === "@/lib/admin-session") source = "export const useAdminSession = () => null; export const hasAdminCapability = () => false;";
      if (source) return { url: `data:text/javascript,${encodeURIComponent(source)}`, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".module.css")) return { format: "module", source: "export default {};", shortCircuit: true };
    return nextLoad(url, context);
  },
});
const { ProcessingCenter } = await import("../components/processing-center.tsx");

const originalFetch = globalThis.fetch;
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const payload = { results: [], page: 1, pages: 1, count: 0, counts: {}, workloads: {}, can_manage: false, ocr: {}, search: {}, model_health: {}, runtime: {} };
function render() {
  hooks.cursor = 0; hooks.effects = []; hooks.callbacks = [];
  return ProcessingCenter();
}
function elements(element) {
  return !element || typeof element !== "object" ? [] : [element, ...[element.props?.children].flat(Infinity).flatMap(elements)];
}
async function setup(surface) {
  hooks.slots = [];
  globalThis.window = { location: new URL(`http://candidate.invalid/admin/processing?surface=${surface}`), setTimeout, clearTimeout, setInterval, clearInterval };
  globalThis.document = { hidden: false };
  render(); const dispose = hooks.effects[0](); await tick(); dispose();
  return render();
}
function toggleTechnical(tree, open) {
  elements(tree).find(node => node.props?.className === "processing-reference-technical").props.onToggle({ currentTarget: { open } });
  return render();
}

test("closed processing surfaces only read visible data; opening technical details restores their real sources", async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({ path: new URL(url, "http://candidate.invalid").pathname, options }); return Response.json(payload); };
  try {
    for (const [surface, expected] of [
      ["overview", ["items", "queue-health"]], ["documents", ["items", "queue-health"]], ["workers", ["review-tasks"]],
      ["research-sources", []], ["ai-models", []], ["projections", []], ["faults", []],
    ]) {
      calls.length = 0;
      const tree = await setup(surface);
      assert.equal(await hooks.callbacks[0](), true);
      assert.deepEqual(calls.map(call => call.path.split("/").at(-2)), expected, surface);
      assert.ok(calls.every(call => call.options.credentials === "include" && call.options.signal));
      assert.equal(elements(tree).some(node => node.type?.name === "OcrTaskMonitor"), false);
    }
    let tree = await setup("documents");
    tree = toggleTechnical(tree, true); calls.length = 0;
    assert.equal(elements(tree).filter(node => node.type?.name === "OcrTaskMonitor").length, 1);
    await hooks.callbacks[0]();
    assert.deepEqual(calls.map(call => call.path.split("/").at(-2)), ["items", "queue-health", "processing-center"]);
    tree = toggleTechnical(tree, false); calls.length = 0;
    await hooks.callbacks[0]();
    assert.equal(elements(tree).some(node => node.type?.name === "OcrTaskMonitor"), false);
    assert.deepEqual(calls.map(call => call.path.split("/").at(-2)), ["items", "queue-health"]);
  } finally { globalThis.fetch = originalFetch; delete globalThis.window; delete globalThis.document; }
});

test("a 503 remains an explicit visible failure even while technical details are closed", async () => {
  globalThis.fetch = async () => new Response("unavailable", { status: 503 });
  try {
    await setup("workers");
    assert.equal(await hooks.callbacks[0](), false);
    const tree = render();
    const status = elements(tree).find(node => node.type?.name === "AsyncStatus" && node.props.state === "error");
    assert.match(status.props.message, /人工待办暂时读取失败/);
    const details = elements(tree).find(node => node.props?.className === "processing-reference-technical");
    assert.equal(details.props.open, false);
    assert.equal(elements(details).includes(status), false);
  } finally { globalThis.fetch = originalFetch; delete globalThis.window; delete globalThis.document; }
});

test("overlapping refreshes share one request and changing surfaces aborts and ignores a late response", async () => {
  const pending = [];
  globalThis.fetch = (url, options) => new Promise(resolve => pending.push({ url, options, resolve }));
  try {
    let tree = await setup("documents");
    const load = hooks.callbacks[0];
    const first = load();
    assert.equal(load(), first);
    assert.equal(pending.length, 2);
    tree = toggleTechnical(tree, true);
    elements(tree).find(node => node.props?.id === "processing-surface-tab-research-sources").props.onClick();
    tree = render();
    toggleTechnical(tree, false);
    assert.equal(await hooks.callbacks[0](), true);
    assert.ok(pending.every(call => call.options.signal.aborted));
    pending.forEach(call => call.resolve(Response.json({ ...payload, results: [{ id: "late-old-surface" }] })));
    assert.equal(await first, false);
    assert.equal(hooks.slots.some(value => Array.isArray(value) && value.some(row => row?.id === "late-old-surface")), false);
  } finally { globalThis.fetch = originalFetch; delete globalThis.window; delete globalThis.document; }
});
