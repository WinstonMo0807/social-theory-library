import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const source = fs.readFileSync(path.join(root, "components", "metadata-review.tsx"), "utf8");
const css = fs.readFileSync(path.join(root, "app", "globals.css"), "utf8");

test("metadata candidates appear beside their corresponding fields", () => {
  for (const field of [
    "title",
    "authors",
    "publisher",
    "publication_place",
    "publication_year",
    "isbn",
    "doi",
    "disciplines",
    "subdisciplines",
    "theory_schools",
    "topics",
  ]) {
    assert.match(source, new RegExp(`inlineCandidates\\(\\"${field}\\"\\)`));
  }
  assert.match(source, /slice\(0, 3\)/);
  assert.match(source, /采用后仍需保存复核内容/);
});

test("inline suggestions preserve review decisions and full evidence access", () => {
  assert.match(source, /onApply=\{applyCandidate\}/);
  assert.match(source, /decideMetadataCandidate\(candidate, \"reject\"\)/);
  assert.match(source, /metadata-candidate-\$\{candidate\.id\}/);
  assert.match(source, /scrollIntoView/);
  assert.match(source, /CandidateCard/);
});

test("inline suggestion layout handles long values and mobile widths", () => {
  assert.match(css, /\.inline-metadata-candidates/);
  assert.match(css, /overflow-wrap: anywhere/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.doesNotMatch(css.match(/\.inline-metadata-candidates[\s\S]*?@media \(max-width: 720px\)/)?.[0] ?? "", /transition:\s*all/);
});
