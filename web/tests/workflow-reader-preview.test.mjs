import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { publicReaderPreviewHref } from "../components/admin/workflow/file-presentation.ts";

const context = {publication:{public_state:"published",catalog_revision_active:true,active_revision_id:"catalog-active"}};
const file = {current_reader_asset_id:"exact-reader-file"};
const reader = {readable:true,assets:[{id:"exact-reader-file",kind:"normalized",status:"ready",validation_status:"valid"}],availability:{capabilities:[{key:"pdf",source:{catalog_revision_id:"catalog-active",asset_id:"exact-reader-file"}}]}};

test("workflow public Reader points at the validated file in the active public revision", () => {
  assert.equal(publicReaderPreviewHref(context,file,reader),"/reader/exact-reader-file?preview=1");
  assert.equal(publicReaderPreviewHref(context,{current_reader_asset_id:"new-unpublished-file"},reader),"");
  assert.equal(publicReaderPreviewHref(context,file,{...reader,availability:{capabilities:[{key:"pdf",source:{catalog_revision_id:"older-revision",asset_id:"exact-reader-file"}}]}}),"");
});

test("draft, withdrawn, invalid and missing Reader data stay on the protected file preview", () => {
  for(const public_state of ["draft","withdrawn",undefined]) assert.equal(publicReaderPreviewHref({publication:{...context.publication,public_state}},file,reader),"");
  assert.equal(publicReaderPreviewHref({publication:{...context.publication,catalog_revision_active:false}},file,reader),"");
  assert.equal(publicReaderPreviewHref({publication:{...context.publication,active_revision_id:undefined}},file,{...reader,availability:{capabilities:[{key:"pdf",source:{asset_id:"exact-reader-file"}}]}}),"");
  assert.equal(publicReaderPreviewHref(context,file,{...reader,readable:false}),"");
  for(const change of [{kind:"original"},{status:"processing"},{validation_status:"invalid"}]) assert.equal(publicReaderPreviewHref(context,file,{...reader,assets:[{...reader.assets[0],...change}]}),"");
  assert.equal(publicReaderPreviewHref(context,file,{}),"");
  assert.equal(publicReaderPreviewHref({},file,reader),"");
});

test("shared Reader preview disables private records and usage writes without changing manifest access", async () => {
  const [route,shell] = await Promise.all([
    readFile(new URL("../app/reader/[assetId]/page.tsx",import.meta.url),"utf8"),
    readFile(new URL("../components/reader-shell.tsx",import.meta.url),"utf8"),
  ]);
  assert.match(route,/loadReaderManifestResult\(assetId\)/);
  assert.match(route,/readOnlyPreview=\{query\.preview === "1"\}/);
  assert.match(shell,/readerSession\.status === "authenticated" && !readOnlyPreview/);
  assert.match(shell,/!readOnlyPreview \? <UsageTracker/);
  assert.match(shell,/onClick=\{readOnlyPreview \? undefined : trackDownload\}/);
});
