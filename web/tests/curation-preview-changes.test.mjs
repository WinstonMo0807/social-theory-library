import assert from "node:assert/strict";
import test from "node:test";
import { curationPreviewChanges } from "../components/admin/curation/curation-preview-changes.ts";

const works = { module_id: "scholar-representative-works", display_name: "重要文献", serializer_fields: ["curated.essential_works"], curated_fields: ["curation.essential_work_ids"] };
function payload(draft, published, modules = [works]) {
  return { perspectives: { draft: { available: true, data: draft }, published: { available: true, data: published } }, public_control: { page_tree: [{ page_id: "overview", modules }, { page_id: "works", modules }] } };
}
test("saved curation changes locate only genuinely changed public modules and deduplicate pages", () => {
  const published = { curated: { essential_works: [{ id: "old", title: "旧书" }], key_concepts: ["劳动"] } };
  const draft = { curated: { essential_works: [{ id: "new", title: "新书" }], key_concepts: ["劳动"] } };
  const modules = [works, { module_id: "scholar-concepts", display_name: "关键概念", serializer_fields: ["curated.key_concepts"], curated_fields: ["curation.key_concepts"] }];
  assert.deepEqual(curationPreviewChanges(payload(draft, published, modules), ["curation"]).map(row => [row.module_id, row.pageId]), [["scholar-representative-works", "overview"]]);
  assert.deepEqual(curationPreviewChanges(payload(draft, published, modules), ["timeline"]), []);
});
test("both additions and removal to an empty section remain real changes", () => {
  for (const [draft, published] of [[[{ id: "new" }], []], [[], [{ id: "old" }]]]) {
    assert.equal(curationPreviewChanges(payload({ curated: { essential_works: draft } }, { curated: { essential_works: published } }), ["curation.essential_work_ids"]).length, 1);
  }
});
test("unpublished objects do not turn unavailable published payloads into online content", () => {
  const value = payload({ curated: { essential_works: [{ id: "new" }] } }, { curated: { essential_works: [{ id: "new" }] } });
  value.perspectives.published.available = false;
  assert.equal(curationPreviewChanges(value, ["curation"]).length, 1);
  value.perspectives.draft.available = false;
  assert.deepEqual(curationPreviewChanges(value, ["curation"]), []);
});
test("unknown fields and unsupported page contracts do not invent comparison regions", () => {
  const value = payload({ secret: "draft", curated: { essential_works: [{ id: "new" }] } }, {});
  assert.deepEqual(curationPreviewChanges(value, ["secret"]), []);
  value.perspectives.draft.unsupported_preview_fields = ["curation"];
  assert.deepEqual(curationPreviewChanges(value, ["curation"]), []);
  value.perspectives.draft.unsupported_preview_fields = [];
  value.public_control.page_tree = [{ page_id: "overview", modules: [works], preview: { supported: false } }];
  assert.deepEqual(curationPreviewChanges(value, ["curation"]), []);
});
