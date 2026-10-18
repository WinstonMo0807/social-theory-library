import { expect, test, type Page } from "@playwright/test";
import type { MappingCommand, MappingData, MappingRevision, MappingState } from "../lib/api/page-mapping.client";

// Synthetic contracts for the later unified acceptance run; no real holding or provider.
const id = (n: number) => `70000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const assetId = id(1), stamp = "2026-10-18T00:00:00Z";
const data = (): MappingData => ({ pages: [1, 2, 3].map(pdf_page => ({ pdf_page, labels: [String(pdf_page)],
  page_type: "body", confirmed: false, note: "", override_manual: false, source: "unknown" })), segments: [], missing: [] });
const revision = (n: number, content: MappingData): MappingRevision => ({ id: id(100 + n), revision: n, origin: "save", created_at: stamp,
  created_by_id: 1, source_fingerprint: "a".repeat(64), restored_from_id: null, applied_at: null,
  applied_asset_id: null, publication: null, data: content });

async function setup(page: Page) {
  const first = revision(1, data());
  const fixture: { state: MappingState; commands: MappingCommand[]; conflict: boolean; owner: number } = {
    state: { asset_id: assetId, asset: { id: assetId, edition_id: id(2), work_id: id(3), title: "合成页码校准文件", page_count: 3,
      sha256: "synthetic", preview_url: "", source_current: true, publication_state: "draft" }, expected_revision: 1,
      source_fingerprint: "a".repeat(64), current: data(), latest: first, history: [first], history_count: 1,
      history_page: 1, history_next_page: null, preceding_revision: null }, commands: [], conflict: false, owner: 1,
  };
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/auth/me/") return respond({ id: fixture.owner, role: "admin", display_name: "Synthetic Admin",
      capabilities: ["access_back_office", "can_edit_metadata", "can_publish_work"], reading_preferences: {} });
    if (url.pathname === `/api/catalog/admin/assets/${assetId}/page-mapping/`) {
      if (route.request().method() === "GET") return respond(url.searchParams.has("revision_id") ? fixture.state.latest : fixture.state);
      const command = route.request().postDataJSON() as MappingCommand;
      fixture.commands.push(command);
      if (fixture.conflict) {
        fixture.state = { ...fixture.state, expected_revision: 2, latest: revision(2, data()) };
        return respond({ detail: "合成页码并发冲突", code: "page_mapping_conflict" }, 409);
      }
      const next = revision(fixture.state.expected_revision + 1, structuredClone(command.data || fixture.state.latest!.data!));
      fixture.state = { ...fixture.state, latest: next, expected_revision: next.revision, history: [next, ...fixture.state.history] };
      return respond(fixture.state);
    }
    return respond({ count: 0, results: [] });
  });
  await page.goto(`/admin/library/assets/${assetId}/page-mapping`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "印刷页与物理页映射" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "PDF 第 1 页印刷标签", exact: true })).toBeVisible();
  return fixture;
}

test("saving changes creates a candidate and preserves the physical page identity", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("textbox", { name: "PDF 第 1 页印刷标签", exact: true }).fill("iv");
  await page.getByRole("button", { name: "保存候选", exact: true }).first().click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0].action).toBe("save");
  expect(fixture.commands[0].data?.pages[0].labels).toEqual(["iv"]);
  expect(fixture.commands[0].data?.pages.map(row => row.pdf_page)).toEqual([1, 2, 3]);
  expect(fixture.state.current.pages[0].labels).toEqual(["1"]);
  expect(fixture.commands[0].source_fingerprint).toBe("a".repeat(64));
});

test("409 retains edits and requires deliberate adoption of the competing revision", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("textbox", { name: "PDF 第 1 页印刷标签", exact: true }).fill("iv");
  fixture.conflict = true;
  await page.getByRole("button", { name: "保存候选", exact: true }).first().click();
  await expect(page.getByRole("textbox", { name: "PDF 第 1 页印刷标签", exact: true })).toHaveValue("iv");
  await expect(page.getByRole("button", { name: "保存候选", exact: true }).first()).toBeDisabled();
  await page.getByRole("button", { name: "保留输入并采用新修订基准", exact: true }).click();
  await page.getByRole("dialog", { name: "保留输入并采用新修订基准", exact: true }).getByRole("button", { name: "采用此基准" }).click();
  fixture.conflict = false;
  await page.getByRole("button", { name: "保存候选", exact: true }).first().click();
  await expect.poll(() => fixture.commands.length).toBe(2);
  expect(fixture.commands[1].expected_revision).toBe(2);
  expect(fixture.commands[1].data?.pages[0].labels).toEqual(["iv"]);
  expect(fixture.commands[1].request_id).not.toBe(fixture.commands[0].request_id);
});

test("segment modal Escape preserves unsaved input until discard is confirmed", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "新建映射段" }).click();
  const dialog = page.getByRole("dialog", { name: "分段页码设置", exact: true });
  await dialog.getByRole("textbox", { name: "分段名称" }).fill("待核对前置页");
  await page.keyboard.press("Escape");
  const discard = page.getByRole("dialog", { name: "放弃此弹窗内的未保存输入？", exact: true });
  await expect(discard).toBeVisible();
  await discard.getByRole("button", { name: "返回编辑" }).click();
  await expect(dialog.getByRole("textbox", { name: "分段名称" })).toHaveValue("待核对前置页");
});

test("missing printed pages remain separate from real PDF pages", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("tab", { name: "校准与检查" }).click();
  await page.getByRole("button", { name: "记录缺页", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "记录缺失的印刷页", exact: true });
  await dialog.getByRole("textbox", { name: "缺失的印刷页标签" }).fill("4");
  await dialog.getByRole("textbox", { name: "缺页原因" }).fill("合成原件缺失此印刷页");
  await dialog.getByRole("checkbox", { name: "已核对原件，确认该印刷页缺失" }).check();
  await dialog.getByRole("button", { name: "保留缺页记录" }).click();
  await page.getByRole("button", { name: "保存候选", exact: true }).first().click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0].data?.pages).toHaveLength(3);
  expect(fixture.commands[0].data?.missing[0]).toMatchObject({ label: "4", confirmed: true });
});

test("spread labels retain one physical page and require a second explicit label", async ({ page }) => {
  const fixture = await setup(page);
  await page.getByRole("checkbox", { name: "此物理页是双页合扫" }).check();
  await page.getByRole("textbox", { name: "第二个印刷页标签", exact: true }).fill("2");
  await expect(page.getByText("两个印刷页共用此 PDF 页。引用显示范围，文字尚未区分左右页。")).toBeVisible();
  await page.getByRole("button", { name: "保存候选", exact: true }).first().click();
  await expect.poll(() => fixture.commands.length).toBe(1);
  expect(fixture.commands[0].data?.pages[0]).toMatchObject({ pdf_page: 1, labels: ["1", "2"], confirmed: false });
  expect(fixture.commands[0].data?.pages).toHaveLength(3);
});
