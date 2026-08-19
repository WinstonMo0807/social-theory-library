import { expect, test, type Page, type Route } from "@playwright/test";

const itemId = "11111111-1111-4111-8111-111111111111";
const workId = "22222222-2222-4222-8222-222222222222";
const editionId = "33333333-3333-4333-8333-333333333333";

const labels = {
  file: "文件与识别",
  work: "作品识别",
  bibliography: "书目与出版",
  contributors: "责任者与身份",
  classification: "社科分类",
  knowledge: "理论、主题与知识关系",
  reader: "文本与阅读文件",
  curation: "策展定位",
  publication: "发布检查与上架",
};

type StepKey = keyof typeof labels;

function workspace(current: StepKey = "work", documentType = "book") {
  const keys = Object.keys(labels) as StepKey[];
  return {
    mode: "intake",
    context: {
      item_id: itemId,
      work_id: workId,
      edition_id: editionId,
      title: documentType === "journal_article" ? "期刊工作流" : "图书工作流",
      filename: "workflow.pdf",
      document_type: documentType,
      publication_state: "ready",
      return_href: "/admin/review",
    },
    workflow: {
      overall_status: "attention",
      current_step: current,
      suggested_next_step: current === "work" ? "bibliography" : "contributors",
      unresolved_count: 2,
      warnings_count: 2,
      blockers_count: 0,
      steps: keys.map((key, index) => ({
        key,
        label: labels[key],
        status: index < keys.indexOf(current) ? "complete" : key === current ? "available" : "pending",
        issues: [],
        summary: key === "work" ? "图书工作流" : "",
        next_action: `处理${labels[key]}`,
      })),
    },
    data: {
      file: { filename: "workflow.pdf", status: "needs_review", validation: "valid", page_count: 12 },
      work: { title: "图书工作流", document_type: documentType, language: "zh-CN", subtitle: "", expected_updated_at: "2026-08-19T10:00:00Z", expected_work_updated_at: "2026-08-19T10:00:00Z" },
      bibliography: documentType === "journal_article"
        ? { publication_year: 2026, journal_title: "社会学研究", volume: "1", issue: "2", page_range: "1-20", doi: "10.1/test" }
        : { publication_year: 2026, publisher: "测试出版社", isbn13: "9780000000000" },
      contributors: { items: [{ person_id: "44444444-4444-4444-8444-444444444444", display_name: "测试作者", role: "author", resolution_state: "confirmed" }] },
      classification: { primary_disciplines: [{ id: "55555555-5555-4555-8555-555555555555", name: "社会学" }], related_disciplines: [], subdisciplines: [], confirmed: false },
      knowledge: { relations: [], confirmed: false },
      reader: { readable: true, original_asset_status: "ready", text_layer_status: "pending", page_label_status: "needs_review", semantic_index_status: "not_indexed", reader_rendition_policy: "auto" },
      curation: { reading_path_placements: [], recommendation_placements: [], skipped: false },
      publication: { publication_state: "ready", preflight: { blockers: [], warnings: [{ message: "OCR 尚未完成", step: "reader" }], background_tasks: ["OCR"] } },
    },
    candidates: {},
    permissions: { can_edit: true, can_publish: true, can_manage_publication: true, can_manage_curation: true },
    queue: { next_item_id: null, return_href: "/admin/review" },
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockWorkflow(page: Page, documentType = "book") {
  let state = workspace("work", documentType);
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/auth/me/") {
      return json(route, {
        id: 1,
        email: "admin@example.test",
        display_name: "Workflow Admin",
        role: "admin",
        access_level: "admin",
        capabilities: ["access_back_office", "can_edit_metadata", "can_edit_draft_authority", "can_publish_work"],
        reading_preferences: {},
      });
    }
    if (path === "/api/auth/token/refresh/") return json(route, {});
    if (path === `/api/catalog/admin/intake/${itemId}/` && method === "GET") return json(route, state);
    if (path === `/api/catalog/admin/intake/${itemId}/sections/work/` && method === "PATCH") {
      calls.push({ path, method, body: request.postDataJSON() });
      state = workspace("bibliography", documentType);
      state.data.work = { ...state.data.work, ...request.postDataJSON().data };
      return json(route, state);
    }
    if (path === `/api/catalog/admin/intake/${itemId}/sections/curation/` && method === "PATCH") {
      calls.push({ path, method, body: request.postDataJSON() });
      state = workspace("publication", documentType);
      state.data.curation = { ...state.data.curation, skipped: true };
      return json(route, state);
    }
    if (path === `/api/ingestion/items/${itemId}/publish/` && method === "POST") {
      calls.push({ path, method, body: request.postDataJSON() });
      return json(route, { work_id: workId, context: { work_id: workId } });
    }
    if (path.startsWith("/api/catalog/admin/")) return json(route, { results: [] });
    return json(route, {});
  });
  return { calls, setState(next: ReturnType<typeof workspace>) { state = next; } };
}

