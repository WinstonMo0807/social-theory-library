import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api";
async function login(page: Page, context: BrowserContext, role: string) {
  await context.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(`${role}-v305@example.test`);
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

test("A31 theory timeline is secondary, scoped and keeps legacy object/filter links", async ({ page, baseURL }) => {
  await login(page, page.context(), "owner");
  const csrf = (await page.context().cookies(api)).find((cookie) => cookie.name === "csrftoken")!.value;
  const headers = { "X-CSRFToken": csrf, Origin: baseURL!, Referer: `${baseURL}/admin` };
  const nodes = [];
  for (const name of ["甲", "乙"]) {
    const response = await page.request.post(`${api}/catalog/admin/theory-system/nodes/`, { headers, data: {
      canonical_name_zh: `时间线归属${name}`, slug: `timeline-scope-${nodes.length}-${Date.now()}`, node_type: "theory_tradition", status: "draft",
    } });
    expect(response.status(), await response.text()).toBe(201);
    nodes.push(await response.json());
  }
  const response = await page.request.post(`${api}/catalog/admin/theory-timeline/`, { headers, data: {
    title: "只属于乙的事件", event_type: "development", start_year: 1990, review_status: "suggested", relations: [{ node: nodes[1].id, relation_type: "subject" }],
  } });
  expect(response.status(), await response.text()).toBe(201);
  const event = await response.json();
  await page.goto(`/admin/theories/${nodes[0].id}`);
  await page.getByRole("link", { name: "管理此理论的时间线", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/theories/${nodes[0].id}\\?section=timeline`));
  await expect(page.getByRole("heading", { name: "时间线归属甲的时间线", exact: true })).toBeVisible();
  await expect(page.locator(".normalized-timeline-list")).not.toContainText("只属于乙的事件");
  await expect(page.locator(".normalized-timeline-list")).toContainText("共 0 条");
  const form = page.locator(".timeline-event-editor");
  await expect(form).toContainText("时间线归属甲");
  await form.getByRole("textbox", { name: "事件标题", exact: true }).fill("从甲的理论页新建事件");
  await form.getByRole("spinbutton", { name: "开始年", exact: true }).fill("2001");
  await form.getByRole("textbox", { name: "来源", exact: true }).fill("合成来源，没有真实外部调用");
  const saved = page.waitForResponse((r) => r.url().endsWith("/admin/theory-timeline/") && r.request().method() === "POST");
  await form.getByRole("button", { name: "保存事件", exact: true }).click();
  const savedResponse = await saved;
  expect(savedResponse.status(), await savedResponse.text()).toBe(201);
  expect((await savedResponse.json()).relations.map((row: { node: string }) => row.node)).toEqual([nodes[0].id]);
  await page.goto(`/admin/theory-timeline?node=${nodes[1].id}&event=${event.id}&q=${encodeURIComponent("只属于乙")}&returnTo=${encodeURIComponent(`/admin/theories/${nodes[1].id}`)}`);
  await expect(form.getByRole("textbox", { name: "事件标题", exact: true })).toHaveValue("只属于乙的事件");
  await expect(page.getByRole("textbox", { name: "标题或来源", exact: true })).toHaveValue("只属于乙");
  await expect(page.getByRole("link", { name: "返回时间线归属乙", exact: true })).toHaveAttribute("href", `/admin/theories/${nodes[1].id}`);
  await page.goto(`/admin/theories/${nodes[0].id}?section=timeline&event=${event.id}`);
  await expect(page.getByRole("alert").filter({ hasText: "这个事件不属于当前理论" })).toBeVisible();
  await expect(form.getByRole("button", { name: "保存事件", exact: true })).toBeDisabled();
});

for (const kind of ["relation", "timeline"] as const) {
  test(`A14 A19 A32 ${kind}: save draft, reject stale editor, explicit publish and five-width actions`, async ({ page, browser, baseURL }, info) => {
    test.setTimeout(180_000);
    expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
    await login(page, page.context(), "owner");
    const csrf = (await page.context().cookies(api)).find((cookie) => cookie.name === "csrftoken")!.value;
    const headers = { "X-CSRFToken": csrf, Origin: baseURL!, Referer: `${baseURL}/admin` };
    const source = "30600000-0000-4000-8000-000000000204";
    const node = await page.request.post(`${api}/catalog/admin/theory-system/nodes/`, { headers, data: {
      canonical_name_zh: `专门页验证 ${kind} ${Date.now()}`, slug: `dedicated-${kind}-${Date.now()}`, node_type: "theory_tradition", status: "published",
    } });
    expect(node.status(), await node.text()).toBe(201);
    const target = await node.json();
    const endpoint = kind === "relation" ? "/catalog/admin/theory-system/relations/" : "/catalog/admin/theory-timeline/";
    const created = await page.request.post(`${api}${endpoint}`, { headers, data: kind === "relation" ? {
      source_node: source, target_node: target.id, relation_type: "criticizes", direction: "directed", evidence_source: "合成来源，第8页", description: "专门编辑页旧公开内容", status: "published",
    } : { title: `专门页时间线 ${Date.now()}`, description: "专门编辑页旧公开内容", event_type: "development", start_year: 2000, orientation: "left", review_status: "approved", relations: [{ node: target.id, relation_type: "subject", description: "应保留的关系来源" }] } });
    expect(created.status(), await created.text()).toBe(201);
    const record = await created.json();
    expect(record.editorial_revision).toBeTruthy();
    const initial = await page.request.post(`${api}${record.editorial_revision.publish_url}`, { headers, data: {} });
    expect(initial.status(), await initial.text()).toBe(200);
    const objectEndpoint = `${api}${endpoint}${record.id}/`;
    const route = kind === "relation" ? `/admin/theory-relations?relation=${record.id}` : `/admin/theories/${target.id}?section=timeline&event=${record.id}`;
    const publicEndpoint = kind === "relation" ? `${api}/catalog/theory-system/nodes/${target.slug}/` : `${api}/catalog/theory-system/timeline/?q=${encodeURIComponent(record.title)}`;
    const original = await (await page.request.get(publicEndpoint)).json();
    expect(JSON.stringify(original)).toContain("专门编辑页旧公开内容");
    const secondContext = await browser.newContext({ baseURL });
    const second = await secondContext.newPage();
    try {
      await login(second, secondContext, "curator");
      await Promise.all([page.goto(route), second.goto(route)]);
      const form = page.locator(kind === "relation" ? ".theory-relation-bottom-grid > form" : ".timeline-event-editor");
      const otherForm = second.locator(kind === "relation" ? ".theory-relation-bottom-grid > form" : ".timeline-event-editor");
      const label = kind === "relation" ? "关系说明" : "说明";
      const save = kind === "relation" ? "保存关系" : "保存事件";
      await expect(form.getByRole("textbox", { name: label, exact: true })).toHaveValue("专门编辑页旧公开内容");
      await expect(otherForm.getByRole("textbox", { name: label, exact: true })).toHaveValue("专门编辑页旧公开内容");
      await form.getByRole("textbox", { name: label, exact: true }).fill("甲保存的长说明，不应提前公开 AcademicInterdisciplinaryUnbrokenWordForLayoutTesting");
      await otherForm.getByRole("textbox", { name: label, exact: true }).fill("乙的输入不能被覆盖");
      const savedResponse = page.waitForResponse((r) => r.url() === objectEndpoint && r.request().method() === "PATCH");
      await form.getByRole("button", { name: save, exact: true }).click();
      const saved = await savedResponse;
      expect(saved.status(), await saved.text()).toBe(202);
      expect(JSON.stringify(await (await page.request.get(publicEndpoint)).json())).toEqual(JSON.stringify(original));
      const staleResponse = second.waitForResponse((r) => r.url() === objectEndpoint && r.request().method() === "PATCH");
      await otherForm.getByRole("button", { name: save, exact: true }).click();
      expect((await staleResponse).status()).toBe(409);
      await expect(otherForm.getByRole("textbox", { name: label, exact: true })).toHaveValue("乙的输入不能被覆盖");
      const recovery = otherForm.getByRole("link", { name: "在新标签页查看最新内容" });
      await expect(recovery).toHaveAttribute("href", route);
      const [latest] = await Promise.all([second.waitForEvent("popup"), recovery.click()]);
      await expect(latest.getByRole("textbox", { name: label, exact: true })).toHaveValue(/甲保存的长说明/);
      await expect(latest.getByRole("button", { name: "确认发布已保存的修改" })).toBeEnabled();
      const publish = form.getByRole("button", { name: "确认发布已保存的修改" });
      for (const width of [360, 390, 768, 1280, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        await publish.scrollIntoViewIfNeeded();
        await publish.focus();
        await expect(publish).toBeFocused();
        await publish.click({ trial: true });
        expect(await publish.evaluate((el) => {
          const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          return r.x >= 0 && r.right <= window.innerWidth && Boolean(hit && (el === hit || el.contains(hit)));
        })).toBe(true);
        await page.screenshot({ path: info.outputPath(`${kind}-actions-${width}.png`) });
        const layout = await form.evaluate((root) => {
          const targets = [root, ...root.querySelectorAll("fieldset, input, textarea, select, .timeline-draft-preview, .timeline-draft-preview article")];
          return targets.flatMap((element) => {
            const rect = element.getBoundingClientRect();
            if (!rect.width || !rect.height) return [];
            const outside = rect.left < -1 || rect.right > window.innerWidth + 1;
            const contentOverflow = element.matches(".timeline-draft-preview, .timeline-draft-preview article") && element.scrollWidth > element.clientWidth + 1;
            return outside || contentOverflow ? [{ element: element.tagName, className: element.className, left: rect.left, right: rect.right, contentOverflow }] : [];
          });
        });
        expect.soft(layout, `${kind} full form at ${width}px`).toEqual([]);
      }
      await form.getByRole("textbox", { name: label, exact: true }).fill("尚未保存的后续输入");
      await expect(publish).toBeDisabled();
      page.once("dialog", (dialog) => dialog.dismiss());
      await page.getByRole("link", { name: "内容管理", exact: true }).click();
      await expect(page).toHaveURL(`${baseURL}${route}`);
      await expect(form.getByRole("textbox", { name: label, exact: true })).toHaveValue("尚未保存的后续输入");
      // Restore the saved draft deliberately; it is never silently refreshed.
      await form.getByRole("textbox", { name: label, exact: true }).fill("甲保存的长说明，不应提前公开 AcademicInterdisciplinaryUnbrokenWordForLayoutTesting");
      const publication = page.waitForResponse((r) => r.url().includes("/editorial-revisions/") && r.url().endsWith("/publish/") && r.request().method() === "POST");
      page.once("dialog", (dialog) => dialog.accept());
      await publish.click();
      expect((await publication).status()).toBe(200);
      const visible = await page.request.get(publicEndpoint);
      expect(visible.status()).toBe(200);
      expect(JSON.stringify(await visible.json())).toContain("甲保存的长说明");
      await expect(form.getByRole("button", { name: "确认发布已保存的修改" })).toHaveCount(0);
      if (kind === "timeline") {
        const after = await (await page.request.get(objectEndpoint)).json();
        expect(after.relations[0].description).toBe("应保留的关系来源");
        expect(after.orientation, "Editing the description must retain the existing timeline placement").toBe("left");
      }
    } finally { await secondContext.close(); }
  });
}

for (const kind of ["relation", "timeline", "review"] as const) {
  test(`A31 ${kind}: browse all 35 filtered records and restore page context`, async ({ page, baseURL }) => {
    expect(new URL(baseURL!).hostname).toBe("127.0.0.1");
    await login(page, page.context(), "owner");
    const timeline = kind === "timeline";
    const review = kind === "review";
    const endpoint = timeline ? "/catalog/admin/theory-timeline/" : review ? "/catalog/admin/theory-system/review-tasks/" : "/catalog/admin/theory-system/relations/";
    const firstResponse = await page.request.get(`${api}${endpoint}?q=V306-LIST-`);
    expect(firstResponse.status()).toBe(200);
    const first = await firstResponse.json();
    expect(first.count).toBe(35);
    expect(first.results).toHaveLength(24);
    const secondResponse = await page.request.get(first.next);
    const last = await secondResponse.json();
    expect(last.results).toHaveLength(11);
    const pageKey = timeline ? "page" : review ? "review_page" : "relations_page";
    const queryKey = timeline ? "q" : review ? "review_q" : "relation_q";
    const route = timeline ? "/admin/theory-timeline" : "/admin/theory-relations";
    const params = new URLSearchParams({ [queryKey]: "V306-LIST-", return_to: "/admin/library?page=2&q=原列表" });
    await page.goto(`${route}?${params}`);
    const section = page.locator(timeline ? ".normalized-timeline-list" : review ? ".theory-review-list" : ".theory-existing-relations");
    const records = section.locator(timeline || review ? "tbody > tr" : ":scope > article");
    const nav = page.getByRole("navigation", { name: timeline ? "事件列表分页" : review ? "建议列表分页" : "关系列表分页" });
    await expect(records).toHaveCount(24);
    const seen = new Set(await records.locator(timeline || review ? "td:first-child strong" : ":scope > div strong:last-child").allTextContents());
    await nav.getByRole("link", { name: "下一页", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${pageKey}=2`));
    await expect(records).toHaveCount(11);
    for (const title of await records.locator(timeline || review ? "td:first-child strong" : ":scope > div strong:last-child").allTextContents()) seen.add(title);
    expect(seen.size).toBe(35);
    expect(new URL(page.url()).searchParams.get(queryKey)).toBe("V306-LIST-");
    expect(new URL(page.url()).searchParams.get("return_to")).toBe("/admin/library?page=2&q=原列表");
    await page.reload();
    await expect(records).toHaveCount(11);
    if (!review) {
      const chosen = last.results[0];
      await records.first().getByRole("button", { name: timeline ? /^编辑时间轴事件 / : "编辑", exact: !timeline }).click();
      await expect(page).toHaveURL(new RegExp(`${timeline ? "event" : "relation"}=${chosen.id}`));
      const field = page.getByRole("textbox", { name: timeline ? "事件标题" : "关系说明", exact: true });
      await expect(field).toHaveValue(timeline ? chosen.title : chosen.description);
      await page.reload();
      await expect(field).toHaveValue(timeline ? chosen.title : chosen.description);
      await expect(records).toHaveCount(11);
    }
    await nav.getByRole("link", { name: "上一页", exact: true }).click();
    await expect(records).toHaveCount(24);
  });
}
