import assert from "node:assert/strict";
import test from "node:test";
import { evidenceCurationSavePayload } from "../lib/api/evidence-curation.types.ts";

test("curation saves preserve source references without sending original text or locators", () => {
  const draft = {
    edit_version: "revision-current", title: "Do not overwrite parent title",
    items: [{ id: "reference-1", source_type: "span", source_id: "span-1", group_title: "分组", reason: "关联说明", order: 99,
      text: "Injected editable source text", page_start: 123,
      source: { text: "Protected original", context_before: "Protected context", asset_id: "original-pdf", public_eligible: true } }],
  };
  assert.deepEqual(evidenceCurationSavePayload(draft), {
    edit_version: "revision-current", items: [{ id: "reference-1", source_type: "span", source_id: "span-1", group_title: "分组", reason: "关联说明", order: 0 }],
  });
  assert.equal(draft.items[0].source.text, "Protected original");
  assert.equal(draft.items[0].order, 99, "serialization must not mutate loaded drafts");
});

test("new sources keep exact identities and removing all references is an explicit empty draft", () => {
  assert.deepEqual(evidenceCurationSavePayload({ edit_version: "v2", items: [
    { source_type: "passage", source_id: "p-second", group_title: "", reason: "", order: 17 },
    { source_type: "span", source_id: "s-first", group_title: "", reason: "", order: 3 },
  ] }).items, [
    { source_type: "passage", source_id: "p-second", group_title: "", reason: "", order: 0 },
    { source_type: "span", source_id: "s-first", group_title: "", reason: "", order: 1 },
  ]);
  assert.deepEqual(evidenceCurationSavePayload({ edit_version: "v3", items: [] }), { edit_version: "v3", items: [] });
});