test("focus mode validates, saves, collapses and advances without route navigation", async ({ page }) => {
  const mock = await mockWorkflow(page);
  await page.goto(`/admin/intake/${itemId}#work`);
  await expect(page.getByRole("complementary", { name: "当前馆藏工作步骤" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "后台导航" })).toHaveCount(0);
  await page.getByRole("textbox", { name: "作品题名" }).fill("");
  await page.getByRole("button", { name: "保存并继续" }).click();
  await expect(page).toHaveURL(new RegExp(`#work$`));
  await expect(page.getByText("请填写作品题名。").first()).toBeVisible();
  expect(mock.calls).toHaveLength(0);

  await page.getByRole("textbox", { name: "作品题名" }).fill("修订后的图书工作流");
  await page.getByRole("button", { name: "保存并继续" }).click();
  await expect(page).toHaveURL(new RegExp(`#bibliography$`));
  await expect(page.getByRole("heading", { name: "书目与出版" })).toBeVisible();
  expect(mock.calls[0].path).toContain("sections/work");

  await page.getByRole("button", { name: /作品识别/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`#work$`));
});

test("dirty canonical value survives refresh and leaving prompts", async ({ page }) => {
  await mockWorkflow(page);
  await page.goto(`/admin/intake/${itemId}#work`);
  await page.getByRole("textbox", { name: "副题名" }).fill("尚未保存的副题名");
  await page.getByRole("button", { name: "刷新" }).click();
  await expect(page.getByRole("textbox", { name: "副题名" })).toHaveValue("尚未保存的副题名");
  await expect(page.locator(".workflow-editor-header").getByText(/1 项未保存/)).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("未保存修改");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "退出当前工作" }).click();
  await expect(page).toHaveURL(new RegExp(`#work$`));
});

test("journal fields, curation skip and warning confirmation preserve one editor context", async ({ page }) => {
  const mock = await mockWorkflow(page, "journal_article");
  await page.goto(`/admin/intake/${itemId}#bibliography`);
  await expect(page.getByRole("group", { name: "期刊论文出处" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "期刊名" })).toHaveValue("社会学研究");
  await expect(page.getByRole("textbox", { name: "ISBN-13" })).toHaveCount(0);

  mock.setState(workspace("curation", "journal_article"));
  await page.goto(`/admin/intake/${itemId}#curation`);
  await page.getByRole("button", { name: "暂不策展并继续" }).click();
  await expect(page).toHaveURL(new RegExp(`#publication$`));
  expect(mock.calls.some((call) => call.path.includes("sections/curation"))).toBe(true);
  await page.getByRole("button", { name: "发布并留在当前项" }).click();
  await expect(page.getByRole("dialog", { name: "确认带警告发布" })).toBeVisible();
  await page.getByRole("button", { name: "确认发布" }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/library/works/${workId}#publication$`));
  expect(mock.calls.some((call) => call.path.endsWith("/publish/") && (call.body as { confirm_warnings?: boolean }).confirm_warnings)).toBe(true);
});
