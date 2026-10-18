import { expect, test, type Page } from "@playwright/test";
import type { CounterTurnData } from "../lib/api/counter-evidence.client";
import type { ProjectData, ResearchRecord } from "../lib/api/research.client";

// Synthetic fixtures only. Execute with the complete site's final acceptance pass.
const projectId = "24000000-0000-4000-8000-000000000001";
const turnId = "24000000-0000-4000-8000-000000000002";
const nextId = "24000000-0000-4000-8000-000000000003";
const evidenceId = "24000000-0000-4000-8000-000000000004";
const timestamp = "2026-10-18T00:00:00Z";
const project = (): ResearchRecord<ProjectData> => ({ id: projectId, revision: 1, created_at: timestamp, updated_at: timestamp,
  data: { title: "合成反证研究", question: "需要检验的合成判断", scope: { kind: "library" }, selections: [], last_turn_id: turnId } });
const turn = (): ResearchRecord<CounterTurnData> => ({ id: turnId, project_id: projectId, revision: 1, generation: 1, status: "completed", created_at: timestamp, updated_at: timestamp,
  data: { question: "需要检验的合成判断", mode: "counterargument", scope: { kind: "library" }, statement: { proposition: "需要检验的合成判断", subject: "合成对象" }, analysis_statement: { proposition: "需要检验的合成判断", subject: "合成对象" }, subclaims: [],
    analysis: [{ id: evidenceId, relation: "insufficient_evidence", status: "needs_review", decision: null,
      reference: { source_status: "available", reference_id: evidenceId, evidence_span_id: evidenceId, asset_id: "synthetic-asset", document_revision_id: "synthetic-revision", pdf_page: 2, title: "仅供测试的来源", authors: ["合成作者"], quote: "这是用于回归测试的原文片段。", reader_url: "/reader/synthetic-asset?page=2&revision=synthetic-revision" },
      candidate_statement: { proposition: "用于测试的候选命题", attribution: "quoted_claim" },
      model_suggestion: { relation: "support", reason: "测试模型仅提出支持候选，不能视为已确认判断。", attribution: "引述", scope_difference: "对象仍待核对" }, reason: "需要核对原文归属" }] } });

async function mockCounter(page: Page) {
  const state = { project: project(), turn: turn(), owner: 1, conflict: false, loseResponse: false,
    writes: [] as Record<string, unknown>[], starts: [] as Record<string, unknown>[], notes: [] as Record<string, unknown>[], queries: [] as URLSearchParams[], receipts: new Set<string>() };
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/auth/me/") return respond({ id: state.owner, role: "reader", display_name: "Synthetic Reader", reading_preferences: {} });
    if (path === `/api/reading/research-projects/${projectId}/`) return respond(state.project);
    if (path === `/api/reading/research-projects/${projectId}/turns/`) {
      if (request.method() === "POST") {
        const body = request.postDataJSON(); state.starts.push(body);
        state.turn = { ...turn(), id: nextId, status: "queued", data: { ...turn().data, question: body.question, statement: body.statement, analysis_statement: body.statement, analysis: [], subclaims: body.subclaims } };
        state.project.revision += 1; state.project.data.last_turn_id = nextId;
        return respond(state.turn, 202);
      }
      state.queries.push(url.searchParams);
      return respond({ count: 1, next: null, results: [state.turn] });
    }
    if ([`/api/reading/research-turns/${turnId}/`, `/api/reading/research-turns/${nextId}/`].includes(path)) return respond(state.turn);
    if (path === `/api/reading/research-turns/${turnId}/decision/`) {
      const body = request.postDataJSON(); state.writes.push(body);
      if (state.receipts.has(body.request_id)) return respond(state.turn);
      if (state.conflict) { state.turn.revision = 2; return respond({ detail: "合成冲突：本轮已有新判断。" }, 409); }
      const row = state.turn.data.analysis![0];
      if (row.decision) row.decision_history = [...(row.decision_history || []), { revision: state.turn.revision, at: timestamp, relation: row.relation, decision: row.decision, action: body.action }];
      row.relation = body.action === "clear" ? "insufficient_evidence" : body.relation;
      row.status = body.action === "clear" ? "needs_review" : "user_confirmed";
      row.decision = body.action === "clear" ? null : { by: "owner", at: timestamp, relation: body.relation, note: body.note, attribution: body.attribution, scope_note: body.scope_note, ...(body.save_as_note ? { memory_id: "synthetic-memory" } : {}) };
      state.turn.revision += 1; state.receipts.add(body.request_id);
      if (state.loseResponse) return respond({ detail: "合成响应丢失，输入保留。" }, 503);
      return respond(state.turn);
    }
    if (path === `/api/reading/research-turns/${turnId}/subclaims/`) {
      const body = request.postDataJSON(); state.writes.push(body);
      if (state.conflict) { state.turn.revision = 2; return respond({ detail: "子命题合成冲突" }, 409); }
      state.turn.data.subclaims = body.subclaims; state.turn.revision += 1; return respond(state.turn);
    }
    if (path === "/api/reading/research-memories/" && request.method() === "POST") { state.notes.push(request.postDataJSON()); return respond({ id: "synthetic-note", revision: 1, state: "proposed", created_at: timestamp, updated_at: timestamp, data: {} }, 201); }
    return respond({ count: 0, results: [], next: null });
  });
  return state;
}
async function openCounter(page: Page) {
  await page.goto(`/account/research/${projectId}/counter-evidence`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "学术反证：检验一个判断", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "纠正分类", exact: true })).toBeVisible();
}
async function openEditor(page: Page) {
  await page.getByRole("button", { name: "纠正分类", exact: true }).click();
  return page.getByRole("region", { name: "纠正证据分类", exact: true });
}

