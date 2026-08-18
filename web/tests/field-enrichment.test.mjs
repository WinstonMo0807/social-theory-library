import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("field enrichment is explicitly triggered and renders auditable evidence", async () => {
  const source = await readFile(
    new URL("../components/field-enrichment-control.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /核对结构化来源/);
  assert.match(source, /联网核对本页/);
  assert.match(source, /requested_mode: mode/);
  assert.match(source, /visibility: "admin"/);
  assert.match(source, /candidate\.evidence_records\.filter/);
  assert.match(source, /evidence\.supporting_text/);
  assert.match(source, /evidence\.canonical_url/);
  assert.match(source, /部分来源未完成/);
  assert.match(source, /当前值/);
  assert.match(source, /候选值/);
  assert.doesNotMatch(source, /setTimeout|650/);
  assert.doesNotMatch(source, /推荐.*grade|自动接受/);
});


test("existing scholar and theory editors use the shared field control", async () => {
  const [scholars, theories] = await Promise.all([
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(scholars, /targetType="person"/);
  assert.match(scholars, /name: "external_identifier"/);
  assert.match(scholars, /name: "affiliation"/);
  assert.match(scholars, /name: "name_variant"/);
  assert.match(theories, /targetType="knowledge_node"/);
  assert.match(theories, /name: "alias"/);
  assert.match(theories, /name: "discipline"/);
  assert.match(theories, /name: "subdiscipline"/);
});
