import {test,expect,type Page} from "@playwright/test";
import type {IssueDraft} from "../components/admin/curation/use-issue-draft";
import type {IssuePublicationReviewData} from "../components/admin/curation/issue-publication-review";

const issue="71111111-1111-4111-8111-111111111111",block="72222222-2222-4222-8222-222222222222";
async function setup(page:Page,options:{blocked?:boolean;failed?:boolean;media?:boolean;frameFailure?:boolean;frameVersion?:string}={}) {
  let value:IssueDraft={id:issue,slug:"publish-review-fixture",title:"隔离发布验收文章",introduction:"验收导语",issue_label:"",public_byline:"",cover_url:"",display_from:null,published_at:null,edit_version:"v1",has_unpublished_changes:true,body_blocks:[{id:block,type:"paragraph",text:"人工稿件保留"}],items:[]};
  const commands:Record<string,unknown>[]=[],writes:Record<string,unknown>[]=[];
  const mediaWrites:Record<string,unknown>[]=[],renditionWrites:Record<string,unknown>[]=[];
  const mediaId="73333333-3333-4333-8333-333333333333",oldImage="74444444-4444-4444-8444-444444444444",newImage="75555555-5555-4555-8555-555555555555";
  if(options.media)value.cover_rendition_id=oldImage;
  let media={id:mediaId,updated_at:"2026-10-22T01:00:00Z",alt_text:"隔离验收图片",license:"",rights:"",source_label:"",source_url:"",credit:"",renditions:[]};
  const projection=():IssuePublicationReviewData=>({edit_version:value.edit_version,checked_at:"2026-10-22T02:00:00Z",draft_revision_id:issue,current_revision_id:value.has_unpublished_changes?null:issue,draft_at:"2026-10-22T01:00:00Z",current_at:value.published_at,blocking_count:options.blocked?1:0,warning_count:0,has_draft:Boolean(value.has_unpublished_changes),can_publish:!options.blocked&&Boolean(value.has_unpublished_changes),actor_label:"验收编辑",public_url:"/recommendations/publish-review-fixture",reader_preview:value,checks:options.blocked?[{code:"source_unavailable",severity:"blocking",title:"原文或关联资料暂不可公开",detail:"验收来源撤回",section:"body",block_id:block,item_id:""}]:[],changes:[{field:"title",label:"标题",before_display:"旧标题",after_display:value.title,change:"changed"}]});
  await page.context().addCookies([{name:"stl_access",value:"opaque-publish-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  await page.route("**/api/**",async route=>{const req=route.request(),url=new URL(req.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:1,email:"publish-review@example.test",display_name:"验收编辑",role:"admin",capabilities:["access_back_office","can_edit_metadata","can_publish_authority"],reading_preferences:{}}});
    if(url.pathname==="/api/catalog/admin/media/collection/"){expect(url.searchParams.get("rendition_id")).toBe(oldImage);return route.fulfill({json:{count:1,page:1,pages:1,results:[media]}});}
    if(url.pathname===`/api/catalog/admin/media/${mediaId}/`){if(req.method()==="PATCH"){mediaWrites.push(req.postDataJSON());media={...media,...req.postDataJSON(),updated_at:"2026-10-22T01:01:00Z"};}return route.fulfill({json:media});}
    if(url.pathname===`/api/catalog/admin/media/${mediaId}/renditions/`){renditionWrites.push(req.postDataJSON());return route.fulfill({json:{id:newImage,url:`/api/catalog/admin/media/renditions/${newImage}/file/`}});}
    if(url.pathname===`/api/catalog/admin/recommendation-issues/${issue}/`){if(req.method()==="PUT"){writes.push(req.postDataJSON());value={...value,...req.postDataJSON(),edit_version:"v2"};}return route.fulfill({json:value});}
    if(url.pathname.endsWith(`/${issue}/preview/`)){
      if(req.frame().parentFrame()&&options.frameFailure)return route.fulfill({status:503,json:{detail:"合成预览读取失败"}});
      const data=projection();
      if(req.frame().parentFrame()&&options.frameVersion)data.edit_version=options.frameVersion;
      return route.fulfill({json:url.searchParams.get("review")==="true"?data:value});
    }
    if(url.pathname.endsWith(`/${issue}/publish/`)){commands.push(req.postDataJSON());if(options.failed)return route.fulfill({status:400,json:{detail:"来源已撤回，发布阻断"}});value={...value,has_unpublished_changes:false,published_at:"2026-10-22T02:01:00Z"};return route.fulfill({json:value});}
    if(url.pathname.endsWith("/presence/"))return route.fulfill({json:{participants:[],checked_at:"2026-10-22T00:00:00Z",expires_after_seconds:90,shared:true,notice:""}});
    if(url.pathname.endsWith("/work-notices/"))return route.fulfill({json:{count:0,results:[],checked_at:"2026-10-22T00:00:00Z"}});
    return route.fulfill({json:{count:0,next:null,previous:null,results:[]}});
  });
  await page.goto(`/admin/recommendations/issues/${issue}`);
  await page.getByRole("button",{name:"发布检查",exact:true}).click();
  await expect(page.getByRole("heading",{name:"真实预览与发布检查",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"重新检查",exact:true})).toBeEnabled();
  return {commands,writes,mediaWrites,renditionWrites,value:()=>value};
}

test("publication blocker locates the exact preserved editor block",async({page})=>{
  const state=await setup(page,{blocked:true});await expect(page.getByRole("button",{name:"修复1项后发布"})).toBeDisabled();await page.getByRole("button",{name:"定位",exact:true}).click();await expect(page.locator(`#editor-block-${block}`)).toHaveAttribute("data-selected","true");await expect(page.getByRole("textbox",{name:"内容",exact:true})).toHaveText("人工稿件保留");expect(state.commands).toHaveLength(0);
});

test("reader preview uses a real version-bound iframe for desktop and mobile",async({page})=>{
  const state=await setup(page);const frame=page.locator('iframe[title="已保存稿的真实页面预览"]');await expect(frame).toHaveAttribute("src",/frame=1&version=v1/);await expect(frame).toHaveAttribute("data-device","desktop");await page.getByRole("button",{name:"移动端",exact:true}).click();await expect(frame).toHaveAttribute("data-device","mobile");await expect(page.frameLocator('iframe[title="已保存稿的真实页面预览"]').getByRole("heading",{name:"隔离发布验收文章",exact:true})).toBeVisible();expect(state.commands).toHaveLength(0);
});

test("publication requires explicit confirmation and refreshes when version id is unchanged",async({page})=>{
  const state=await setup(page);await page.getByRole("button",{name:"确认发布",exact:true}).click();expect(state.commands).toHaveLength(0);await page.getByRole("dialog",{name:"确认发布已检查版本"}).getByRole("button",{name:"确认发布",exact:true}).click();await expect.poll(()=>state.commands.length).toBe(1);expect(state.commands[0]).toMatchObject({edit_version:"v1",confirm:true});await expect(page.getByRole("button",{name:"暂无待发布草稿",exact:true})).toBeDisabled();await expect(page.getByRole("link",{name:"查看公开页 ↗"})).toBeVisible();expect(state.value().body_blocks[0].text).toBe("人工稿件保留");
});

test("failed publish displays a result dialog and preserves the draft",async({page})=>{
  const state=await setup(page,{failed:true});await page.getByRole("button",{name:"确认发布",exact:true}).click();await page.getByRole("dialog",{name:"确认发布已检查版本"}).getByRole("button",{name:"确认发布",exact:true}).click();await expect(page.getByRole("dialog",{name:"发布结果核对"})).toBeVisible();expect(state.value().has_unpublished_changes).toBe(true);expect(state.value().published_at).toBeNull();expect(state.commands).toHaveLength(1);
});

test("dirty changes remain editable and block publication until saved",async({page})=>{
  const state=await setup(page);await page.getByRole("button",{name:"返回编辑",exact:true}).click();await page.getByRole("textbox",{name:"标题",exact:true}).fill("尚未保存的新标题");await page.getByRole("button",{name:"发布检查",exact:true}).click();await expect(page.getByRole("heading",{name:"您有未保存的修改"})).toBeVisible();await expect(page.getByRole("button",{name:"确认发布",exact:true})).toBeDisabled();await page.getByRole("button",{name:"保存草稿",exact:true}).first().click();await expect.poll(()=>state.writes.length).toBe(1);await expect(page.getByRole("heading",{name:"您有未保存的修改"})).toHaveCount(0);expect(state.commands).toHaveLength(0);
});

test("current image rights use metadata CAS and a new selection without publishing",async({page})=>{
  const state=await setup(page,{media:true});
  await page.getByRole("button",{name:"返回编辑",exact:true}).click();
  await page.getByRole("button",{name:"主图",exact:true}).click();
  await page.getByRole("button",{name:"编辑当前图片出处",exact:true}).click();
  const form=page.locator("form").filter({has:page.getByRole("button",{name:"保存资料并填入",exact:true})});
  await form.getByRole("textbox",{name:"使用许可",exact:true}).fill("仅供隔离验收的授权说明");
  await form.getByRole("button",{name:"保存资料并填入",exact:true}).click();
  await expect.poll(()=>state.mediaWrites.length).toBe(1);
  expect(state.mediaWrites[0]).toMatchObject({expected_updated_at:"2026-10-22T01:00:00Z",license:"仅供隔离验收的授权说明"});
  await expect.poll(()=>state.renditionWrites.length).toBe(1);
  expect(state.renditionWrites[0]).toMatchObject({kind:"hero",width:1280});
  await expect(page.getByText("已填入当前表单；保存草稿后保留，发布后才公开。已发布的图片版本保持原样。",{exact:true})).toBeVisible();
  expect(state.commands).toHaveLength(0);
});

test("discarding unsaved publication changes requires an explicit choice and writes nothing",async({page})=>{
  const state=await setup(page);
  await page.getByRole("button",{name:"返回编辑",exact:true}).click();
  await page.getByRole("textbox",{name:"标题",exact:true}).fill("本次未保存标题");
  await page.getByRole("button",{name:"发布检查",exact:true}).click();
  await page.getByRole("button",{name:"放弃修改",exact:true}).click();
  await page.getByRole("dialog",{name:"放弃未保存修改"}).getByRole("button",{name:"保留修改",exact:true}).click();
  await expect(page.getByRole("heading",{name:"您有未保存的修改"})).toBeVisible();
  await page.getByRole("button",{name:"放弃修改",exact:true}).click();
  await page.getByRole("dialog",{name:"放弃未保存修改"}).getByRole("button",{name:"确认放弃",exact:true}).click();
  await expect(page.getByRole("heading",{name:"您有未保存的修改"})).toHaveCount(0);
  await page.getByRole("button",{name:"返回编辑",exact:true}).click();
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue("隔离发布验收文章");
  expect(state.writes).toHaveLength(0);expect(state.commands).toHaveLength(0);
});

// Defined for unified acceptance only; no browser checks run during implementation.
for(const mismatch of [false,true])test(`article publish stays disabled for ${mismatch?"another saved version":"failed frame loading"}`,async({page})=>{
  const state=await setup(page,mismatch?{frameVersion:"v2"}:{frameFailure:true});
  await expect(page.getByText("页面预览读取失败、账户或保存版本已变化。请重新检查后发布。",{exact:true})).toBeVisible();
  await page.evaluate(({issue})=>window.postMessage({type:"stl:issue-publication-preview",owner:"1",issueId:issue,version:"v1",state:"ready"},location.origin),{issue});
  await expect(page.getByRole("button",{name:"确认发布",exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"发布设置",exact:true}).click();
  await expect(page.getByRole("button",{name:"确认发布",exact:true})).toBeDisabled();
  expect(state.commands).toHaveLength(0);
});
