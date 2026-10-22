import {test,expect,type Page} from "@playwright/test";

// Isolated contract definitions only; not evidence of live/visual acceptance.
const id="71111111-1111-4111-8111-111111111111",revision="72222222-2222-4222-8222-222222222222",draft="73333333-3333-4333-8333-333333333333";
const version="a".repeat(64),key=`stl:knowledge-history:v1:1:topic:${id}`;
async function setup(page:Page,options:{lost?:boolean;pendingDraft?:boolean;stored?:unknown}={}) {
  const writes:{body:Record<string,unknown>;owner:string|undefined}[]=[];
  let saved=false,fail=false,owner=1;
  const row={id:revision,revision:1,status:"published",snapshot_public:true,matches_current:false,note:"历史保存说明",actor:"隔离编辑",created_at:"2026-10-23T08:00:00Z",published_at:"2026-10-23T08:05:00Z",can_restore:true};
  const payload=()=>({object_type:"topic",object_id:id,edit_version:saved?"b".repeat(64):version,title:"隔离主题历史",status:"published",is_public:true,has_draft:saved||Boolean(options.pendingDraft),draft_id:saved?draft:null,can_withdraw:!saved&&!options.pendingDraft,
    history:{count:1,page:1,pages:1,results:[{...row,can_restore:!saved&&!options.pendingDraft}]},selected:{...row,can_restore:!saved&&!options.pendingDraft},
    changes:[{field:"description",label:"说明",before:"当前正式说明",after:"历史说明",changed:true}],dependencies:[{key:"catalog.worktopic",label:"馆藏主题关联",count:2}],events:[],scope:"隔离样本的对象修订字段；不会恢复其他对象。"});
  await page.context().addCookies([{name:"stl_access",value:"opaque-history-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  if(options.stored!==undefined)await page.addInitScript(({key,value})=>sessionStorage.setItem(key,JSON.stringify(value)),{key,value:options.stored});
  await page.route("**/api/**",async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:owner,email:"history@example.test",display_name:"隔离编辑",role:"admin",capabilities:["access_back_office","can_view_evidence","can_publish_authority"],reading_preferences:{}}});
    if(url.pathname.endsWith(`/knowledge-publications/topic/${id}/history/`)){
      if(request.method()==="GET")return fail?route.fulfill({status:503,json:{detail:"隔离历史暂不可用"}}):route.fulfill({json:payload()});
      writes.push({body:request.postDataJSON(),owner:request.headers()["x-editor-owner"]});saved=true;
      if(options.lost&&writes.length===1)return route.abort("failed");
      return route.fulfill({status:202,json:{revision_id:draft,revision:2,status:"draft",object_type:"topic",object_id:id,edit_version:"b".repeat(64)}});
    }
    if(url.pathname.endsWith("/knowledge-publications/status/"))return route.fulfill({json:{event_id:null,state:"not_started",label:"尚无发布任务",can_retry:false,failures:[]}});
    return route.fulfill({json:{count:0,results:[]}});
  });
  await page.goto(`/admin/publication/knowledge/topic/${id}?return_to=${encodeURIComponent(`/admin/topics/${id}?section=versions`)}`);
  await expect(page.getByRole("heading",{name:"隔离主题历史",exact:true})).toBeVisible();
  return {writes,fail:()=>{fail=true;},switchOwner:()=>{owner=2;}};
}
async function confirm(page:Page,restore=false){
  await page.getByRole("button",{name:restore?"恢复所选历史版本":"撤回当前公开内容",exact:true}).click();
  const dialog=page.getByRole("dialog");await expect(dialog.getByRole("button",{name:"确认保存草稿"})).toBeDisabled();
  await dialog.getByLabel("操作说明").fill("已核对历史内容与影响范围");await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button",{name:"确认保存草稿"}).click();
}
test("withdrawal records owner/version and stops at a draft",async({page})=>{
  const {writes}=await setup(page);await confirm(page);
  await expect(page.getByRole("status").filter({hasText:"公开内容尚未改变"})).toBeVisible();
  expect(writes).toHaveLength(1);expect(writes[0]).toMatchObject({owner:"1",body:{action:"withdraw",expected_version:version,reason:"已核对历史内容与影响范围"}});
  expect(writes[0].body).not.toHaveProperty("source_revision_id");expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeNull();
  await expect(page.getByRole("link",{name:"进入发布前检查"})).toHaveAttribute("href",new RegExp("edit_version=b{64}"));
});
test("restore is bound to the selected historical revision",async({page})=>{
  const {writes}=await setup(page);await confirm(page,true);
  await expect(page.getByRole("status").filter({hasText:"草稿已保存"})).toBeVisible();
  expect(writes).toHaveLength(1);expect(writes[0].body).toMatchObject({action:"restore",source_revision_id:revision,expected_version:version});
});
test("lost response survives reload and retries the exact original command",async({page})=>{
  const {writes}=await setup(page,{lost:true});await confirm(page);
  await page.getByRole("dialog").getByRole("button",{name:"取消"}).click();await page.reload();
  await expect(page.getByRole("heading",{name:"原操作结果待核对"})).toBeVisible();
  await expect(page.getByRole("button",{name:"撤回当前公开内容",exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"核对原请求",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"草稿已保存"})).toBeVisible();expect(writes).toHaveLength(2);expect(writes[1]).toEqual(writes[0]);
});
test("manual draft and foreign local receipt prevent new commands",async({page})=>{
  const {writes}=await setup(page,{pendingDraft:true,stored:{format:1,owner:"2",objectType:"topic",objectId:id,command:{}}});
  await expect(page.getByRole("button",{name:"撤回当前公开内容",exact:true})).toBeDisabled();await expect(page.getByRole("button",{name:"恢复所选历史版本",exact:true})).toBeDisabled();
  await expect(page.getByRole("alert").filter({hasText:"本标签页记录不可用"})).toBeVisible();expect(writes).toHaveLength(0);
  await page.getByRole("button",{name:"已核对历史，清除本标签页记录"}).click();
  const dialog=page.getByRole("dialog",{name:"核对原操作记录"});
  await expect(dialog.getByRole("button",{name:"确认清除本地记录"})).toBeDisabled();
  await dialog.getByRole("checkbox").check();await dialog.getByRole("button",{name:"确认清除本地记录"}).click();
  await expect(page.getByRole("status").filter({hasText:"已清除本标签页记录"})).toBeVisible();
  expect(writes).toHaveLength(0);expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeNull();
});
test("failed reload clears old data and owner mismatch does not write",async({page})=>{
  const {writes,switchOwner}=await setup(page);switchOwner();await page.getByRole("button",{name:"重新读取",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"登录账户已变化"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"隔离主题历史",exact:true})).toHaveCount(0);expect(writes).toHaveLength(0);
});
test("history, field comparison and real dependency counts remain accessible on mobile",async({page})=>{
  await page.setViewportSize({width:390,height:844});const {writes}=await setup(page);
  await page.getByText("说明 · 有变化",{exact:true}).click();await expect(page.getByText("历史说明",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"引用依赖",exact:true}).click();await expect(page.getByText("馆藏主题关联",{exact:true})).toBeVisible();
  await expect(page.getByText("2 条",{exact:true})).toBeVisible();expect(writes).toHaveLength(0);
});
