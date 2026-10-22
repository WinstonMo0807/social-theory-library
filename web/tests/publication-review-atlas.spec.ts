import {test,expect,type Page} from "@playwright/test";
import type {components} from "../lib/api/generated/schema";

const edition="91111111-1111-4111-8111-111111111111",work="92222222-2222-4222-8222-222222222222",item="93333333-3333-4333-8333-333333333333";
async function setup(page:Page,options:{legacy?:boolean;blocked?:boolean;previewFailure?:boolean;conflict?:boolean}={}) {
  const commands:Record<string,unknown>[]=[],reads:string[]=[];
  const data:components["schemas"]["PublicationDesk"]={edition_id:edition,work_id:work,version:"a".repeat(64),checked_at:"2026-10-23T01:00:00Z",title:"隔离发布检查样本",authors:"隔离作者",
    publication:{public_state:"unpublished",catalog_revision_active:false,detail:"尚未公开。"},
    preparation:{edition_id:edition,active_revision_id:null,fingerprint:"b".repeat(64),can_publish:!options.blocked,blocking:options.blocked?["作者尚未确认"]:[],warnings:["本记录仅公开书目，没有可阅读或下载的文献"],background_processing:["书目检索"],changes:[{field:"title",label:"标题",before:"",after:"隔离发布检查样本",before_display:"",after_display:"隔离发布检查样本",change:"added"}]},
    history:{count:0,page:1,pages:1,results:[]},selected:null,impacts:[],dependencies:{count:0,page:1,page_size:20,results:[],summary:{catalog_evidence:0,reader_annotations:0,reader_bookmarks:0,reader_progress:0},notice:"仅显示已有数量",export_url:""},events:[],events_limited:false,workbench_url:`/admin/library/works/${work}?edition=${edition}#publication`,preview_url:`/admin/preview/works/${edition}`,notice:"隔离数据",
    review:{current:null,saved_at:"2026-10-23T00:00:00Z",saved_by:"隔离编辑",note:"隔离验收稿",page_count_before:null,page_count_after:null,relations:[{title:"关联责任者",field:"authors",count:1,items:[{id:item,label:"隔离作者",change:"added"}]}],checks:[{key:"file",title:"PDF 文件",state:"notice",detail:"仅公开书目，无阅读或下载文件",href:`/admin/library/works/${work}/files?edition=${edition}&tab=files`}]}};
  await page.context().addCookies([{name:"stl_access",value:"opaque-review-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  await page.route("**/api/**",async route=>{const request=route.request(),url=new URL(request.url());reads.push(url.pathname);
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:1,display_name:"隔离编辑",email:"review@example.test",role:"admin",capabilities:["access_back_office","can_publish_work"],reading_preferences:{}}});
    if(url.pathname.endsWith(`/intake/${item}/`))return route.fulfill({json:{context:{edition_id:edition}}});
    if(url.pathname.endsWith(`/editions/${edition}/publication/history/`))return route.fulfill({json:data});
    if(url.pathname.endsWith("/cover/"))return route.fulfill({json:{image_url:""}});
    if(request.method()==="POST"&&url.pathname.endsWith("/publication/")){commands.push(request.postDataJSON());return options.conflict?route.fulfill({status:409,json:{detail:"保存内容已变化，请重新检查。"}}):route.fulfill({json:{accepted:true}});}
    return route.fulfill({json:{count:0,results:[]}});
  });
  // Only the frame handshake is simulated here; public-page rendering has its own acceptance cases.
  await page.route("**/admin/preview/works/**",route=>route.fulfill({contentType:"text/html",body:`<!doctype html><title>隔离草稿预览</title><p>隔离草稿预览</p><script>const q=new URLSearchParams(location.search);parent.postMessage({type:'stl:publication-preview',editionId:'${edition}',version:q.get('version'),fingerprint:q.get('fingerprint'),ok:${!options.previewFailure}},location.origin);</script>`}));
  await page.goto(options.legacy?`/admin/publication/${item}`:`/admin/publication/${edition}?object=edition`);
  await expect(page.getByRole("heading",{name:"发布前检查",exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"发布对象"})).toBeVisible();
  return {commands,reads};
}

test("legacy upload identity resolves its edition before requesting the review",async({page})=>{
  const {reads,commands}=await setup(page,{legacy:true});
  expect(reads).toContain(`/api/catalog/admin/intake/${item}/`);
  expect(reads).toContain(`/api/catalog/admin/editions/${edition}/publication/history/`);
  expect(reads).not.toContain(`/api/catalog/admin/editions/${item}/publication/history/`);
  await expect(page.getByRole("link",{name:"查看版本历史 →"})).toHaveAttribute("href",`/admin/publication/${edition}?object=edition&view=history`);
  expect(commands).toHaveLength(0);
});

test("five sections and device preview lead to one explicitly confirmed saved-version publish",async({page})=>{
  const {commands}=await setup(page);
  for(const name of ["内容变化","关联内容","发布检查","版本记录"])await expect(page.getByRole("heading",{name,exact:false}).first()).toBeVisible();
  await page.getByRole("button",{name:"移动端预览",exact:true}).click();
  await expect(page.getByTitle("出版版本草稿的真实公开页面")).toHaveCSS("width","390px");
  await page.getByRole("button",{name:"完成检查后发布 →"}).click();
  const dialog=page.getByRole("dialog",{name:"确认发布操作"});
  await expect(dialog.getByRole("button",{name:"确认发布",exact:true})).toBeDisabled();
  await dialog.getByRole("checkbox").check();await dialog.getByRole("button",{name:"确认发布",exact:true}).click();
  await expect.poll(()=>commands.length).toBe(1);
  expect(commands[0]).toMatchObject({action:"publish",edition_id:edition,expected_version:"a".repeat(64),prepared_fingerprint:"b".repeat(64),confirm_warnings:true});
  await expect(page.getByText(/命令已接受/)).toBeVisible();
});

test("blockers and failed preview prevent the publish confirmation",async({page})=>{
  const {commands}=await setup(page,{blocked:true,previewFailure:true});
  await expect(page.getByText("作者尚未确认",{exact:true})).toBeVisible();
  await expect(page.getByText("预览未能确认，请重新检查后继续。",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"完成检查后发布 →"})).toBeDisabled();
  expect(commands).toHaveLength(0);
});

test("a stale publication response requires a fresh check and never reports success",async({page})=>{
  const {commands}=await setup(page,{conflict:true});
  await page.getByRole("button",{name:"完成检查后发布 →"}).click();
  const dialog=page.getByRole("dialog",{name:"确认发布操作"});await dialog.getByRole("checkbox").check();await dialog.getByRole("button",{name:"确认发布",exact:true}).click();
  await expect(page.getByText(/保存内容已变化，请重新检查/)).toBeVisible();
  await expect(page.getByText(/命令已接受/)).toHaveCount(0);expect(commands).toHaveLength(1);
});
