import assert from "node:assert/strict";
import test from "node:test";
import { evidenceCurationPreviewHref } from "../lib/admin-curation-preview.ts";

test("evidence previews keep the actual parent identity in the canonical editor route", () => {
  const id = "d72e3ceb-5524-4647-b690-b9fa8825b19f";
  for (const [route, type] of [["topics", "topic"], ["scholars", "scholar"], ["theories", "node"]]) {
    assert.equal(evidenceCurationPreviewHref(`/admin/${route}/${id}?section=passages&return_to=%2Fadmin`), `/admin/preview/evidence/${type}/${id}`);
  }
});
test("unrelated, malformed and external edit routes cannot become evidence preview targets", () => {
  for (const href of ["https://example.test/admin/topics/owner?section=passages", "//example.test/admin/topics/owner", "/admin/topics/not-a-uuid?section=passages", "/admin/scholars/d72e3ceb-5524-4647-b690-b9fa8825b19f/relations?section=passages", "/admin/topics/d72e3ceb-5524-4647-b690-b9fa8825b19f?section=identity"]) {
    assert.equal(evidenceCurationPreviewHref(href), "");
  }
});
