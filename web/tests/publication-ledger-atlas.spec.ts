import {test,expect,type Page} from "@playwright/test";
import type {components} from "../lib/api/generated/schema";

const edition="81111111-1111-4111-8111-111111111111",work="82222222-2222-4222-8222-222222222222",old="83333333-3333-4333-8333-333333333333",current="84444444-4444-4444-8444-444444444444";
async function setup(page:Page,options:{withdraw?:boolean;unknownRestore?:boolean}={}) {
  let attempts=0;
  const commands:Array<{url:string;body:Record<string,unknown>}>=[];
  const value:components["schemas"]["PublicationDesk"]={edition_id:edition,work_id:work,title:"隔离发布台验收馆藏",authors:"验收作者",version:"a".repeat(64),checked_at:"2026-10-22T03:00:00Z",
    publication:{public_state:"published",catalog_revision_active:true,publicly_visible:true,listed_publicly:true,public_url:"/works/fixture",detail:"当前正式版本仍公开。"},
    preparation:{edition_id:edition,active_revision_id:current,fingerprint:"b".repeat(64),can_publish:true,blocking:[],warnings:[],background_processing:[],changes:[{field:"title",label:"标题",before:"旧题名",after:"新题名",before_display:"旧题名",after_display:"新题名",change:"changed"}]},
    history:{count:2,page:1,pages:1,results:[{id:current,revision:2,title:"当前正式版",status:"active",created_at:"2026-10-22T02:00:00Z",activated_at:"2026-10-22T02:01:00Z",is_current:true,can_rollback:false,created_by:"验收编辑",note:"当前公开内容",changed_fields:["标题"]},{id:old,revision:1,title:"旧正式版",status:"superseded",created_at:"2026-10-21T02:00:00Z",activated_at:"2026-10-21T02:01:00Z",is_current:false,can_rollback:true,created_by:"验收编辑",note:"原公开内容保留",changed_fields:["首次发布"]}]},selected:null,review:null,
    impacts:[{title:"在线阅读与引用",detail:"保留原始定位",href:`/admin/library/works/${work}/files?edition=${edition}`}],
    dependencies:{count:0,page:1,page_size:20,results:[],summary:{catalog_evidence:0,reader_annotations:0,reader_bookmarks:0,reader_progress:0},notice:"私人记录只显示数量。",export_url:""},events:[],events_limited:false,workbench_url:`/admin/library/works/${work}?edition=${edition}#publication`,preview_url:`/admin/preview/works/${edition}`,notice:"仅已有依赖，不推算访问量。"};
  await page.context().addCookies([{name:"stl_access",value:"opaque-publication-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  await page.route("**/api/**",async route=>{const req=route.request(),url=new URL(req.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:1,display_name:"验收编辑",email:"ledger@example.test",role:"admin",capabilities:["access_back_office","can_publish_work",...(options.withdraw===false?[]:["can_withdraw_work"])],reading_preferences:{}}});
    if(url.pathname.endsWith("/workflows/queue/"))return route.fulfill({json:{count:1,page:1,page_size:20,total_pages:1,results:[{id:edition,edition_id:edition,work_id:work,title:value.title,source_type:"manual",workbench_url:value.workbench_url,publication:value.publication,updated_at:"2026-10-22T00:00:00Z"}]}});
    if(url.pathname.endsWith("/publication/history/")){const selected=url.searchParams.get("revision");return route.fulfill({json:{...value,selected:selected?{revision:value.history.results.find(row=>row.id===selected),changes:value.preparation.changes,notice:"历史摘要，未执行恢复。"}:null}});}
    if(url.pathname.endsWith("/cover/"))return route.fulfill({json:{image_url:""}});
    if(url.pathname.endsWith("/knowledge-status/"))return route.fulfill({json:{event_id:null,state:"not_started",can_retry:false,failures:[],label:"无任务"}});
    if(req.method()==="POST"&&(url.pathname.endsWith("/publication/")||url.pathname.endsWith("/publication/rollback/"))){commands.push({url:url.pathname,body:req.postDataJSON()});if(options.unknownRestore&&url.pathname.endsWith("/rollback/")&&attempts++===0)return route.abort("failed");return route.fulfill({json:{accepted:true,status:"publishing"}});}
    return route.fulfill({json:{count:0,results:[]}});
  });
  await page.goto(`/admin/publication?selection=${edition}`);
  await expect(page.getByRole("heading",{name:"发布台、历史与撤回",exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"进入发布前检查 →",exact:true})).toBeVisible();
  return commands;
}

test("publication history, scope and private aggregate dependencies come from the selected edition",async({page})=>{
  const commands=await setup(page);
  await expect(page.getByRole("table",{name:"正式发布修订记录"})).toContainText("原公开内容保留");
  await page.getByRole("button",{name:"查看",exact:true}).last().click();
  await expect(page.getByRole("heading",{name:"历史修订 1",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"影响范围",exact:true}).click();await expect(page.getByText("保留原始定位",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"引用依赖",exact:true}).click();await expect(page.getByText("私人记录只显示数量。",{exact:true})).toBeVisible();expect(commands).toHaveLength(0);
});

test("withdraw requires its own capability and never borrows publish permission",async({page})=>{
  await setup(page,{withdraw:false});await expect(page.getByRole("button",{name:"撤回",exact:true})).toBeDisabled();
});

test("withdraw sends the inspected version only after reason and impact confirmation",async({page})=>{
  const commands=await setup(page);await page.getByRole("button",{name:"撤回",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"确认发布操作"});await expect(dialog.getByRole("button",{name:"确认撤回",exact:true})).toBeDisabled();
  await dialog.getByRole("textbox",{name:"操作原因",exact:true}).fill("隔离验收的撤回原因");await dialog.getByRole("checkbox").check();await dialog.getByRole("button",{name:"确认撤回",exact:true}).click();
  await expect.poll(()=>commands.length).toBe(1);expect(commands[0].body).toMatchObject({action:"withdraw",edition_id:edition,expected_version:"a".repeat(64),reason:"隔离验收的撤回原因"});
});

test("unknown restore survives reload and retries the same request identity",async({page})=>{
  const commands=await setup(page,{unknownRestore:true});await page.getByRole("button",{name:"恢复",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"确认发布操作"});await dialog.getByRole("textbox",{name:"操作原因",exact:true}).fill("核对旧版本后恢复");await dialog.getByRole("checkbox").check();await dialog.getByRole("button",{name:"确认恢复",exact:true}).click();
  await expect(page.getByRole("heading",{name:"这次操作结果尚需核对",exact:true})).toBeVisible();await page.reload();
  await expect(page.getByRole("button",{name:"重试原请求",exact:true})).toBeEnabled();await page.getByRole("button",{name:"重试原请求",exact:true}).click();
  await expect.poll(()=>commands.length).toBe(2);expect(commands[1]).toEqual(commands[0]);await expect(page.getByRole("heading",{name:"这次操作结果尚需核对",exact:true})).toHaveCount(0);
});
