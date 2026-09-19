import assert from "node:assert/strict";
import test from "node:test";
import { adminListHref, adminLoginHref, adminPageNumber, adminTaskScope, preservingAdminRedirect, safeAdminHref, withAdminReturn } from "../lib/admin-route-context.ts";
import { pdfValidationPresentation, publicationPresentation, queueWorkbenchHref, queueWorkspaceApi, selectedQueueItem } from "../lib/api/admin-collections.ts";

test("A01/A02 no active publication result does not become public from an editorial decision", () => {
  assert.equal(publicationPresentation({ editorial_state: "published", public_state: "unpublished", listed_publicly: false }).label, "尚未公开");
  assert.equal(publicationPresentation({ editorial_state: "published" }).label, "公开状态待核实");
  assert.equal(publicationPresentation({ public_state: "publishing" }).tone, "info");
});

test("A03 valid nonprimary revision is distinct from actual public listing eligibility", () => {
  assert.match(publicationPresentation({ public_state: "published", catalog_revision_active: true, listed_publicly: false }).label, /作品列表显示其他版本/);
  assert.equal(publicationPresentation({ public_state: "published", catalog_revision_active: true, listed_publicly: true }).label, "已公开");
});

test("A04 pending, valid, invalid and unknown PDF validation are four distinct presentations", () => {
  assert.deepEqual(["pending", "valid", "invalid", undefined].map((value) => pdfValidationPresentation(value).tone), ["warning", "success", "danger", "neutral"]);
  assert.equal(pdfValidationPresentation("valid").label, "PDF校验通过");
  for (const value of ["pending", "invalid", undefined, "ready"]) assert.doesNotMatch(pdfValidationPresentation(value).label, /通过/);
});

test("A31 legacy item redirects preserve edition, session, filters and nested return location", () => {
  const destination = preservingAdminRedirect("/admin/intake/item-one", { item: "item-one", edition: "edition-two", session: "session-three", source: ["manual", "existing"], return_to: "/admin/review?source=manual&page=2" }, "publication", ["item"]);
  const url = new URL(destination, "https://library.test");
  assert.equal(url.pathname, "/admin/intake/item-one");
  assert.equal(url.searchParams.get("edition"), "edition-two");
  assert.equal(url.searchParams.get("session"), "session-three");
  assert.deepEqual(url.searchParams.getAll("source"), ["manual", "existing"]);
  assert.equal(url.searchParams.get("return_to"), "/admin/review?source=manual&page=2");
  assert.equal(url.searchParams.has("item"), false);
  assert.equal(url.hash, "#publication");
});

test("A31 login round-trip keeps the complete object, query and section", () => {
  const expected = "/admin/library/works/work?edition=edition&return_to=%2Fadmin%2Flibrary%3Fpage%3D2#file";
  const login = new URL(adminLoginHref("/admin/library/works/work", "edition=edition&return_to=%2Fadmin%2Flibrary%3Fpage%3D2", "#file"), "https://library.test");
  assert.equal(login.searchParams.get("next"), expected);
});

test("A11 pagination and filtering preserve unrelated source and return parameters", () => {
  const href = adminListHref("/admin/library", "q=%E9%95%BF%E9%A2%98%E5%90%8D&view=editions&work_id=w&ordering=title&return_to=%2Fadmin%2Freview", { page: 2 });
  const url = new URL(href, "https://library.test");
  assert.equal(url.searchParams.get("page"), "2");
  assert.equal(url.searchParams.get("work_id"), "w");
  assert.equal(url.searchParams.get("q"), "长题名");
  assert.equal(url.searchParams.get("ordering"), "title");
  assert.equal(url.searchParams.get("return_to"), "/admin/review");
});

test("A03/A31 return links keep exact Edition, protect local scope and never pick another object", () => {
  const href = withAdminReturn("/admin/library/works/w?edition=e", "/admin/library?view=editions&page=3", "file");
  const url = new URL(href, "https://library.test");
  assert.equal(url.searchParams.get("edition"), "e");
  assert.equal(url.searchParams.get("return_to"), "/admin/library?view=editions&page=3");
  assert.equal(url.hash, "#file");
  assert.equal(selectedQueueItem([{ id: "edition:a" }, { id: "edition:b" }], "edition:missing"), null);
  assert.equal(selectedQueueItem([{ id: "edition:a" }], ""), null);
  assert.equal(selectedQueueItem([{ id: "edition:a" }, { id: "edition:b" }], "edition:b").id, "edition:b");
});

test("A05/A09 workspace requests use an Edition context even without an UploadItem", () => {
  assert.equal(queueWorkspaceApi({ work_id: "w", edition_id: "e", item_id: null }), "/catalog/admin/library/works/w/?edition=e");
  assert.equal(queueWorkspaceApi({ work_id: null, edition_id: null, item_id: "u" }), "/catalog/admin/intake/u/");
  assert.equal(queueWorkspaceApi({ work_id: null, edition_id: null, item_id: null }), "");
  assert.equal(queueWorkbenchHref({ workbench_url: "" }), "");
});

test("A32 return paths cannot become external redirects or escaped admin paths", () => {
  for (const value of ["https://external.test/admin", "//external.test/admin", "/admin/../login", "/admin\\external", "/admin\n/evil", "javascript:alert(1)"]) assert.equal(safeAdminHref(value), "/admin/library");
  assert.equal(safeAdminHref("/admin/library?view=editions#file"), "/admin/library?view=editions#file");
});

test("page parsing does not trust negative, fractional or unbounded values", () => {
  for (const value of ["0", "-1", "1.2", "NaN", "Infinity", "9007199254740992", null]) assert.equal(adminPageNumber(value), 1);
  assert.equal(adminPageNumber("41"), 41);
});

test("task scope keeps publication, service health and sensitive recovery distinct", () => {
  assert.equal(adminTaskScope("/admin/review").title, "待办与上架");
  assert.equal(adminTaskScope("/admin/library").title, "馆藏");
  assert.equal(adminTaskScope("/admin/scholars/person").title, "知识与关联");
  assert.equal(adminTaskScope("/admin/recommendations").title, "公开展示");
  assert.equal(adminTaskScope("/admin/processing").title, "处理与服务");
  assert.equal(adminTaskScope("/admin/settings").title, "系统管理");
});
