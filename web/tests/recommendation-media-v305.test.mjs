import assert from "node:assert/strict";
import test from "node:test";
import { adaptApiWork, adaptRecommendationWork } from "../lib/public-data-adapters.ts";

function work() {
  return {
    id: "work-1", title: "图例与书封", document_type: "book", subtitle: "", abstract: "", language: "zh-CN",
    cover: "/api/catalog/works/work-1/cover/?rendition=cover-1",
    recommendation_image: "/api/catalog/works/work-1/recommendation-image/?rendition=hero-1",
    cover_media: { alt_text: "书封说明", renditions: [{ url: "/cover.webp", width: 320, height: 480 }] },
    recommendation_media: { alt_text: "图例说明", renditions: [{ url: "/hero.webp", width: 640, height: 360 }] },
    edition: { id: "edition-1", public_slug: "work-1", publication_year: 2026, contributors: [] },
    theories: [], topics: [],
  };
}

test("catalog cards keep the cover when a separate recommendation image exists", () => {
  const source = work();
  const card = adaptApiWork(source);
  assert.equal(card.coverImage, source.cover);
  assert.equal(card.coverSources[0].url, "/cover.webp");
  assert.equal(card.coverAlt, "书封说明");
});

test("recommendation cards select their own responsive rendition without mutating the source", () => {
  const source = work();
  const original = structuredClone(source);
  const card = adaptRecommendationWork(source);
  assert.equal(card.coverImage, source.recommendation_image);
  assert.equal(card.coverSources[0].url, "/hero.webp");
  assert.equal(card.coverAlt, "图例说明");
  assert.deepEqual(source, original);
});

test("legacy recommendation images do not inherit an unrelated cover srcset", () => {
  const source = { ...work(), recommendation_media: undefined };
  const card = adaptRecommendationWork(source);
  assert.equal(card.coverImage, source.recommendation_image);
  assert.equal(card.coverSources, undefined);
});

test("works without covers can use recommendation renditions as their fallback image", () => {
  const source = { ...work(), cover: "", cover_media: undefined };
  const card = adaptApiWork(source);
  assert.equal(card.coverSources[0].url, "/hero.webp");
  assert.equal(card.coverAlt, "图例说明");
});
