import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("candidate review uses one evidence/status shell for both candidate domains", async () => {
  const source = await readFile(
    new URL("../components/candidate-review.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /field_enrichment/);
  assert.match(source, /query_lexicon/);
  assert.match(source, /candidate-review/);
  assert.match(source, /evidence_records/);
  assert.match(source, /candidate-review\/\$\{candidate\.review_kind\}/);
  assert.match(source, /action: \"accept\" \| \"reject\"/);
});
