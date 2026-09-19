import assert from "node:assert/strict";
import test from "node:test";
import { primaryEditionRequest } from "../lib/api/primary-edition.ts";
import { safeAdminHref, withAdminReturn } from "../lib/admin-route-context.ts";

const preview = { edition_id: "selected-edition", can_select: true, blocking: [], request_key: "30600000-0000-4000-8000-000000000111", fingerprint: "a".repeat(64) };

test("A03/A13 primary selection keeps reviewed fingerprint and request identity across retries", () => {
  const first = primaryEditionRequest(preview, "selected-edition");
  const second = primaryEditionRequest(preview, "selected-edition");
  assert.deepEqual(first, second);
  assert.deepEqual(first, { request_key: preview.request_key, fingerprint: preview.fingerprint, confirm: true });
});

test("A03/A14 primary request rejects another Edition, blocked or untrusted preview", () => {
  assert.throws(() => primaryEditionRequest(preview, "another-edition"));
  assert.throws(() => primaryEditionRequest({ ...preview, can_select: false }, "selected-edition"));
  assert.throws(() => primaryEditionRequest({ ...preview, blocking: ["仍有未发布草稿"] }, "selected-edition"));
  assert.throws(() => primaryEditionRequest({ ...preview, fingerprint: "invalid" }, "selected-edition"));
  assert.throws(() => primaryEditionRequest({ ...preview, request_key: "" }, "selected-edition"));
});

test("A31 full preview returns to exact editor and then the original filtered list", () => {
  const list = "/admin/library?view=editions&page=2&work_id=work";
  const editor = withAdminReturn("/admin/library/works/work?edition=edition", list, "file");
  const previewHref = withAdminReturn("/admin/preview/works/edition", editor);
  const editorFromPreview = new URL(previewHref, "https://library.test").searchParams.get("return_to");
  assert.equal(safeAdminHref(editorFromPreview), editor);
  assert.equal(new URL(editorFromPreview, "https://library.test").searchParams.get("edition"), "edition");
  assert.equal(new URL(editorFromPreview, "https://library.test").searchParams.get("return_to"), list);
});
