import { expect, test, type Page } from "@playwright/test";

// Synthetic acceptance scenarios. Authored during implementation; run at unified acceptance.
const id = "41000000-0000-4000-8000-000000000001";
const noteId = "41000000-0000-4000-8000-000000000002";
const projectId = "41000000-0000-4000-8000-000000000003";
const sample = () => ({ id, revision: 1, state: "proposed", created_at: "2026-10-18T00:00:00Z", updated_at: "2026-10-18T00:00:00Z", data: {
  body: "测试中的个人认识", kind: "understanding", sources: [], source_status: "unavailable", usage_scopes: [], history: [],
  origin_note: { id: noteId, available: true, body: "测试原始笔记", quote: "", source_status: "unavailable" },
} });

async function mockMemories(page: Page) {
  const state = { owner: 1, record: sample(), conflict: false, selected: false, deleted: false, requests: [] as Array<{ method: string; path: string; body: Record<string, unknown> }> };
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Test", reading_preferences: {} });
    if (method !== "GET") state.requests.push({ method, path, body: request.postDataJSON() as Record<string, unknown> });
    if (path === "/api/reading/annotations/") return respond({ count: 1, next: null, results: [{ id: noteId, asset: noteId, kind: "note", body_text: "测试原始笔记", quote: "不应作为判断自动填入的引文", orphaned: true, work: { title: "合成测试书目" }, updated_at: state.record.updated_at }] });
    if (path === "/api/reading/research-memories/") {
      if (method === "POST") { const body = request.postDataJSON(); state.record = { ...sample(), data: { ...sample().data, body: body.body, kind: body.kind } }; return respond(state.record, 201); }
      const matching = !state.deleted && (!url.searchParams.get("state") || state.record.state === url.searchParams.get("state"));
      return respond({ count: matching ? 1 : 0, results: matching ? [state.record] : [], next: null, counts: { total: state.deleted ? 0 : 1, proposed: state.record.state === "proposed" ? 1 : 0, confirmed: state.record.state === "confirmed" ? 1 : 0, ignored: 0 } });
    }
    if (path === `/api/reading/research-memories/${id}/usage/`) {
      if (method === "POST") { const body = request.postDataJSON(); state.selected = body.action === "grant"; state.record.revision += 1; return respond(state.record); }
      return respond({ memory_id: id, revision: state.record.revision, targets: [{ kind: "project", id: projectId, title: "合成测试研究", revision: 1, selected: state.selected, enabled: state.selected }] });
    }
    if (path === `/api/reading/research-memories/${id}/`) {
      if (method === "PATCH") {
        const body = request.postDataJSON();
        if (state.conflict || body.expected_revision !== state.record.revision) return respond({ detail: "内容已更新，请保留输入并读取最新版本。" }, 409);
        state.record = { ...state.record, revision: state.record.revision + 1, state: body.state || state.record.state, data: { ...state.record.data, body: body.body || state.record.data.body, kind: body.kind || state.record.data.kind } };
      }
      if (method === "DELETE") { if (request.postDataJSON().expected_revision !== state.record.revision) return respond({ detail: "笔记已有新修订，请核对后再删除。" }, 409); state.deleted = true; return route.fulfill({ status: 204 }); }
      return respond(state.record);
    }
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}

test("confirmation saves a note without granting usage; grant requires an explicit target", async ({ page }) => {
  const state = await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "测试中的个人认识", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" });
  await editor.getByRole("button", { name: "确认并保存笔记" }).click();
  await expect(editor.getByRole("button", { name: "选择使用范围", exact: true })).toBeEnabled();
  expect(state.selected).toBe(false);
  expect(state.requests.at(-1)?.body).toMatchObject({ expected_revision: 1, state: "confirmed" });
  await editor.getByRole("button", { name: "选择使用范围", exact: true }).click();
  const usage = page.getByRole("dialog", { name: "选择笔记使用范围" });
  await expect(usage.getByRole("button", { name: "授权给此范围" })).toBeDisabled();
  await usage.getByLabel("研究或计划").selectOption(`project:${projectId}`);
  await usage.getByRole("button", { name: "授权给此范围" }).click();
  await expect(usage.getByText("已保存使用范围。", { exact: true })).toBeVisible();
  expect(state.requests.at(-1)?.body).toEqual({ expected_revision: 2, action: "grant", targets: [{ kind: "project", id: projectId, expected_revision: 1 }] });
});

test("a new note stays proposed and never copies a source quote into the user's judgment", async ({ page }) => {
  const state = await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "从笔记选择", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "从笔记选择" });
  await dialog.getByRole("radio").click();
  await expect(dialog.getByLabel("待确认的笔记")).toHaveValue("测试原始笔记");
  await dialog.getByRole("button", { name: "保存并继续核对" }).click();
  await expect(page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" })).toBeVisible();
  expect(state.record.state).toBe("proposed");
  expect(state.requests.find(row => row.method === "POST")?.body).toMatchObject({ annotation_id: noteId, body: "测试原始笔记" });
  expect(state.requests.some(row => row.path.includes("/usage/"))).toBe(false);
});

test("conflicting revisions preserve the user's draft until an explicit new baseline is chosen", async ({ page }) => {
  const state = await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "测试中的个人认识", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" });
  await editor.getByLabel("笔记正文").fill("必须保留的本地输入");
  state.record.revision = 2;
  state.record.data.body = "另一处更新的笔记";
  await editor.getByRole("button", { name: "确认并保存笔记" }).click();
  await expect(editor.getByRole("alert")).toContainText("内容已更新");
  await expect(editor.getByLabel("笔记正文")).toHaveValue("必须保留的本地输入");
  await editor.getByRole("button", { name: "保留输入，以最新版本为保存基准" }).click();
  await editor.getByRole("button", { name: "确认并保存笔记" }).click();
  await expect.poll(() => state.record.data.body).toBe("必须保留的本地输入");
  expect(state.requests.at(-1)?.body.expected_revision).toBe(2);
});

test("unavailable source preserves the user's note without a stale reader link", async ({ page }) => {
  await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "测试中的个人认识", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" });
  await editor.getByRole("button", { name: "我的原始笔记", exact: true }).click();
  await expect(editor.getByText("测试原始笔记", { exact: true })).toBeVisible();
  await expect(editor.getByText("原文当前不可用，自己的笔记仍保留。")).toBeVisible();
  await expect(editor.getByRole("link", { name: /打开原始笔记/ })).toHaveCount(0);
});

test("delete uses the reviewed revision instead of deleting a concurrently changed note", async ({ page }) => {
  const state = await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "测试中的个人认识", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" });
  await editor.getByRole("button", { name: "删除这条笔记" }).click();
  state.record.revision = 2;
  await page.getByRole("dialog", { name: "删除这条已保存笔记？" }).getByRole("button", { name: "确认删除" }).click();
  await expect(editor.getByRole("alert")).toContainText("笔记已有新修订");
  expect(state.deleted).toBe(false);
  expect(state.requests.at(-1)?.body.expected_revision).toBe(1);
});

test("a changed cookie owner clears the private list and open editor", async ({ page }) => {
  const state = await mockMemories(page);
  await page.goto("/account/confirmed-notes");
  await page.getByRole("button", { name: "测试中的个人认识", exact: true }).click();
  state.owner = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("button", { name: "测试中的个人认识", exact: true })).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "从笔记形成记忆的主动确认" })).toHaveCount(0);
});
