import test from "node:test";
import assert from "node:assert/strict";
import { buildTopicSavePayload } from "../lib/topic-draft.ts";

const baseline = {
  name: "Existing topic", slug: "stable-topic", description: "Existing description",
  coreQuestions: "First question\nSecond question", status: "published",
  primaryWorkIds: ["work-1"], scholarIds: [], featuredPassageIds: ["passage-1"],
  readingPaths: [{ title: "Path", workIds: ["work-2"] }],
  baseCuration: {
    foundational_work_ids: ["work-1"], related_scholar_ids: ["scholar-locked"],
    featured_passage_id: "passage-1", featured_passage_reason: "Human reason",
    featured_passage_evidence: { asset_id: "asset-1", page: 8 },
    reading_paths: [{ id: "path-1", title: "Path", work_ids: ["work-2"], evidence: "Retained" }],
    unknown_metadata: { confirmed: true },
  },
};
const body = {
  name: baseline.name, slug: baseline.slug, description: baseline.description,
  core_questions: ["First question", "Second question"], editorial_status: "published",
  curation: { foundational_work_ids: ["work-1"], related_scholar_ids: [],
    featured_passage_id: "passage-1", featured_passage_reason: "Recomputed candidate",
    featured_passage_evidence: {}, reading_paths: [{ title: "Path", work_ids: ["work-2"] }] },
};

test("unchanged form does not resubmit normalized defaults or provenance", () => {
  assert.deepEqual(buildTopicSavePayload(body, baseline, baseline), {});
});
test("editing questions only sends their titles and order", () => {
  const draft = { ...baseline, coreQuestions: "Second question\nRevised first question" };
  assert.deepEqual(buildTopicSavePayload({ ...body, core_questions: ["Second question", "Revised first question"] }, draft, baseline),
    { core_questions: ["Second question", "Revised first question"] });
});
test("description-only edit preserves the address, status and curation", () => {
  assert.deepEqual(buildTopicSavePayload({ ...body, description: "Revised" }, { ...baseline, description: "Revised" }, baseline),
    { description: "Revised" });
});
test("changed reading selection preserves other curation including hidden path identity", () => {
  const patch = buildTopicSavePayload({ ...body, curation: { ...body.curation, foundational_work_ids: ["work-3"] } },
    { ...baseline, primaryWorkIds: ["work-3"] }, baseline);
  assert.deepEqual(patch, { curation: { ...baseline.baseCuration, foundational_work_ids: ["work-3"] } });
  assert.equal(baseline.baseCuration.foundational_work_ids[0], "work-1");
});
test("an explicit passage replacement changes its complete provenance only", () => {
  const proposed = { ...body.curation, featured_passage_id: "passage-2", featured_passage_reason: "Chosen reason", featured_passage_evidence: { asset_id: "asset-2", page: 9 } };
  assert.deepEqual(buildTopicSavePayload({ ...body, curation: proposed }, { ...baseline, featuredPassageIds: ["passage-2"] }, baseline),
    { curation: { ...baseline.baseCuration, featured_passage_id: "passage-2", featured_passage_reason: "Chosen reason", featured_passage_evidence: { asset_id: "asset-2", page: 9 } } });
});
test("new topics and explicit clearing retain their intended payload", () => {
  assert.equal(buildTopicSavePayload(body, baseline, null), body);
  assert.deepEqual(buildTopicSavePayload({ ...body, core_questions: [] }, { ...baseline, coreQuestions: "" }, baseline), { core_questions: [] });
});
