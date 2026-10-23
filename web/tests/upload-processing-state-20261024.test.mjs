import assert from "node:assert/strict";
import test from "node:test";
import { activeUploadStage, uploadNeedsRefresh, uploadSnapshotTime } from "../lib/ingestion-staging-status.ts";

// Deferred acceptance: authored during implementation, not executed this round.
test("an accepted upload keeps following an independently paused task and rejects older stage snapshots", () => {
  const original = {status:"needs_review", updated_at:"2026-10-24T08:00:00Z"};
  const paused = {...original, document_stages:{ocr:{job_id:"ocr-job", source:"processing_job", status:"paused", progress:40, updated_at:"2026-10-24T08:05:00Z"}}};
  assert.equal(uploadNeedsRefresh({status:"extracting"}), true);
  assert.equal(uploadNeedsRefresh(original), false);
  assert.equal(uploadNeedsRefresh(paused), true);
  assert.equal(activeUploadStage(paused)?.status, "paused");
  assert.ok(uploadSnapshotTime(paused) > uploadSnapshotTime(original));
  const finished = {...paused, document_stages:{ocr:{...paused.document_stages.ocr, status:"succeeded", updated_at:"2026-10-24T08:06:00Z"}}};
  assert.equal(uploadNeedsRefresh(finished), false);
  assert.ok(uploadSnapshotTime(finished) > uploadSnapshotTime(paused));
});
