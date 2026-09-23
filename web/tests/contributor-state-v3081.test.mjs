import test from "node:test";
import assert from "node:assert/strict";
import { fillContributor } from "../components/admin/workflow/contributor-state.ts";

test("linking a created translator fills the existing row and preserves the author", () => {
  const rows = [{ id: "author-row", person_id: "rosa", display_name: "罗萨", role: "author" },
    { id: "translator-row", person_id: null, display_name: "郑作彧", role: "translator", note: "人工备注" }];
  const selected = fillContributor(rows, { id: "zheng", name: "郑作彧" }, "translator");
  assert.equal(selected.length, 2);
  assert.equal(selected[0], rows[0]);
  assert.equal(selected[1].id, "translator-row");
  assert.equal(selected[1].note, "人工备注");
  assert.equal(selected[1].person_id, "zheng");
  assert.deepEqual(fillContributor(selected, { id: "zheng", name: "郑作彧" }, "translator"), selected);
  assert.equal(rows[1].person_id, null);
});

test("same-name distinct people remain selectable and roles are independent", () => {
  const rows = [{ person_id: "one", display_name: "王明", role: "author" }, { person_id: null, display_name: "王明", role: "translator" }];
  const result = fillContributor(rows, { id: "two", name: "王明" }, "translator");
  assert.equal(result[0].person_id, "one");
  assert.equal(result[1].person_id, "two");
  assert.equal(result.length, 2);
});
