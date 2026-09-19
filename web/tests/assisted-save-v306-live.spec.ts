import { expect, test, type Locator, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8105/api";
async function expectInputValues(inputs: Locator, values: string[]) {
  await expect(inputs).toHaveCount(values.length);
  for (let index = 0; index < values.length; index += 1) await expect(inputs.nth(index)).toHaveValue(values[index]);
}
async function login(page: Page) {
  await page.route("**/runtime-config.js", (route) => route.fulfill({ contentType: "application/javascript", body: `window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});` }));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("owner-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

test("A13 A15 A24 identity suggestions fill actual rows, undo only added authors and save once", async ({ page }, info) => {
  test.setTimeout(120_000);
  await login(page);
  const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=${encodeURIComponent("V306身份建议演练")}`)).json();
  expect(list.count).toBe(1);
  const work = list.results[0];
  const workspaceUrl = `${api}/catalog/admin/library/works/${work.id}/?edition=${work.primary_edition.id}`;
  await page.goto(`/admin/library/works/${work.id}?edition=${work.primary_edition.id}#contributors`);
  const authors = page.getByRole("textbox", { name: "作者姓名", exact: true });
  await expectInputValues(authors, ["V306保留原作者"]);
  const writes: string[] = [];
  page.on("request", (r) => { if (r.method() === "POST" && /\/edits\/|\/adopt\//.test(r.url())) writes.push(r.url()); });
  const contributors = page.locator("#workflow-section-contributors");
  async function fillPerson(role: "作者" | "译者", name: string) {
    await contributors.getByRole("button", { name: "智能查找", exact: true }).nth(role === "作者" ? 0 : 1).click();
    const panel = page.getByRole("region", { name: `${role}建议`, exact: true });
    await expect(panel).toHaveAttribute("aria-busy", "false");
    const result = panel.locator("article").filter({ has: page.getByText(name, { exact: true }) });
    if (!(await result.isVisible())) {
      const more = panel.getByRole("button", { name: /^查看另外/ });
      await expect(more).toBeVisible();
      await more.click();
    }
    await result.getByRole("button", { name: `填入${role}`, exact: true }).click();
  }
  await fillPerson("作者", "V306预填作者甲");
  await expectInputValues(authors, ["V306保留原作者", "V306预填作者甲"]);
  await fillPerson("译者", "V306预填作者甲");
  await expect(page.getByRole("textbox", { name: "译者姓名", exact: true })).toHaveValue("V306预填作者甲");
  await page.getByRole("button", { name: "撤销作者填入", exact: true }).click();
  await expectInputValues(authors, ["V306保留原作者"]);
  await expect(page.getByRole("textbox", { name: "译者姓名", exact: true })).toHaveValue("V306预填作者甲");
  await fillPerson("作者", "V306预填作者甲");
  await fillPerson("作者", "V306预填作者乙");
  await expectInputValues(authors, ["V306保留原作者", "V306预填作者甲", "V306预填作者乙"]);
  expect(writes).toEqual([]);
  expect((await (await page.request.get(workspaceUrl)).json()).data.contributors.items).toHaveLength(1);
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("button", { name: "撤销译者填入", exact: true }).click({ trial: true });
    // Trial click scrolls but does not move focus. Start each viewport with a
    // real focus change before checking navigation back to the person input.
    await page.getByRole("button", { name: "撤销译者填入", exact: true }).focus();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    for (const label of await contributors.locator(".workflow-field-assistant-row > strong, .field-assistant-trigger").all()) {
      const textLines = await label.evaluate((element) => {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        const lines = new Set<number>();
        let node;
        while ((node = walker.nextNode())) {
          if (!node.textContent?.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const rect of range.getClientRects()) lines.add(Math.round(rect.top));
        }
        return lines.size;
      });
      expect.soft(textLines, `${width}px: short labels and lookup buttons stay on one line`).toBe(1);
    }
    for (const row of await contributors.locator(".workflow-contributor-row").all()) {
      const widthRatio = await row.evaluate((element) => {
        const parent = element.parentElement!;
        const style = getComputedStyle(parent);
        return element.getBoundingClientRect().width / (parent.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
      });
      expect.soft(widthRatio, `${width}px: the person form uses its available card width`).toBeGreaterThan(0.95);
    }
    for (const picker of await contributors.locator(".workflow-entity-combobox").all()) {
      expect(await picker.evaluate((element) => {
        const controls = [element.querySelector(":scope > svg"), element.querySelector("input"), element.querySelector(":scope > button")];
        const centers = controls.map((control) => { const box = control!.getBoundingClientRect(); return box.top + box.height / 2; });
        return Math.max(...centers) - Math.min(...centers);
      }), `${width}px: search icon, input and toggle share one row`).toBeLessThan(2);
    }
    const personPicker = contributors.getByRole("combobox").first();
    await personPicker.focus();
    await expect(personPicker).toBeFocused();
    await personPicker.press("ArrowDown");
    await expect(personPicker).toHaveAttribute("aria-expanded", "true");
    await personPicker.press("Escape");
    await expect(personPicker).toHaveAttribute("aria-expanded", "false");
    expect(await personPicker.evaluate((element) => {
      const box = element.getBoundingClientRect();
      return document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === element;
    }), `${width}px: keyboard focus is not covered`).toBe(true);
    await page.getByRole("button", { name: "撤销译者填入", exact: true }).click({ trial: true });
    if (width === 360 || width === 1440) await page.screenshot({ path: info.outputPath(`identity-filled-${width}.png`) });
  }
  await page.locator("#workflow-section-bibliography > button").click();
  await page.getByRole("button", { name: "重新查找", exact: true }).click();
  await page.getByRole("region", { name: "出版社建议", exact: true }).getByRole("button", { name: "填入出版社", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "出版社", exact: true })).toHaveValue("V306预填出版社");
  expect(writes).toEqual([]);
  const saved = page.waitForResponse((r) => r.url().endsWith(`/works/${work.id}/edits/`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "保存书目修改", exact: true }).click();
  const response = await saved;
  expect(response.status(), await response.text()).toBe(200);
  const body = response.request().postDataJSON();
  expect(body.suggestions).toHaveLength(4);
  expect(writes).toHaveLength(1);
  const result = await response.json();
  expect(result.data.contributors.items.map((row: { display_name: string; role: string }) => [row.display_name, row.role])).toEqual([
    ["V306保留原作者", "author"], ["V306预填作者甲", "translator"], ["V306预填作者甲", "author"], ["V306预填作者乙", "author"],
  ]);
  expect(result.data.bibliography.publisher_authority_id).toBeTruthy();
  await expect(page.getByText(/本页所有书目修改已保存/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("textbox", { name: "出版社", exact: true })).toHaveValue("V306预填出版社");
});

test("unknown author fills the new-person input without saving a changed title or creating a person", async ({ page }) => {
  await login(page);
  const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=${encodeURIComponent("V306未识别姓名演练")}`)).json();
  const work = list.results[0];
  await page.goto(`/admin/library/works/${work.id}?edition=${work.primary_edition.id}#work`);
  const writes: string[] = [];
  page.on("request", (r) => { if (["POST", "PATCH"].includes(r.method()) && /\/edits\/|\/adopt\/|\/create\/|\/sections\//.test(r.url())) writes.push(r.url()); });
  await page.getByRole("textbox", { name: "作品题名", exact: true }).fill("尚未保存的身份演练新题名");
  await page.locator("#workflow-section-contributors > button").click();
  await page.locator("#workflow-section-contributors").getByRole("button", { name: "智能查找", exact: true }).first().click();
  const panel = page.getByRole("region", { name: "作者建议", exact: true });
  await panel.getByRole("button", { name: "填写新人物名称", exact: true }).click();
  await expect(panel.getByRole("textbox", { name: "新学者名称", exact: true })).toHaveValue("V306待核对新人物");
  await expect(panel.getByRole("textbox", { name: "新学者名称", exact: true })).toBeFocused();
  await expect(panel).toContainText("不会自动合并同名人物");
  expect(writes).toEqual([]);
  const unchanged = await (await page.request.get(`${api}/catalog/admin/library/works/${work.id}/?edition=${work.primary_edition.id}`)).json();
  expect(unchanged.data.work.title).toBe("V306未识别姓名演练");
  expect(unchanged.data.contributors.items).toEqual([]);
});

test("A22 same-name people require an explicit identity check and never merge on fill", async ({ page }) => {
  await login(page);
  const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=${encodeURIComponent("V306同名身份演练")}`)).json();
  const work = list.results[0];
  await page.goto(`/admin/library/works/${work.id}?edition=${work.primary_edition.id}#contributors`);
  await page.locator("#workflow-section-contributors").getByRole("button", { name: "智能查找", exact: true }).first().click();
  const panel = page.getByRole("region", { name: "作者建议", exact: true });
  const person = panel.locator("article").filter({ hasText: "生于1980年" });
  await person.getByText("查看依据", { exact: true }).click();
  await expect(person).toContainText("馆内存在同名对象");
  await person.getByRole("button", { name: "填入作者", exact: true }).click();
  await expect(panel).toContainText("请查看依据并确认具体人物");
  await expect(page.getByRole("textbox", { name: "作者姓名", exact: true })).toHaveValue("");
  await person.getByRole("button", { name: "已核对，填入作者", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "作者姓名", exact: true })).toHaveValue("V306同名人物");
  const saved = page.waitForResponse((r) => r.url().endsWith(`/works/${work.id}/edits/`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "保存书目修改", exact: true }).click();
  const response = await saved;
  expect(response.status(), await response.text()).toBe(200);
  const chosen = response.request().postDataJSON().suggestions[0];
  expect(chosen.source_type).toBe("local_person");
  const result = await response.json();
  expect(result.data.contributors.items).toHaveLength(1);
  expect(result.data.contributors.items[0].person_id).toBe(chosen.selected_entity_id);
  const lookupLoaded = page.waitForResponse((r) => r.url().endsWith("/field-assistant/lookup/") && r.request().postDataJSON()?.field_name === "author" && r.request().postDataJSON()?.refresh === true);
  await page.locator("#workflow-section-contributors").getByRole("button", { name: "智能查找", exact: true }).first().click();
  const lookupResponse = await lookupLoaded;
  expect(lookupResponse.status(), await lookupResponse.text()).toBe(200);
  const lookup = await lookupResponse.json();
  const identities = [...lookup.results, ...lookup.more_results].filter((row: { entity?: { id: string } }) => row.entity?.id);
  expect(new Set(identities.map((row: { entity: { id: string } }) => row.entity.id)).size).toBe(2);
});

test("A13 A14 A24 prefill is visible and editable; whole save survives a lost response without duplication", async ({ page }, info) => {
  test.setTimeout(120_000);
  await login(page);
  const list = await (await page.request.get(`${api}/catalog/admin/library/works/?q=${encodeURIComponent("V306智能填写演练")}`)).json();
  expect(list.count).toBe(1);
  const work = list.results[0];
  const workspaceUrl = `${api}/catalog/admin/library/works/${work.id}/?edition=${work.primary_edition.id}`;
  await page.goto(`/admin/library/works/${work.id}?edition=${work.primary_edition.id}#work`);
  const initial = await (await page.request.get(workspaceUrl)).json();
  const writes: string[] = [];
  page.on("request", (r) => { if (r.method() === "POST" && /\/edits\/|\/adopt\//.test(r.url())) writes.push(r.url()); });
  await page.getByRole("textbox", { name: "作品题名", exact: true }).fill("V306修改后智能填写演练");
  await page.getByRole("button", { name: "查找简介", exact: true }).click();
  const panel = page.getByRole("region", { name: "简介建议", exact: true });
  await expect(panel).toContainText("此次没有启动外部检索");
  await panel.getByRole("button", { name: "填入简介", exact: true }).click();
  const abstract = page.getByLabel("馆藏简介", { exact: true });
  await expect(abstract).toHaveValue("用于验证先填表再保存的合成简介。");
  await expect(page.getByText(/已填入简介，尚未保存/)).toBeVisible();
  expect(writes).toEqual([]);
  expect((await (await page.request.get(workspaceUrl)).json()).data.work.abstract).toBe(initial.data.work.abstract);
  await page.getByRole("button", { name: "撤销简介填入", exact: true }).click();
  await expect(abstract).toHaveValue(initial.data.work.abstract || "");
  expect(writes).toEqual([]);
  await page.getByRole("button", { name: "查找简介", exact: true }).click();
  await panel.getByRole("button", { name: "填入简介", exact: true }).click();
  await abstract.fill("管理员核对并改写的最终简介。中文长标题与VeryLongUnbrokenEnglishWordForResponsiveTesting");
  await page.locator("#workflow-section-bibliography > button").click();
  await page.getByLabel("本版本出版年份", { exact: true }).fill("2024");
  const save = page.getByRole("button", { name: "保存书目修改", exact: true });
  await expect(save).toHaveCount(1);
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await save.scrollIntoViewIfNeeded();
    await save.click({ trial: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    if (width === 360 || width === 1440) await page.screenshot({ path: info.outputPath(`whole-save-${width}.png`) });
  }
  let lostRequest: Record<string, unknown> | null = null;
  await page.route(`**/library/works/${work.id}/edits/`, async (route) => {
    lostRequest = route.request().postDataJSON();
    const response = await route.fetch();
    expect(response.status(), await response.text()).toBe(200);
    await route.abort("failed"); // Server committed; deliberately lose only the response.
  }, { times: 1 });
  await save.click();
  await expect(save).toBeEnabled();
  await expect(page.getByLabel("本版本出版年份", { exact: true })).toHaveValue("2024");
  expect(lostRequest).not.toBeNull();
  const retry = page.waitForResponse((r) => r.url().endsWith(`/works/${work.id}/edits/`) && r.request().method() === "POST");
  await save.click();
  const response = await retry;
  expect(response.status(), await response.text()).toBe(200);
  const result = await response.json();
  expect(result.save_result.replayed).toBe(true);
  expect(response.request().postDataJSON()).toEqual(lostRequest);
  expect(result.save_result.sections).toEqual(["work", "bibliography"]);
  expect(result.data.work.title).toBe("V306修改后智能填写演练");
  expect(result.data.work.abstract).toContain("管理员核对并改写");
  expect(result.data.bibliography.publication_year).toBe(2024);
  await expect(page).toHaveURL(/#bibliography$/);
  await expect(page.getByText(/本页所有书目修改已保存，尚未发布/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("本版本出版年份", { exact: true })).toHaveValue("2024");
  await page.locator("#workflow-section-work > button").click();
  await expect(abstract).toHaveValue(result.data.work.abstract);
});
