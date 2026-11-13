import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(relative, modules, FormDataType = FormData) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const exports = {};
  new Function("require", "exports", "FormData", code)(name => modules[name] ?? require(name), exports, FormDataType);
  return exports;
}
const authModules = {
  "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
  "next/navigation": { useSearchParams: () => new URLSearchParams() },
  "./auth-guest-records": { useGuestTransfer: () => null },
  "@/lib/auth-navigation": { safeAuthDestination: () => "/account", authPageHref: mode => `/${mode}` },
};
function nodes(tree) {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return React.isValidElement(tree) ? [tree, ...nodes(tree.props.children)] : [];
}
const input = (tree, name) => nodes(tree).find(node => node.type === "input" && node.props.name === name);

test("server-rendered credential forms cannot fall back to a credential-bearing GET", () => {
  const { AuthForm } = load("../components/auth-form.tsx", {
    ...authModules, "@/lib/api": { apiRequest() { throw Error("SSR must not request authentication"); } },
  });
  for (const mode of ["login", "register", "reset"]) {
    const html = renderToStaticMarkup(React.createElement(AuthForm, { mode }));
    assert.match(html, /<form[^>]*method="post"/);
    const fields = [...html.matchAll(/<input\b[^>]*>/g)].map(match => match[0]);
    assert.ok(fields.length > 0);
    assert.ok(fields.every(field => /\bdisabled=""/.test(field)), "Inputs stay unavailable until handlers are ready");
    assert.match(html, /<button[^>]*type="submit"[^>]*disabled=""/);
    assert.match(html, /<noscript>/);
  }
});

// This small hook harness exercises component event handlers without a browser,
// authentication server, or real credentials. It does not claim browser acceptance.
function authHarness() {
  let cursor = 0, mounted = false;
  const slots = [], effects = [], cleanups = [], requests = [];
  const slot = initial => { const at = cursor++; return slots[at] ??= { value: typeof initial === "function" ? initial() : initial }; };
  const hooks = {
    ...React,
    useId: () => "auth-check",
    useState(initial) { const entry = slot(initial); return [entry.value, value => { entry.value = typeof value === "function" ? value(entry.value) : value; }]; },
    useRef(initial) { return slot(() => ({ current: initial })).value; },
    useEffect(callback) { if (!mounted) effects.push(callback); },
  };
  class FormValues {
    constructor(tree) { this.tree = tree; }
    get(name) { return input(this.tree, name)?.props.value ?? null; }
  }
  const { AuthForm } = load("../components/auth-form.tsx", {
    ...authModules, react: hooks,
    "@/lib/api": {
      apiRequest: async (path, init) => {
        requests.push({ path, init });
        if (init?.method === "POST") throw Error("合成请求未完成，请重试。");
        return { email_delivery_available: true };
      },
    },
  }, FormValues);
  return {
    requests,
    render() { cursor = 0; return AuthForm({ mode: "register" }); },
    mount() { mounted = true; effects.forEach(effect => { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); }); },
    close() { cleanups.forEach(cleanup => cleanup()); },
  };
}

test("confirmation feedback waits for interaction, clears after correction, and focuses a rejected submission", async () => {
  const harness = authHarness();
  try {
    let tree = harness.render();
    harness.mount();
    tree = harness.render();
    assert.equal(input(tree, "password").props.disabled, false);
    input(tree, "password").props.onChange({ target: { value: "SyntheticPass12" } });
    input(tree, "confirmPassword").props.onChange({ target: { value: "SyntheticOther12" } });
    tree = harness.render();
    assert.equal(input(tree, "confirmPassword").props["aria-invalid"], undefined);
    let focused = 0;
    input(tree, "confirmPassword").props.ref.current = { focus() { focused++; } };
    let prevented = false;
    await tree.props.onSubmit({ currentTarget: tree, preventDefault() { prevented = true; } });
    tree = harness.render();
    assert.equal(prevented, true);
    assert.equal(focused, 1);
    assert.equal(harness.requests.some(request => request.init?.method === "POST"), false);
    assert.equal(input(tree, "confirmPassword").props["aria-invalid"], true);
    const help = input(tree, "confirmPassword").props["aria-describedby"];
    assert.ok(nodes(tree).some(node => node.props.id === help && node.props.role === "status"));
    input(tree, "confirmPassword").props.onChange({ target: { value: "SyntheticPass12" } });
    tree = harness.render();
    assert.equal(input(tree, "confirmPassword").props["aria-invalid"], undefined);
    await tree.props.onSubmit({ currentTarget: tree, preventDefault() {} });
    tree = harness.render();
    assert.ok(nodes(tree).some(node => node.props.role === "alert"));
    tree.props.onChange();
    assert.equal(nodes(harness.render()).some(node => node.props.role === "alert"), false);
  } finally { harness.close(); }
});

test("dialog light dismissal requires a primary press and click outside its actual bounds", () => {
  const { Dialog } = load("../components/ui/dialog.tsx", { react: {
    ...React, useRef: current => ({ current }), useEffect() {}, useEffectEvent: callback => callback,
  } });
  let requested = 0;
  const dialog = Dialog({ open: true, onRequestClose() { requested++; } });
  const target = { getBoundingClientRect: () => ({ left: 100, right: 400, top: 100, bottom: 300 }) };
  const event = (x, y, extra = {}) => ({ target, currentTarget: target, clientX: x, clientY: y, isPrimary: true, button: 0, ...extra });
  const click = (start, end = start) => { dialog.props.onPointerDown(start); dialog.props.onClick(end); };
  click(event(110, 110)); // padding: target is dialog, coordinates are inside
  assert.equal(requested, 0);
  click(event(80, 80));
  assert.equal(requested, 1);
  click(event(150, 150), event(80, 80)); // selection/drag out of the dialog
  click(event(80, 80), event(150, 150));
  click(event(80, 80, { button: 2 }));
  assert.equal(requested, 1);
  dialog.props.onPointerDown(event(80, 80));
  dialog.props.onPointerCancel(event(80, 80));
  dialog.props.onClick(event(80, 80));
  assert.equal(requested, 1);
  let prevented = false;
  dialog.props.onCancel({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true, "Escape remains controlled by the caller's close guard");
  assert.equal(requested, 2);
});
