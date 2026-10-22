import {test,expect,type Page} from "@playwright/test";
import {projectTopic} from "../components/admin/knowledge/topic-preview";

// Isolated API projections exercise the UI contract, not live providers or visual acceptance.
const id="61111111-1111-4111-8111-111111111111",revisionId="62222222-2222-4222-8222-222222222222";
const version="a".repeat(64),key=`stl:knowledge-publish:v1:1:topic:${id}`;
async function setup(page:Page,options:{existing?:boolean;withdraw?:boolean;lost?:boolean;stale?:boolean;stored?:unknown}={}) {
  const writes:Array<{method:string;path:string;body:unknown;owner:string|undefined;version:string|undefined}>=[];
  let published=false,detailReads=0,previewFailure=false,owner=1;
  const revision=()=>({id:revisionId,target_type:"topic",target_id:id,status:published?"published":"draft"});
  const record=()=>({id,name:"隔离主题发布样本",slug:"isolated-publication-topic",description:"已保存的说明",editorial_status:options.withdraw?"archived":options.existing||published?"published":"draft",edit_version:options.stale&&detailReads>1?"b".repeat(64):version,editorial_revision:options.existing&&!published?revision():null,key_concepts:[],timeline:[],curation:{},parent:null,works:[],disciplines:[],core_questions:[],research_dimensions:[],methods:[]});
  const perspective=()=>({source:"editorial_revision",available:true,serializer:"Topic",data:projectTopic({},record())});
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
    if(url.pathname.endsWith(`/knowledge-preview/topic/${id}/`))return previewFailure?route.fulfill({status:503,json:{detail:"隔离预览暂不可用"}}):route.fulfill({json:{edit_version:version,preview_mode:true,protected:true,object_type:"topic",object_id:id,label:"隔离主题发布样本",status:"published",active_perspective:"draft",perspective:perspective(),perspectives:{draft:perspective(),published:{...perspective(),data:{...perspective().data,description:"当前公开说明"}}},preview_routes:{draft:`/admin/preview/knowledge/topic/${id}`}}});
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
  await page.getByRole("button",{name:"发布前检查",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"知识对象发布前检查"});
  await expect(dialog.getByText("已保存的说明",{exact:true})).toBeVisible();
  const submit=dialog.getByRole("button",{name:withdraw?"确认撤回公开展示":"确认发布",exact:true});
  await expect(submit).toBeDisabled();await dialog.getByRole("checkbox").check();await submit.click();
}

test("first publication binds owner and the saved version after explicit confirmation",async({page})=>{
  const {writes,panel}=await setup(page);await confirm(page);
  await expect(panel.getByRole("status")).toContainText("发布操作已确认");
  expect(writes).toEqual([{method:"PATCH",path:`/api/catalog/admin/topics/${id}/`,body:{editorial_status:"published"},owner:"1",version}]);
  expect(await page.evaluate(key=>sessionStorage.getItem(key),key)).toBeNull();
});

test("lost publish receipt rechecks the original revision without a second publish",async({page})=>{
  const {writes,panel}=await setup(page,{existing:true,lost:true});await confirm(page);
  await expect(panel.getByRole("heading",{name:"原发布操作待核对"})).toBeVisible();
  expect(JSON.parse((await page.evaluate(key=>sessionStorage.getItem(key),key))!)).toMatchObject({phase:"publish",revisionId,owner:"1",objectId:id});
  await panel.getByRole("button",{name:"重试原阶段"}).click();
  await expect(panel.getByRole("status")).toContainText("发布操作已确认");expect(writes).toHaveLength(1);
  expect(writes[0].path).toBe(`/api/catalog/admin/editorial-revisions/${revisionId}/publish/`);
});

test("saved withdrawal keeps its original revision and is never rewritten to published",async({page})=>{
  const {writes,panel}=await setup(page,{existing:true,withdraw:true});await confirm(page,true);
  await expect(panel.getByRole("status")).toContainText("发布操作已确认");
  expect(writes).toHaveLength(1);expect(writes[0].method).toBe("POST");expect(writes[0].body).toEqual({});
});

test("changed saved version cannot open an actionable confirmation",async({page})=>{
  const {writes}=await setup(page,{stale:true});await page.getByRole("button",{name:"发布前检查",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"知识对象发布前检查"});await expect(dialog.getByRole("alert")).toContainText("资料已变化");
  await expect(dialog.getByRole("button",{name:"确认发布",exact:true})).toBeDisabled();expect(writes).toHaveLength(0);
});

test("foreign or malformed pending records block publication without issuing mutations",async({page})=>{
  const {writes,panel}=await setup(page,{stored:{format:1,owner:"2",objectType:"topic",objectId:id,phase:"publish",version,revisionId}});
  await expect(panel.getByRole("heading",{name:"原发布操作待核对"})).toBeVisible();
  await expect(panel.getByRole("button",{name:"发布前检查",exact:true})).toBeDisabled();
  await expect(panel.getByRole("button",{name:"重试原阶段"})).toHaveCount(0);expect(writes).toHaveLength(0);
});

test("full preview links preserve the reviewed version and failed reload removes the prior content",async({page})=>{
  const {writes,failPreviews}=await setup(page);await page.getByRole("button",{name:"发布前检查",exact:true}).click();
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
