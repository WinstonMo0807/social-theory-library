import assert from "node:assert/strict";
import test from "node:test";
import { hasAdminCapability } from "../lib/admin-session.tsx";

test("unknown or editor sessions do not request administrative statistics", () => {
  assert.equal(hasAdminCapability(null, "can_view_audit_log"), false);
  assert.equal(hasAdminCapability({ role: "editor", capabilities: ["can_edit_metadata"] }, "can_view_audit_log"), false);
  assert.equal(hasAdminCapability({ role: "editor" }, "can_view_audit_log"), false);
});

test("explicit capability revocation overrides an administrative role", () => {
  assert.equal(hasAdminCapability({ role: "admin", capabilities: [] }, "can_view_audit_log"), false);
  assert.equal(hasAdminCapability({ role: "admin", capabilities: ["can_view_audit_log"] }, "can_view_audit_log"), true);
});

test("old admin session payloads retain the existing safe display fallback", () => {
  assert.equal(hasAdminCapability({ role: "admin" }, "can_view_audit_log"), true);
  assert.equal(hasAdminCapability({ role: "reader" }, "can_view_audit_log"), false);
  assert.equal(hasAdminCapability({ role: "admin" }, "can_merge_authority"), false);
});
