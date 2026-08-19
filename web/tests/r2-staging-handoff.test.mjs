import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  r2BrowserUploadComplete,
  r2StagingOwnsPrimaryStatus,
  r2StagingStatusLabel,
  r2StagingWaitingAction,
} from "../lib/ingestion-staging-status.ts";


test("R2 pre-import states own the visible status without pretending ingestion began", () => {
  assert.equal(r2StagingStatusLabel("uploading"), "正在上传至临时区");
  assert.equal(
    r2StagingStatusLabel("uploaded"),
    "PDF 已上传至临时区，等待导入书库存储",
  );
  assert.equal(r2StagingStatusLabel("importing"), "正在导入正式书库存储");
  assert.equal(r2StagingOwnsPrimaryStatus("uploaded"), true);
  assert.equal(r2StagingOwnsPrimaryStatus("importing"), true);
  assert.equal(r2StagingOwnsPrimaryStatus("imported"), false);
  assert.equal(r2BrowserUploadComplete("uploaded"), true);
  assert.equal(r2StagingWaitingAction("uploaded"), "等待正式入库");
});


test("R2 retry labels match the backend mutation", () => {
  assert.equal(r2StagingStatusLabel("import_failed"), "正式书库存储导入失败");
  assert.equal(r2StagingWaitingAction("import_failed"), "重新导入");
  assert.equal(r2StagingWaitingAction("expired"), "需要重新上传 PDF");
  assert.equal(r2StagingWaitingAction("aborted"), "上传已取消");
});


test("upload cards and Focus Mode use the shared staging grammar", async () => {
  const [upload, workflow] = await Promise.all([
    readFile(new URL("../components/admin-upload.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(upload, /r2StagingOwnsPrimaryStatus/);
  assert.match(upload, /浏览器到 R2 的上传已完成/);
  assert.match(upload, /retryStagingImport\(item\.id\)/);
  assert.match(upload, /重新导入<\/button>/);
  assert.doesNotMatch(upload, /const stagingStatusLabels/);
  assert.match(workflow, /asRecord\(fileGroup\.item\)/);
  assert.match(workflow, /draft\.retry_label/);
  assert.match(workflow, /r2StagingStatusLabel/);
});
