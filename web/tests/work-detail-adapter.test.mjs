import assert from "node:assert/strict";
import test from "node:test";
import { adaptApiWork } from "../lib/public-data-adapters.ts";

// Synthetic contracts for unified acceptance; never a production fallback.
const version = (id, asset) => ({
  id, public_slug: null, version_label: "合成版本", contributors: [],
  publication_year: 2024, language: "en", readable_asset: asset, journal_contents: [],
});
const payload = (edition) => ({
  id: "synthetic-work", document_type: "book", title: "合成作品", subtitle: "合成副题",
  original_title: "Synthetic original", language: "en", abstract: "", theories: [],
  topics: [], edition, editions: [edition], outline: [],
});

test("the selected edition determines detail identity, file and original title", () => {
  const edition = version("synthetic-secondary", { id: "secondary-file", page_count: 0 });
  const work = adaptApiWork(payload(edition));
  assert.equal(work.slug, "synthetic-secondary");
  assert.equal(work.workId, "synthetic-work");
  assert.equal(work.editionId, "synthetic-secondary");
  assert.equal(work.readerHref, "/reader/secondary-file");
  assert.equal(work.originalTitle, "Synthetic original");
  assert.equal(work.subtitle, "合成副题");
});

test("metadata-only versions never borrow another version's readable file", () => {
  const selected = version("metadata-version", null);
  const raw = payload(selected);
  raw.editions.push(version("readable-version", { id: "other-file", page_count: 25 }));
  const work = adaptApiWork(raw);
  assert.equal(work.readerHref, undefined);
  assert.equal(work.pages, 0);
  assert.equal(work.version.id, "metadata-version");
  assert.equal(work.versions[1].readable_asset.id, "other-file");
});

test("published relationships retain their own version identities", () => {
  const raw = payload(version("main-version", null));
  raw.relations = {
    scholars: [], concepts: [], topics: [], reading_paths: [], curations: [], journal_issues: [],
    works: [payload(version("related-version", { id: "related-file", page_count: 8 }))],
  };
  const work = adaptApiWork(raw);
  assert.equal(work.relatedWorks[0].readerHref, "/reader/related-file");
  assert.equal(work.relatedWorks[0].slug, "related-version");
  assert.equal(work.relations.reading_paths.length, 0);
});
