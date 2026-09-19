import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { UploadPublicationResult } from "../components/admin/workflow/upload-publication-result.tsx";
import { publicationPresentation, publicationPublicHref } from "../lib/api/admin-collections.ts";

const render = (publication, editionId = "edition") => renderToStaticMarkup(React.createElement("dl", null, React.createElement(UploadPublicationResult, { editionId, publication })));

test("A01 upload renderer does not turn a saved published command without an active revision into success", () => {
  const publication = { editorial_state: "published", public_state: "unpublished", catalog_revision_active: false, listed_publicly: false, public_url: "", detail: "尚未公开，缺少有效公开修订" };
  const html = render(publication);
  assert.match(html, /尚未公开/);
  assert.doesNotMatch(html, /status-success|href=|已经发布/);
  const conflicting = render({ ...publication, public_state: "published", listed_publicly: true, public_url: "/works/fake" });
  assert.match(conflicting, /公开状态待核实/);
  assert.doesNotMatch(conflicting, /status-success|href=/);
});

test("A02/A03 upload renderer exposes only an active list-eligible public result", () => {
  const active = { public_state: "published", catalog_revision_active: true, listed_publicly: true, active_revision_id: "revision", public_url: "/works/valid", detail: "有效公开修订已生效" };
  const html = render(active);
  assert.match(html, /已公开/);
  assert.match(html, /status-success/);
  assert.match(html, /href="\/works\/valid"/);
  const secondary = render({ ...active, listed_publicly: false, public_url: "" });
  assert.match(secondary, /已公开，作品列表显示其他版本/);
  assert.doesNotMatch(secondary, /href=/);
});

test("A01 unbound source or missing status remains unknown rather than public", () => {
  const malicious = { public_state: "published", catalog_revision_active: true, listed_publicly: true, public_url: "/works/other" };
  const unbound = render(malicious, null);
  assert.match(unbound, /尚未建立出版版本/);
  assert.doesNotMatch(unbound, /status-success|href=/);
  assert.match(render(undefined), /公开状态待核实/);
  assert.equal(publicationPresentation({ public_state: "published" }).tone, "neutral");
});

test("public result href rejects external, malformed and contradictory destinations", () => {
  const base = { public_state: "published", catalog_revision_active: true, listed_publicly: true };
  for (const public_url of ["https://outside.test/works/a", "//outside.test/works/a", "/works/../admin", "/works/\\outside", "/works/a\n"]) assert.equal(publicationPublicHref({ ...base, public_url }), "");
  assert.equal(publicationPublicHref({ ...base, public_state: "unpublished", public_url: "/works/a" }), "");
});

test("actual upload cards use the shared API publication result and label raw state as a command", async () => {
  const source = await readFile(new URL("../components/admin-upload.tsx", import.meta.url), "utf8");
  assert.match(source, /UploadPublicationResult editionId=\{item\.edition\} publication=\{item\.review_data\?\.publication\}/);
  assert.match(source, /published: "发布决定已保存"/);
  assert.doesNotMatch(source, /published: "已经发布"/);
});
