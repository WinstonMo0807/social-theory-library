import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("field enrichment is explicitly triggered and renders auditable evidence", async () => {
  const source = await readFile(
    new URL("../components/admin/curation/curation-field-assistant.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /onClick=\{\(\) => void lookup\(\)\}/);
  assert.match(source, /field-assistant\/lookup/);
  assert.match(source, /candidate\.evidence\.map/);
  assert.match(source, /evidence\.summary/);
  assert.match(source, /evidence\.url/);
  assert.match(source, /CandidateDecisionBar/);
  assert.match(source, /action\.payload\.reason/);
  assert.doesNotMatch(source, /在\$\{label\}字段确认不采用/);
  assert.doesNotMatch(source, /setTimeout|650/);
  assert.doesNotMatch(source, /推荐.*grade|自动接受/);
});


test("existing scholar and theory editors use the shared field control", async () => {
  const [scholars, theories] = await Promise.all([
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(scholars, /targetType="person"/);
  assert.match(scholars, /fieldName="external_identifier"/);
  assert.match(scholars, /fieldName="affiliation"/);
  assert.match(scholars, /fieldName="name_variant"/);
  assert.match(theories, /targetType="knowledge_node"/);
  assert.match(theories, /fieldName="alias"/);
  assert.match(theories, /fieldName="discipline"/);
  assert.match(theories, /fieldName="subdiscipline"/);
});
