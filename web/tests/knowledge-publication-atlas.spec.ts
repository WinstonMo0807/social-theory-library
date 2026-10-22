import {test,expect,type Page} from "@playwright/test";
import {projectTopic} from "../components/admin/knowledge/topic-preview";

// Isolated API projections exercise the UI contract, not live providers or visual acceptance.
const id="61111111-1111-4111-8111-111111111111",revisionId="62222222-2222-4222-8222-222222222222";
const version="a".repeat(64),key=`stl:knowledge-publish:v1:1:topic:${id}`;
async function setup(page:Page,options:{existing?:boolean;withdraw?:boolean;lost?:boolean;stale?:boolean;stored?:unknown;blocking?:boolean;frameFailure?:boolean}={}) {
  const writes:Array<{method:string;path:string;body:unknown;owner:string|undefined;version:string|undefined}>=[];
  let published=false,detailReads=0,previewFailure=false,owner=1;
  const revision=()=>({id:revisionId,target_type:"topic",target_id:id,status:published?"published":"draft"});
  const record=()=>({id,name:"隔离主题发布样本",slug:"isolated-publication-topic",description:"已保存的说明",editorial_status:options.withdraw?"archived":options.existing||published?"published":"draft",edit_version:options.stale&&detailReads>1?"b".repeat(64):version,editorial_revision:options.existing&&!published?revision():null,key_concepts:[],timeline:[],curation:{},parent:null,works:[],disciplines:[],core_questions:[],research_dimensions:[],methods:[]});
  const perspective=()=>({source:"editorial_revision",available:true,serializer:"Topic",data:projectTopic({},record())});
  const report=()=>({checked_at:"2026-10-23T09:00:00Z",saved_at:"2026-10-23T08:00:00Z",current_revision:options.existing?1:0,draft_revision_id:options.existing?revisionId:null,has_draft:!published,withdrawing:Boolean(options.withdraw),actor_label:"隔离编辑",blocking_count:options.blocking?1:0,warning_count:0,can_publish:!published&&!options.blocking,checks:options.blocking?[{code:"fixture",severity:"blocking",title:"保存内容需要修正",detail:"隔离校验阻断",section:"identity"}]:[{code:"source_review",severity:"notice",title:"原文与关联内容需人工核对",detail:"请核对引用",section:"passages"}],changes:[{key:"intro",label:"主题导读",before:{description:"当前公开说明"},after:{description:"已保存的说明"},changed:true}]});
  await page.context().addCookies([{name:"stl_access",value:"opaque-knowledge-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  if(options.stored!==undefined)await page.addInitScript(({key,value})=>sessionStorage.setItem(key,JSON.stringify(value)),{key,value:options.stored});
  await page.route("**/api/**",async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:owner,email:"knowledge@example.test",display_name:"隔离编辑",role:"admin",capabilities:["access_back_office","can_edit_draft_authority","can_publish_authority","can_view_evidence"],reading_preferences:{}}});
    if(req.method()!=="GET"&&!url.pathname.includes("knowledge-preview"))writes.push({method:req.method(),path:url.pathname,body:req.postDataJSON(),owner:req.headers()["x-editor-owner"],version:req.headers()["if-match"]});
    if(url.pathname.endsWith(`/topics/${id}/`)){
      if(req.method()==="GET")detailReads++;
      if(req.method()==="PATCH")published=true;
      return route.fulfill({json:record()});
    }
    if(url.pathname.endsWith(`/knowledge-preview/topic/${id}/`))return previewFailure||options.frameFailure&&req.method()==="GET"&&!url.searchParams.has("review")?route.fulfill({status:503,json:{detail:"隔离预览暂不可用"}}):route.fulfill({json:{edit_version:version,preview_mode:true,protected:true,object_type:"topic",object_id:id,label:"隔离主题发布样本",status:"published",active_perspective:"draft",perspective:perspective(),perspectives:{draft:perspective(),published:{...perspective(),data:{...perspective().data,description:"当前公开说明"}}},preview_routes:{draft:`/admin/preview/knowledge/topic/${id}`},...(url.searchParams.get("review")==="1"?{publication_review:report()}:{})}});
    if(url.pathname.endsWith(`/editorial-revisions/${revisionId}/publish/`)){published=true;if(options.lost)return route.abort("failed");return route.fulfill({json:revision()});}
    if(url.pathname.endsWith(`/editorial-revisions/${revisionId}/`))return route.fulfill({json:revision()});
    if(url.pathname.endsWith("/knowledge-workspace/"))return route.fulfill({json:{studio:{selection:null}}});
    return route.fulfill({json:{count:0,results:[]}});
  });
  await page.goto(`/admin/topics/${id}?section=publication`);
  const panel=page.getByRole("region",{name:"知识对象发布",exact:true});await expect(panel).toBeVisible();
  return {panel,writes,failPreviews:()=>{previewFailure=true;},changeOwner:()=>{owner=2;}};
}
async function confirm(page:Page,withdraw=false) {
  await page.getByRole("button",{name:"进入完整发布检查",exact:true}).click();
  await expect(page.getByRole("heading",{name:"真实预览与发布检查",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"发布前检查",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"知识对象发布前检查"});
  await expect(dialog.getByText("已保存的说明",{exact:true})).toBeVisible();
  const submit=dialog.getByRole("button",{name:withdraw?"确认撤回公开展示":"确认发布",exact:true});
  await expect(submit).toBeDisabled();await dialog.getByRole("checkbox").check();await submit.click();
}

test("first publication binds owner and the saved version after explicit confirmation",async({page})=>{
  const {writes,panel}=await setup(page);await confirm(page);
  await expect(panel.getByRole("status").filter({hasText:"发布操作已确认"})).toBeVisible();
  expect(writes).toEqual([{method:"PATCH",path:`/api/catalog/admin/topics/${id}/`,body:{editorial_status:"published"},owner:"1",version}]);
  expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeNull();
});

test("lost publish receipt rechecks the original revision without a second publish",async({page})=>{
  const {writes,panel}=await setup(page,{existing:true,lost:true});await confirm(page);
  await expect(panel.getByRole("heading",{name:"原发布操作待核对"})).toBeVisible();
  expect(JSON.parse((await page.evaluate(key=>sessionStorage.getItem(key),key))!)).toMatchObject({phase:"publish",revisionId,owner:"1",objectId:id});
  await panel.getByRole("button",{name:"重试原阶段"}).click();
  await expect(panel.getByRole("status").filter({hasText:"发布操作已确认"})).toBeVisible();expect(writes).toHaveLength(1);
  expect(writes[0].path).toBe(`/api/catalog/admin/editorial-revisions/${revisionId}/publish/`);
});

test("saved withdrawal keeps its original revision and is never rewritten to published",async({page})=>{
  const {writes,panel}=await setup(page,{existing:true,withdraw:true});await confirm(page,true);
  await expect(panel.getByRole("status").filter({hasText:"发布操作已确认"})).toBeVisible();
  expect(writes).toHaveLength(1);expect(writes[0].method).toBe("POST");expect(writes[0].body).toEqual({});
});

test("changed saved version cannot open an actionable confirmation",async({page})=>{
  const {writes}=await setup(page,{stale:true});await page.getByRole("button",{name:"进入完整发布检查",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("保存内容已变化");
  await expect(page.getByRole("button",{name:"发布前检查",exact:true})).toBeDisabled();expect(writes).toHaveLength(0);
});

test("foreign or malformed pending records block publication without issuing mutations",async({page})=>{
  const {writes,panel}=await setup(page,{stored:{format:1,owner:"2",objectType:"topic",objectId:id,phase:"publish",version,revisionId}});
  await expect(panel.getByRole("heading",{name:"原发布操作待核对"})).toBeVisible();
  await expect(panel.getByRole("button",{name:"进入完整发布检查",exact:true})).toBeDisabled();
  await expect(panel.getByRole("button",{name:"重试原阶段"})).toHaveCount(0);expect(writes).toHaveLength(0);
});

test("full preview links preserve the reviewed version and failed reload removes the prior content",async({page})=>{
  const {writes,failPreviews}=await setup(page);await page.getByRole("button",{name:"进入完整发布检查",exact:true}).click();await page.getByRole("button",{name:"发布前检查",exact:true}).click();
  const link=page.getByRole("dialog",{name:"知识对象发布前检查"}).getByRole("link",{name:"打开完整预览 ↗"});
  await expect(link).toHaveAttribute("href",`/admin/preview/knowledge/topic/${id}?edit_version=${version}`);
  await page.goto((await link.getAttribute("href"))!);
  await expect(page.locator(".admin-knowledge-page-preview-body h1")).toHaveText("隔离主题发布样本");
  failPreviews();await page.getByRole("button",{name:"重新读取保存版本"}).click();
  await expect(page.getByRole("alert")).toContainText("隔离预览暂不可用");
  await expect(page.locator(".admin-knowledge-page-preview-body")).toHaveCount(0);expect(writes).toHaveLength(0);
});

test("cookie owner change rejects reload and clears previously visible private preview",async({page})=>{
  const {writes,changeOwner}=await setup(page);
  await page.goto(`/admin/preview/knowledge/topic/${id}?edit_version=${version}`);
  await expect(page.locator(".admin-knowledge-page-preview-body")).toBeVisible();changeOwner();
  await page.getByRole("button",{name:"重新读取保存版本"}).click();
  await expect(page.getByRole("alert")).toContainText("登录账户已变化");
  await expect(page.locator(".admin-knowledge-page-preview-body")).toHaveCount(0);expect(writes).toHaveLength(0);
});

test("review keeps four areas and reuses the same public page in both viewports",async({page})=>{
  const {writes}=await setup(page);await page.getByRole("button",{name:"进入完整发布检查"}).click();
  const nav=page.getByRole("navigation",{name:"发布检查视图"});
  await expect(nav.getByRole("button")).toHaveCount(4);
  const iframe=page.locator('iframe[title="知识对象已保存版本的真实页面预览"]');
  await expect(iframe).toHaveAttribute("src",new RegExp(`edit_version=${version}`));
  await expect(page.getByRole("button",{name:"发布前检查",exact:true})).toBeEnabled();
  await page.getByRole("button",{name:"移动端",exact:true}).click();await expect(iframe).toHaveAttribute("data-device","mobile");
  await nav.getByRole("button",{name:"版本变化"}).click();await expect(page.getByRole("table")).toContainText("已保存的说明");
  await nav.getByRole("button",{name:"发布检查"}).click();await expect(page.getByRole("link",{name:"定位 →"})).toHaveAttribute("href",new RegExp("section=passages"));
  await nav.getByRole("button",{name:"发布设置"}).click();await expect(page.getByText("公开（所有读者可见）",{exact:true})).toBeVisible();expect(writes).toHaveLength(0);
});

test("failed frame never enables publication even when the saved checks loaded",async({page})=>{
  const {writes}=await setup(page,{frameFailure:true});await page.getByRole("button",{name:"进入完整发布检查"}).click();
  await expect(page.getByRole("alert")).toContainText("预览读取失败或超时");
  await page.evaluate(({id,version})=>window.postMessage({type:"stl:knowledge-publication-preview",objectType:"topic",objectId:id,owner:"1",version,pageId:"overview",state:"ready",ok:true},window.location.origin),{id,version});
  await expect(page.getByRole("button",{name:"发布前检查",exact:true})).toBeDisabled();expect(writes).toHaveLength(0);
});

test("server blockers remain actionable and do not become a successful check",async({page})=>{
  const {writes}=await setup(page,{blocking:true});await page.getByRole("button",{name:"进入完整发布检查"}).click();
  await expect(page.getByRole("heading",{name:"保存内容需要修正"})).toBeVisible();
  await expect(page.getByRole("link",{name:"定位 →"})).toHaveAttribute("href",new RegExp("section=identity"));
  await expect(page.getByRole("button",{name:"发布前检查",exact:true})).toBeDisabled();expect(writes).toHaveLength(0);
});

test("legacy selected-object links preserve the object and version-record section",async({page})=>{
  await setup(page);
  await page.goto(`/admin/knowledge?object_type=all&selected_type=topic&selected_id=${id}&section=versions`);
  await expect(page).toHaveURL(new RegExp(`/admin/topics/${id}\\?.*section=versions`));
  await expect(page.getByRole("button",{name:"版本记录",exact:true})).toHaveAttribute("aria-current","true");
});