test("counter evidence loads the newest filtered history and keeps model support a candidate", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page);
  expect(state.queries.every(query => query.get("mode") === "counterargument" && query.get("order") === "newest")).toBe(true);
  await expect(page.locator(".stl4-counter-reason")).toContainText("候选分类：支持（待复核）");
  await expect(page.locator(".stl4-counter-reason")).toContainText("不能直接当作作者本人的结论");
  await page.getByRole("navigation", { name: "证据分类" }).getByRole("button", { name: /不同结论/ }).click();
  await expect(page.getByRole("heading", { name: "当前条件下尚未找到不同结论" })).toBeVisible();
  expect(state.writes).toHaveLength(0);
});

test("explicit conditions create a new counterargument turn without rewriting the old proposition", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page);
  await page.getByLabel("需要检验的原命题").fill("新的合成判断");
  await page.getByLabel("地区", { exact: true }).fill("合成地区");
  await page.getByLabel("时间", { exact: true }).fill("合成时期");
  await page.getByLabel("条件（可选）", { exact: true }).fill("明确的合成限制");
  await page.getByRole("button", { name: "重新检索", exact: true }).click();
  await expect.poll(() => state.starts.length).toBe(1);
  expect(state.starts[0]).toMatchObject({ question: "新的合成判断", mode: "counterargument", parent_id: turnId, expected_revision: 1,
    statement: { proposition: "新的合成判断", geographic_scope: "合成地区", temporal_scope: "合成时期", qualifiers: ["明确的合成限制"] } });
  expect(state.starts[0].request_id).toBeTruthy();
});

test("unchanged structured scope survives a new search and owner attribution supersedes the system clue", async ({ page }) => {
  const state = await mockCounter(page);
  state.turn.data.analysis_statement = { proposition: "需要检验的合成判断", geographic_scope: { label: "合成地域", code: "synthetic" }, temporal_scope: { start: 2001, end: 2010 }, qualifiers: ["条件一", "条件二"] };
  const row = state.turn.data.analysis![0]; row.status = "user_confirmed"; row.relation = "support"; row.decision = { by: "owner", at: timestamp, attribution: "author_claim", note: "本人核对了完整上下文" };
  await openCounter(page);
  await expect(page.getByLabel("地区", { exact: true })).toHaveValue("合成地域");
  await expect(page.getByLabel("时间", { exact: true })).toHaveValue("2001–2010");
  await expect(page.locator(".stl4-counter-reason")).toContainText("本人归属判断：作者本人的主张");
  await expect(page.locator(".stl4-counter-reason")).not.toContainText("不能直接当作作者本人的结论");
  await page.getByRole("button", { name: "重新检索", exact: true }).click();
  await expect.poll(() => state.starts.length).toBe(1);
  expect(state.starts[0].statement).toMatchObject({ geographic_scope: { label: "合成地域", code: "synthetic" }, temporal_scope: { start: 2001, end: 2010 }, qualifiers: ["条件一", "条件二"] });
});

