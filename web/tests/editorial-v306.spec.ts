import { expect, test, type Page } from "@playwright/test";
import type { RecommendationIssue } from "../lib/api/recommendation-issues.types";
const api="http://127.0.0.1:8105/api";
test.beforeEach(async({page,baseURL})=>{
  expect(baseURL,"Only use the disposable cataloging runner").toBe("http://127.0.0.1:3105");
  await page.route("**/runtime-config.js",route=>route.fulfill({contentType:"application/javascript",body:`window.__SOCIAL_THEORY_LIBRARY_CONFIG__=Object.freeze({apiBase:'${api}'});`}));
});
test("directory keeps every card on a page and retains quoted curator on pagination",async({page})=>{
  await page.goto("/recommendations?q=EDITORIAL74测试&page_size=8&curator="+encodeURIComponent("测试署名, 甲"));
  await expect(page.locator("main article")).toHaveCount(8);
  await page.getByRole("navigation",{name:"专题文章分页"}).getByRole("link",{name:"下一页"}).click();
  await expect(page).toHaveURL(/page=2/);await expect(page.locator("main article")).toHaveCount(6);
  await expect(page.getByRole("combobox",{name:"策划者"})).toHaveValue("测试署名, 甲");
});
test("chips reset form defaults after client navigation",async({page})=>{
  await page.goto("/recommendations?q=EDITORIAL74测试&kind=exhibition");
  await expect(page.locator("main article")).toHaveCount(1);
  await page.getByRole("link",{name:"原文展览",exact:true}).click();
  await expect(page.getByRole("combobox",{name:"内容类型"})).toHaveValue("");
});
test("empty search differs from invalid range and keeps the input",async({page})=>{
  await page.goto("/recommendations?q=不存在的EDITORIAL74条件");
  await expect(page.getByRole("heading",{name:"未找到符合条件的专题文章"})).toBeVisible();
  await page.goto("/recommendations?year_from=2025&year_to=1900");
  await expect(page.getByRole("alert")).toContainText("筛选条件无效");
  await expect(page.getByRole("spinbutton",{name:"起始年份"})).toHaveValue("2025");
});
test("article headings are stable links and materials are real",async({page})=>{
  const response=await page.request.get(`${api}/catalog/recommendation-issues/stl4-editorial-0/`);expect(response.status()).toBe(200);
  const issue=await response.json() as RecommendationIssue;
  await page.goto("/recommendations/stl4-editorial-0");
  await page.getByRole("link",{name:/测试章节二/,exact:false}).click();
  await expect(page).toHaveURL(new RegExp(`article-${issue.body_blocks[2].id}`));
  await expect(page.getByRole("heading",{name:issue.title,exact:true})).toBeVisible();
});
test("original drawer retains article context and returns keyboard focus",async({page})=>{
  const response=await page.request.get(`${api}/catalog/recommendation-issues/stl4-editorial-0/`);const issue=await response.json() as RecommendationIssue;
  const source=issue.body_blocks.find(row=>row.type==="evidence")?.resolved_sources?.[0];expect(source,"Synthetic real-PDF source required").toBeTruthy();
  await page.goto("/recommendations/stl4-editorial-0");
  const opener=page.getByRole("button",{name:new RegExp(source!.title)}).first();await opener.click();
  const drawer=page.getByRole("dialog",{name:"原文与编辑注释"});await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("tab",{name:"原文查看",exact:true})).toBeVisible();
  await page.keyboard.press("Escape");await expect(drawer).toHaveCount(0);await expect(opener).toBeFocused();
});
test("missing-image exhibit keeps caption, source and return navigation",async({page})=>{
  await page.goto("/recommendations/stl4-editorial-1");await page.getByRole("link",{name:"查看图像与资料"}).click();
  await expect(page.getByText("没有图片时保留的测试说明",{exact:true})).toBeVisible();
  await expect(page.getByText("本地测试资料，不是历史图像",{exact:true})).toBeVisible();
  await page.getByRole("link",{name:"返回展项",exact:true}).click();await expect(page).toHaveURL(/stl4-editorial-1$/);
});
test("mobile article and directory do not overflow",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  for(const path of ["/recommendations?q=EDITORIAL74测试","/recommendations/stl4-editorial-0","/recommendations/stl4-editorial-1"]){
    await page.goto(path);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }
});

