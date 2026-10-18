import { expect, test, type Page } from "@playwright/test";
import type { OutlineEditNode, OutlineRevision, OutlineState } from "../lib/api/curation-workspace.client";
import type { OutlineNode } from "../lib/api/document-outline";

// Synthetic HTTP/UI contracts only; authored for the later unified acceptance stage.
// No real manuscripts or production library data are used by this fixture.
const uuid = (value: number) => `50000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const assetId = uuid(1), documentId = uuid(2), timestamp = "2026-10-18T00:00:00Z";
const node = (id: number, title: string, page: number, parent: number | null = null): OutlineNode => ({
  id: uuid(id), parent_id: parent ? uuid(parent) : null, title, chapter_title: title, index: page,
  pdf_page: page, printed_label: String(page), contents_page: null, level: parent ? 2 : 1,
  source: "pdf_bookmark", calibration_status: "native", pdf_position: [], normalized_position: [],
});
const initialNodes = () => [node(11, "合成第一章", 3), node(12, "合成第一节", 4, 11), node(21, "合成第二章", 3), node(22, "合成第二节", 5, 21)];
const revision = (number: number, nodes: OutlineNode[], active = false): OutlineRevision => ({
  id: uuid(100 + number), revision: number, asset_id: assetId, document_revision_id: documentId,
  origin: active ? "adopted" : "manual", is_active: active, reviewed: active, diagnostics: [],
  created_at: timestamp, node_count: nodes.length, nodes,
});
type Command = { action: "edit" | "adopt" | "restore"; expected_revision: number; request_id: string; base_revision_id?: string; revision_id?: string; nodes?: OutlineEditNode[] };

async function mockOutline(page: Page, nodes = initialNodes()) {
  const first = revision(1, nodes, true);
  const state: { data: OutlineState; commands: Command[]; conflict: boolean; owner: number; revisions: Map<string, OutlineRevision> } = {
    data: { asset_id: assetId, expected_revision: 1, active: first, latest: first, history: [first], history_count: 1,
      history_page: 1, history_next_page: null, jobs: [], asset: { id: assetId, edition_id: uuid(3), work_id: uuid(4), title: "合成目录校准文件",
        page_count: 8, sha256: "synthetic-file-checksum", preview_url: "", reader_url: "", source_current: true } },
    commands: [], conflict: false, owner: 1, revisions: new Map([[first.id, first]]),
  };
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/auth/me/") return respond({ id: state.owner, role: "admin", display_name: "Synthetic Admin", capabilities: ["access_back_office", "can_edit_metadata", "can_retry_jobs"], reading_preferences: {} });
    if (url.pathname === `/api/catalog/admin/assets/${assetId}/outline/`) {
      if (route.request().method() === "GET") return respond(url.searchParams.get("revision_id") ? state.revisions.get(url.searchParams.get("revision_id")!) : state.data);
      const command = route.request().postDataJSON() as Command;
      state.commands.push(command);
      if (state.conflict) {
        const competing = revision(2, initialNodes());
        state.data = { ...state.data, expected_revision: 2, latest: competing, history: [competing, first], history_count: 2 };
        state.revisions.set(competing.id, competing);
        return respond({ detail: "合成并发修订冲突，输入应保留。", code: "outline_conflict" }, 409);
      }
      const selected = command.revision_id ? state.revisions.get(command.revision_id) : undefined;
      const prior = new Map((state.data.latest?.nodes || []).map(row => [row.id, row]));
      const nextNodes: OutlineNode[] = command.nodes ? command.nodes.map(row => ({ ...prior.get(row.id), ...row,
        id: row.id!, chapter_title: row.title, index: row.pdf_page || 1, printed_label: row.printed_label || "", level: row.parent_id ? 2 : 1 })) : structuredClone(selected?.nodes || []);
      const next = revision(state.data.expected_revision + 1, nextNodes, command.action !== "edit");
      state.revisions.set(next.id, next);
      state.data = { ...state.data, expected_revision: next.revision, latest: next, active: command.action === "edit" ? state.data.active : next,
        history: [next, ...state.data.history], history_count: state.data.history_count + 1 };
      return respond(state.data);
    }
    return respond({ count: 0, results: [] });
  });
  return state;
}

async function openOutline(page: Page) {
  await page.goto(`/admin/library/assets/${assetId}/outline`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("region", { name: "目录树", exact: true })).toBeVisible();
}
const save = (page: Page) => page.getByRole("button", { name: "保存修改", exact: true }).first().click();
async function confirmNode(page: Page) {
  await page.getByRole("button", { name: "确认此节点", exact: true }).click();
  await page.getByRole("dialog", { name: "确认目录节点", exact: true }).getByRole("button", { name: "确认", exact: true }).click();
}

test("editing and confirming one node preserves the unreviewed siblings", async ({ page }) => {
  const nodes = initialNodes();
  nodes[1].calibration_status = "generated"; nodes[2].calibration_status = "matched";
  const state = await mockOutline(page, nodes);
  await openOutline(page);
  await page.getByRole("textbox", { name: "标题", exact: true }).fill("只修改第一章");
  await confirmNode(page);
  await save(page);
  await expect.poll(() => state.commands.length).toBe(1);
  expect(state.commands[0].base_revision_id).toBe(uuid(101));
  expect(state.commands[0].nodes?.map(row => row.calibration_status)).toEqual(["confirmed", "generated", "matched", "native"]);
  expect(state.commands[0].nodes?.map(row => row.pdf_page)).toEqual([3, 4, 3, 5]);
  expect(state.data.active?.id).toBe(uuid(101));
  await expect(page.getByRole("button", { name: "采用目录", exact: true })).toBeDisabled();
});

test("409 preserves input and can save a separate revision against the original base without adopting it", async ({ page }) => {
  const state = await mockOutline(page);
  await openOutline(page);
  await page.getByRole("textbox", { name: "标题", exact: true }).fill("冲突后必须保留的输入");
  await page.getByRole("spinbutton", { name: "PDF 物理页", exact: true }).fill("6");
  state.conflict = true;
  await save(page);
  await expect(page.getByText("合成并发修订冲突，输入应保留。", { exact: false })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("冲突后必须保留的输入");
  await expect(page.getByRole("spinbutton", { name: "PDF 物理页", exact: true })).toHaveValue("6");
  await expect(page.getByRole("button", { name: "保存修改", exact: true }).first()).toBeDisabled();
  await page.getByRole("button", { name: "放弃当前输入并载入最新目录", exact: true }).click();
  await page.getByRole("dialog", { name: "载入其他修订", exact: true }).getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("冲突后必须保留的输入");
  expect(state.commands).toHaveLength(1);
  state.conflict = false;
  await page.getByRole("button", { name: "保留输入另存为新修订", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "保留输入另存为新修订", exact: true });
  await expect(dialog).toContainText("不会自动采用本次输入");
  expect(state.commands).toHaveLength(1);
  await dialog.getByRole("button", { name: "确认", exact: true }).click();
  await expect.poll(() => state.commands.length).toBe(2);
  expect(state.commands[1]).toMatchObject({ action: "edit", expected_revision: 2, base_revision_id: uuid(101) });
  expect(state.commands[1].nodes?.[0]).toMatchObject({ title: "冲突后必须保留的输入", pdf_page: 6 });
  expect(state.data.active?.id).toBe(uuid(101));
  expect(state.revisions.has(uuid(102))).toBe(true);
  await expect.poll(() => state.data.latest?.revision).toBe(3);
});

test("a source candidate only fills a node and requires explicit review before adoption", async ({ page }) => {
  const nodes = initialNodes();
  nodes[0].candidate_sources = [{ source: "printed_contents", title: "合成印刷目录候选", pdf_page: 6, printed_label: "iii", contents_page: 2, normalized_position: [0.2, 0.4] }];
  const state = await mockOutline(page, nodes);
  await openOutline(page);
  await page.getByRole("button", { name: "填入节点", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("合成印刷目录候选");
  await expect(page.getByRole("spinbutton", { name: "PDF 物理页", exact: true })).toHaveValue("6");
  await save(page);
  await expect.poll(() => state.commands.length).toBe(1);
  expect(state.commands[0].nodes?.[0]).toMatchObject({ calibration_status: "unverified", normalized_position: [0.2, 0.4], clear_position: true });
  await expect(page.getByRole("button", { name: "采用目录", exact: true })).toBeDisabled();
  await confirmNode(page);
  await save(page);
  await expect.poll(() => state.commands.length).toBe(2);
  expect(state.commands[1].nodes?.[0].calibration_status).toBe("confirmed");
  expect(state.commands.every(command => command.action === "edit")).toBe(true);
});

test("saving a checked revision does not adopt it until the separate adoption confirmation", async ({ page }) => {
  const state = await mockOutline(page);
  await openOutline(page);
  await page.getByRole("textbox", { name: "标题", exact: true }).fill("合成修订后的标题");
  await confirmNode(page); await save(page);
  await expect.poll(() => state.data.latest?.revision).toBe(2);
  expect(state.data.active?.revision).toBe(1);
  expect(state.commands.map(command => command.action)).toEqual(["edit"]);
  await page.getByRole("button", { name: "采用目录", exact: true }).click();
  expect(state.commands).toHaveLength(1);
  await page.getByRole("dialog", { name: "采用当前目录", exact: true }).getByRole("button", { name: "确认", exact: true }).click();
  await expect.poll(() => state.commands.map(command => command.action)).toEqual(["edit", "adopt"]);
  expect(state.commands[1]).toMatchObject({ revision_id: uuid(102), expected_revision: 2 });
  expect(state.revisions.has(uuid(101))).toBe(true);
  await expect.poll(() => state.data.active?.revision).toBe(3);
});

test("moving a sibling moves its subtree while preserving distinct nodes on the same physical page", async ({ page }) => {
  const state = await mockOutline(page);
  await openOutline(page);
  await page.getByRole("button", { name: "下移节点", exact: true }).click();
  await save(page);
  await expect.poll(() => state.commands.length).toBe(1);
  const saved = state.commands[0].nodes!;
  expect(saved.map(row => row.id)).toEqual([uuid(21), uuid(22), uuid(11), uuid(12)]);
  expect(saved.map(row => row.parent_id)).toEqual([null, uuid(21), null, uuid(11)]);
  expect(saved.filter(row => row.pdf_page === 3).map(row => row.id)).toEqual([uuid(21), uuid(11)]);
  await page.getByRole("checkbox", { name: "同页多节点", exact: true }).check();
  const tree = page.getByRole("region", { name: "目录树", exact: true });
  await expect(tree.getByRole("checkbox", { name: "选择 合成第一章", exact: true })).toBeVisible();
  await expect(tree.getByRole("checkbox", { name: "选择 合成第二章", exact: true })).toBeVisible();
  await expect(tree.getByRole("checkbox", { name: "选择 合成第一节", exact: true })).toHaveCount(0);
});

test("an explicit account change removes the former account's unsaved outline draft", async ({ page }) => {
  const state = await mockOutline(page);
  await openOutline(page);
  await page.getByRole("textbox", { name: "标题", exact: true }).fill("前一账号尚未保存的目录");
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("合成第一章");
  await expect(page.getByRole("button", { name: "保存修改", exact: true }).first()).toBeDisabled();
  expect(state.commands).toHaveLength(0);
});