test("classification correction requires a reason and preserves draft on 409", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page); const editor = await openEditor(page);
  await editor.getByLabel("不相关", { exact: true }).check();
  await expect(editor.getByRole("button", { name: "确认并保存" })).toBeDisabled();
  await editor.getByLabel("更正原因（必填）").fill("合成理由：关键词相似，但对象不同。");
  await editor.getByLabel("观点归属").selectOption("quoted_claim");
  state.conflict = true; await editor.getByRole("button", { name: "确认并保存" }).click();
  await expect(editor.getByRole("button", { name: "确认并保存" })).toBeDisabled();
  await expect(editor.getByLabel("更正原因（必填）")).toHaveValue("合成理由：关键词相似，但对象不同。");
  await editor.getByRole("button", { name: "核对最新结果后沿用输入" }).click();
  state.conflict = false; await editor.getByRole("button", { name: "确认并保存" }).click();
  await expect(editor).toHaveCount(0);
  expect(state.writes[1]).toMatchObject({ action: "confirm", relation: "unrelated", expected_revision: 2, attribution: "quoted_claim", save_as_note: false });
});

test("structured spread mapping keeps PDF location without inferring a spread from a label", async ({ page }) => {
  const state = await mockCounter(page), ref = state.turn.data.analysis![0].reference;
  ref.printed_label = "16–17"; ref.printed_labels = ["16", "17"]; ref.printed_label_precision = "spread";
  await openCounter(page);
  await expect(page.locator(".stl4-counter-evidence-copy")).toContainText("书内页码 16、17 · PDF 第 2 页 · 双页扫描，请核对具体印刷页");
  ref.printed_labels = undefined; ref.printed_label_precision = "unknown";
  await page.getByRole("button", { name: "重新读取", exact: true }).click();
  await expect(page.locator(".stl4-counter-evidence-copy")).toContainText("书内页码 16–17 · PDF 第 2 页");
  await expect(page.locator(".stl4-counter-evidence-copy")).not.toContainText("双页扫描");
});

test("multiple dirty forms use one navigation confirmation and canceled navigation retains both drafts", async ({ page }) => {
  await mockCounter(page); await openCounter(page); const editor = await openEditor(page);
  await page.getByLabel("需要检验的原命题").fill("尚未提交的命题草稿");
  await editor.getByLabel("更正原因（必填）").fill("尚未提交的分类草稿");
  let dialogs = 0;
  page.on("dialog", async dialog => { dialogs += 1; await dialog.dismiss(); });
  await page.getByRole("link", { name: "比较当前研究选材", exact: true }).click();
  await expect(page.getByLabel("需要检验的原命题")).toHaveValue("尚未提交的命题草稿");
  await expect(editor.getByLabel("更正原因（必填）")).toHaveValue("尚未提交的分类草稿");
  expect(dialogs).toBe(1);
});

test("a lost classification response retries the same request and saves the explicit note once", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page); const editor = await openEditor(page);
  await editor.getByLabel("更正原因（必填）").fill("明确保存为本人待确认笔记的判断。");
  await editor.getByRole("checkbox", { name: /同时保存到我的笔记/ }).check();
  state.loseResponse = true; await editor.getByRole("button", { name: "确认并保存" }).click();
  await expect(editor.getByRole("alert")).toContainText("合成响应丢失");
  state.loseResponse = false; await editor.getByRole("button", { name: "确认并保存" }).click();
  await expect(editor).toHaveCount(0);
  expect(state.writes).toHaveLength(2);
  expect(state.writes[0].request_id).toBe(state.writes[1].request_id);
  expect(state.writes[0]).toMatchObject({ save_as_note: true, expected_revision: 1 });
  expect(state.receipts.size).toBe(1);
  expect(state.notes).toHaveLength(0); // The decision endpoint performs the atomic note write.
});

