import assert from "node:assert/strict";
import test from "node:test";
import {fileDraftFromWorkspace, pdfValidationPresentation, fileProcessingStatusLabel, fileTextProfileLabel, fileDuplicateLabel, WORKFLOW_GROUPS} from "../components/admin/workflow/file-presentation.ts";

test("file summaries explain processing, text and edition matching in administrator language", () => {
  assert.equal(fileProcessingStatusLabel("received"), "已收到文件，等待处理");
  assert.equal(fileProcessingStatusLabel("unknown"), "处理状态待核实");
  assert.notEqual(fileProcessingStatusLabel("published"), "已公开");
  assert.equal(fileTextProfileLabel(""), "尚未识别");
  assert.equal(fileTextProfileLabel("born_digital"), "PDF 自带文字");
  assert.equal(fileDuplicateLabel("existing_edition"), "文件已关联到当前出版版本");
});
test("PDF only valid is a success, invalid and pending remain distinct", () => {
  assert.equal(pdfValidationPresentation("valid").tone,"success");
  assert.equal(pdfValidationPresentation("invalid").tone,"error");
  assert.equal(pdfValidationPresentation("pending").tone,"pending");
  for (const value of ["passed","failed",null,undefined,true]) assert.notEqual(pdfValidationPresentation(value).tone,"success");
});
test("task groups preserve all existing workbench sections exactly once", () => {
  const keys=WORKFLOW_GROUPS.flatMap(group=>group.steps);
  assert.equal(new Set(keys).size,8);
  assert.deepEqual([...keys].sort(),["work","bibliography","file","reader","contributors","classification","curation","publication"].sort());
});

test("flat real Edition workspace keeps file validation, history and scoped actions",()=>{
  const payload={validation:"invalid",can_supplement:false,can_replace:true,upload_item_id:null,edition_id:"edition-1",file_submit_url:"/catalog/admin/editions/edition-1/files/",file_history:[{id:"old-file",is_current:false}]};
  assert.deepEqual(fileDraftFromWorkspace(payload),{...payload,assets:[]});
  assert.equal(fileDraftFromWorkspace({item:{validation:"pending",retry_label:"重新导入"},assets:[{id:"file-1"}]}).retry_label,"重新导入");
});
