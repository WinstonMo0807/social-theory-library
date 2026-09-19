import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api/catalog";
const editors = [
  { kind: "scholars", id: "30600000-0000-4000-8000-000000000201", label: "页面简介", field: "short_description", save: "保存学者", route: (id: string) => `/admin/scholars/${id}` },
  { kind: "topics", id: "30600000-0000-4000-8000-000000000202", label: "主题说明", field: "description", save: "保存", route: (id: string) => `/admin/topics/${id}` },
  { kind: "disciplines", id: "", label: "卡片说明", field: "description", save: "保存学科", route: (id: string) => `/admin/disciplines?discipline=${id}` },
  { kind: "subdisciplines", id: "", label: "页面说明", field: "description", save: "保存子学科", route: (id: string) => `/admin/subdisciplines?subdiscipline=${id}` },
  { kind: "theory-system/nodes", id: "30600000-0000-4000-8000-000000000204", label: "简介", field: "summary", save: "保存为编辑草稿", route: (id: string) => `/admin/theories?node=${id}` },
  { kind: "theory-system/reading-paths", id: "30600000-0000-4000-8000-000000000205", label: "路径介绍", field: "introduction", save: "保存阅读路径", route: (id: string) => `/admin/reading-paths?path=${id}` },
];

async function configure(context: BrowserContext) {
  await context.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'http://127.0.0.1:8105/api'});` }));
}

async function login(page: Page, role: string) {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

for (const entry of editors) {
  test(`A14 ${entry.kind}: two real administrator sessions protect input and public content`, async ({ browser, page, baseURL }, testInfo) => {
    test.setTimeout(120_000);
    expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
    await configure(page.context());
    await login(page, "owner");
    let id = entry.id;
    if (entry.kind === "subdisciplines") {
      const disciplines = await (await page.request.get(`${api}/admin/disciplines/`)).json();
      const parent = disciplines.results.find((row: { editorial_status: string }) => row.editorial_status === "published");
      expect(parent).toBeTruthy();
      const csrf = (await page.context().cookies(api)).find((cookie) => cookie.name === "csrftoken")?.value;
      expect(csrf).toBeTruthy();
      const response = await page.request.post(`${api}/admin/subdisciplines/`, {
        headers: { "X-CSRFToken": csrf!, Origin: baseURL!, Referer: `${baseURL}/admin/subdisciplines` },
        data: { name: "双人编辑子学科", slug: `two-editors-${Date.now()}`, discipline: parent.id, description: "未修改的公开说明", editorial_status: "published" },
      });
      expect(response.status(), await response.text()).toBe(201);
      id = (await response.json()).id;
    } else if (!id) {
      const response = await page.request.get(`${api}/admin/${entry.kind}/`);
      expect(response.status()).toBe(200);
      const rows = (await response.json()).results;
      const selected = rows.find((row: { editorial_status: string }) => row.editorial_status === "published");
      expect(selected, "requires a real published fixture, never a fallback object").toBeTruthy();
      id = selected.id;
    }
    const endpoint = `${api}/admin/${entry.kind}/${id}/`;
    const beforeResponse = await page.request.get(endpoint);
    expect(beforeResponse.status()).toBe(200);
    const before = await beforeResponse.json();
    const publicEndpoint = `${api}/${entry.kind}/${before.slug}/`;
    const publicBeforeResponse = await page.request.get(publicEndpoint);
    expect(publicBeforeResponse.status()).toBe(200);
    const publicBefore = await publicBeforeResponse.json();
    expect(publicBefore).toHaveProperty(entry.field);
    const secondContext = await browser.newContext({ baseURL });
    await configure(secondContext);
    const second = await secondContext.newPage();
    try {
      await login(second, "curator");
      const route = entry.route(id);
      await Promise.all([page.goto(route), second.goto(route)]);
      const firstInput = page.getByRole("textbox", { name: entry.label, exact: true });
      const secondInput = second.getByRole("textbox", { name: entry.label, exact: true });
      await expect(firstInput).toHaveValue(before[entry.field]);
      await expect(secondInput).toHaveValue(before[entry.field]);
      const firstText = `管理员一已保存 ${entry.kind} ${Date.now()}`;
      const secondText = `管理员二需要保留的输入 ${entry.kind}`;
      await firstInput.fill(firstText);
      await secondInput.fill(secondText);
      const firstWrite = page.waitForResponse((r) => r.url() === endpoint && r.request().method() === "PATCH");
      await page.getByRole("button", { name: entry.save, exact: true }).click();
      const savedResponse = await firstWrite;
      expect(savedResponse.status(), await savedResponse.text()).toBe(202);
      expect(savedResponse.request().headers()["if-match"]).toBe(before.edit_version);
      const saved = await savedResponse.json();
      expect(saved[entry.field]).toBe(firstText);

      const secondWrite = second.waitForResponse((r) => r.url() === endpoint && r.request().method() === "PATCH");
      await second.getByRole("button", { name: entry.save, exact: true }).click();
      const refused = await secondWrite;
      expect(refused.status(), await refused.text()).toBe(409);
      expect(refused.request().headers()["if-match"]).toBe(before.edit_version);
      await expect(secondInput).toHaveValue(secondText);
      await expect(second.getByText("这条资料已被修改。你的输入没有提交，请先核对最新内容再保存。", { exact: true })).toBeVisible();
      const recoveryLink = second.getByRole("link", { name: "在新标签页查看最新内容", exact: true });
      await expect(recoveryLink).toHaveAttribute("href", route);
      const [latest] = await Promise.all([second.waitForEvent("popup"), recoveryLink.click()]);
      await expect(latest.getByRole("textbox", { name: entry.label, exact: true })).toHaveValue(firstText);
      await expect(secondInput).toHaveValue(secondText);
      // Manual conflict resolution is explicit, in the fresh page.
      await latest.getByRole("textbox", { name: entry.label, exact: true }).fill(secondText);
      const retry = latest.waitForResponse((r) => r.url() === endpoint && r.request().method() === "PATCH");
      await latest.getByRole("button", { name: entry.save, exact: true }).click();
      const recovered = await retry;
      expect(recovered.status(), await recovered.text()).toBe(202);
      expect(recovered.request().headers()["if-match"]).toBe(saved.edit_version);
      expect((await (await latest.request.get(endpoint)).json())[entry.field]).toBe(secondText);
      const publicAfter = await page.request.get(publicEndpoint);
      expect(publicAfter.status()).toBe(200);
      expect((await publicAfter.json())[entry.field]).toEqual(publicBefore[entry.field]);
      await second.screenshot({ path: testInfo.outputPath(`conflict-${entry.kind.replaceAll("/", "-")}.png`), fullPage: true });
    } finally {
      await secondContext.close();
    }
  });
}

test("A14 topic delayed first load never presents an editable blank object", async ({ page, baseURL }) => {
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
  await configure(page.context());
  await login(page, "owner");
  const row = editors[1];
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`${api}/admin/topics/${row.id}/`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await gate;
    await route.continue();
  });
  try {
    await page.goto(row.route(row.id));
    await expect(page.getByText("正在读取所选资料。", { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "名称", exact: true })).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page.getByRole("textbox", { name: "名称", exact: true })).toHaveValue("V306布局主题");
  await page.getByRole("textbox", { name: "主题说明", exact: true }).fill("加载后输入必须保留");
  const result = page.waitForResponse((r) => r.url() === `${api}/admin/topics/${row.id}/` && r.request().method() === "PATCH");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  const response = await result;
  expect(response.status()).toBe(202);
  expect((await response.json()).description).toBe("加载后输入必须保留");
});