test("withdrawn evidence hides old snippets and permits clearing only the owner's decision", async ({ page }) => {
  const state = await mockCounter(page), row = state.turn.data.analysis![0];
  row.reference.source_status = "unavailable"; row.reference.quote = "不应回显的撤回来源片段"; row.status = "source_unavailable"; row.relation = "different_conclusion";
  row.decision = { by: "owner", at: timestamp, note: "前次本人判断仍保留" };
  await page.goto(`/account/research/${projectId}/counter-evidence`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("不应回显的撤回来源片段", { exact: true })).toHaveCount(0);
  await expect(page.locator(".stl4-counter-tag")).toHaveText("待复核");
  await page.getByRole("button", { name: "查看前次判断" }).click();
  const editor = page.getByRole("region", { name: "纠正证据分类" });
  await expect(editor).toContainText("前次本人判断仍保留");
  await expect(editor.getByRole("button", { name: "确认并保存" })).toBeDisabled();
  await editor.getByRole("button", { name: "撤回本人判断", exact: true }).click();
  await editor.getByRole("button", { name: "确认撤回本人判断" }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0]).toMatchObject({ action: "clear", id: evidenceId, expected_revision: 1 });
  expect(state.turn.data.analysis![0].decision_history?.[0].decision?.note).toBe("前次本人判断仍保留");
});

test("canceling classification and note-dialog dismissal keeps unsaved input", async ({ page }) => {
  await mockCounter(page); await openCounter(page); const editor = await openEditor(page);
  await editor.getByLabel("更正原因（必填）").fill("不可静默丢失的分类草稿");
  page.once("dialog", dialog => dialog.dismiss());
  await editor.getByRole("button", { name: "取消", exact: true }).click();
  await expect(editor.getByLabel("更正原因（必填）")).toHaveValue("不可静默丢失的分类草稿");
  page.once("dialog", dialog => dialog.accept());
  await editor.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "保存到我的笔记", exact: true }).click();
  const note = page.getByRole("dialog", { name: "保存到我的笔记", exact: true });
  await note.getByLabel("本人笔记").fill("不可静默丢失的笔记草稿");
  page.once("dialog", dialog => dialog.dismiss()); await page.keyboard.press("Escape");
  await expect(note.getByLabel("本人笔记")).toHaveValue("不可静默丢失的笔记草稿");
});

test("subclaim conflict retains explicit IDs and does not change the analyzed original statement", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page);
  await page.getByRole("button", { name: "拆分与检验子命题", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "拆分与检验子命题" });
  await dialog.getByRole("button", { name: /添加子命题/ }).click();
  await dialog.getByLabel("子命题 1", { exact: true }).fill("明确拆分的合成子命题");
  state.conflict = true; await dialog.getByRole("button", { name: "保存子命题" }).click();
  await expect(dialog.getByLabel("子命题 1", { exact: true })).toHaveValue("明确拆分的合成子命题");
  await dialog.getByRole("button", { name: "核对最新轮次后沿用拆分" }).click();
  state.conflict = false; await dialog.getByRole("button", { name: "保存子命题" }).click();
  await expect(dialog.getByRole("button", { name: "检验此子命题" })).toBeEnabled();
  expect(state.writes[0].subclaims).toEqual(state.writes[1].subclaims);
  expect(state.turn.data.analysis_statement?.proposition).toBe("需要检验的合成判断");
});

test("same-owner explicit session revalidation clears drafts and restores usable actions", async ({ page }) => {
  const state = await mockCounter(page); await openCounter(page); const editor = await openEditor(page);
  await editor.getByLabel("更正原因（必填）").fill("会话变化前的私人草稿");
  await page.evaluate(() => window.dispatchEvent(new Event("social-theory-library:session-change")));
  await expect(editor).toHaveCount(0);
  const next = await openEditor(page);
  await expect(next.getByLabel("更正原因（必填）")).toHaveValue("");
  await next.getByLabel("更正原因（必填）").fill("重新验证后的本人判断");
  await next.getByRole("button", { name: "确认并保存" }).click();
  await expect.poll(() => state.writes.length).toBe(1);
});