async function loginReader(page:Page){
  await page.goto("/login");await page.getByLabel("邮箱",{exact:true}).fill("reader-v305@example.test");
  await page.locator('input[name="password"]').fill("E2E-Local-Only-305-passphrase");
  await page.getByRole("button",{name:"登录",exact:true}).click();await expect(page).toHaveURL(/\/account$/);
}

test("exhibition embeds the exact reader and saves display preferences",async({page})=>{
  await page.goto("/recommendations/stl4-editorial-1");await page.getByRole("link",{name:"进入展项",exact:true}).first().click();
  await expect(page.locator(".reader-embedded")).toBeVisible();
  await expect(page.getByRole("progressbar",{name:"展项阅读位置"})).toBeVisible();
  await page.getByRole("button",{name:"阅读设置",exact:true}).first().click();
  const dialog=page.getByRole("dialog",{name:"阅读设置",exact:true});
  await dialog.getByRole("radio",{name:"减少动态效果",exact:true}).check();
  await dialog.getByRole("checkbox",{name:"默认展开目录"}).uncheck();
  await dialog.getByRole("combobox",{name:"高亮颜色"}).selectOption("gray");
  await dialog.getByRole("button",{name:"保存设置"}).click();
  await expect(page.locator(".reader-embedded")).toHaveAttribute("data-reader-motion","reduced");
  await expect(page.locator(".reader-embedded")).toHaveClass(/left-closed/);
  await page.reload();await expect(page.locator(".reader-embedded")).toHaveAttribute("data-reader-highlight","gray");
});

test("mobile table of contents starts collapsed and can navigate",async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto("/recommendations/stl4-editorial-0");
  const toc=page.locator("aside details");await expect(toc).not.toHaveAttribute("open");
  await toc.getByText("文章目录",{exact:true}).click();await toc.getByRole("link",{name:/测试章节二/}).click();await expect(page).toHaveURL(/#article-/);
});

test("lost list-save response is recovered without another POST",async({page})=>{
  await loginReader(page);let writes=0;
  await page.route("**/catalog/recommendation-issues/stl4-editorial-0/save-list/**",async route=>{
    if(route.request().method()!=="POST")return route.continue();writes++;const response=await route.fetch();expect(response.status()).toBe(200);return route.abort("failed");
  });
  await page.goto("/recommendations/stl4-editorial-0");await page.getByRole("button",{name:"保存书单 ＋",exact:true}).click();
  await page.getByRole("button",{name:"核对原保存结果"}).click();await expect(page.getByRole("link",{name:"打开我的书单"})).toBeVisible();expect(writes).toBe(1);
});

test("comment consent, lost receipt and delete are real owner operations",async({page})=>{
  await loginReader(page);const label=`隔离评论${Date.now()}`,response=await page.request.get(`${api}/catalog/recommendation-issues/stl4-editorial-0/`),issue=await response.json() as RecommendationIssue;
  let writes=0;
  await page.route(`**/reading/article-comments/${issue.id}/`,async route=>{
    if(route.request().method()!=="POST")return route.continue();writes++;const result=await route.fetch();expect(result.status()).toBe(200);return route.abort("failed");
  });
  await page.goto("/recommendations/stl4-editorial-0#article-comments");const comments=page.locator("#article-comments");
  await comments.getByLabel("公开署名",{exact:true}).fill(label);await comments.getByLabel("评论内容",{exact:true}).fill("仅用于隔离环境验收的测试评论。");
  await expect(comments.getByRole("button",{name:"提交审核"})).toBeDisabled();await comments.getByRole("checkbox").check();await comments.getByRole("button",{name:"提交审核"}).click();
  await comments.getByRole("button",{name:"核对原提交结果"}).click();const own=comments.locator("article").filter({hasText:label});await expect(own).toContainText("待审核");expect(writes).toBe(1);
  page.once("dialog",dialog=>dialog.accept());await own.getByRole("button",{name:"删除本人评论"}).click();await expect(own).toHaveCount(0);
});
