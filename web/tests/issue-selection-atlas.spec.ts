import {expect,test,type Page} from "@playwright/test";
import type {IssueDraft} from "../components/admin/curation/use-issue-draft";
import type {EditorialAssistance} from "../lib/api/curation-workspace.client";

const issue="51111111-1111-4111-8111-111111111111",node="52222222-2222-4222-8222-222222222222",jobId="53333333-3333-4333-8333-333333333333",suggestion="54444444-4444-4444-8444-444444444444",span="55555555-5555-4555-8555-555555555555",revision="56666666-6666-4666-8666-666666666666";
async function setup(page:Page,options:{unknownAdopt?:boolean;stale?:boolean;failed?:boolean}={}){
  const source={type:"node" as const,id:node,title:"隔离验收概念",public_eligible:true,summary:"真实资料说明占位，仅用于测试",href:"/theories/nodes/selection-fixture"};
  let value:IssueDraft={id:issue,slug:"selection-fixture",title:"选材隔离验收",issue_label:"",introduction:"人工导语",public_byline:"",cover_url:"",display_from:null,published_at:null,edit_version:"v1",items:[],body_blocks:[{id:node,type:"paragraph",text:"必须保留的人工段落"}],selection_workspace:{question:"隔离验收问题",query:"技术与社会",filters:{year_min:1800,year_max:2020,document_types:["book"]},references:[{type:"node",id:node}],materials:[{target:{type:"node",id:node},source,available:true,public_eligible:true}]}};
  let task:EditorialAssistance={id:jobId,issue_id:issue,operation:"guide",status:options.failed?"failed":"succeeded",stage:options.failed?"failed":"candidate",progress:options.failed?10:100,error_code:options.failed?"model_unavailable":"",error_message:options.failed?"本地模型暂不可用":"",source_available:true,draft_changed:Boolean(options.stale),can_adopt:!options.failed&&!options.stale,edit_version:options.stale?"old":"v1",sources:[{source_key:"s1",target:{type:"node",id:node},source}],suggestions:options.failed?[]:[{id:suggestion,kind:"paragraph",text:"待审阅的建议",source_keys:["s1"],gap:"尚缺直接原文"}],adopted_ids:[],dismissed_ids:[],question:"隔离验收问题",created_at:"2026-10-22T00:00:00Z",updated_at:"2026-10-22T00:00:00Z",created_by:"验收编辑",task_token:"isolated-token",model:null,poll_after_ms:null};
  const writes:Record<string,unknown>[]=[],actions:Record<string,unknown>[]=[],queries:Record<string,unknown>[]=[];let unknown=Boolean(options.unknownAdopt);
  await page.context().addCookies([{name:"stl_access",value:"opaque-selection-fixture",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  await page.route("**/api/**",async route=>{const req=route.request(),url=new URL(req.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:1,email:"selection@example.test",display_name:"验收编辑",role:"admin",capabilities:["access_back_office","can_edit_metadata","can_publish_authority"],reading_preferences:{}}});
    if(url.pathname.endsWith("/work-notices/"))return route.fulfill({json:{count:0,results:[],checked_at:task.created_at}});
    if(url.pathname.endsWith("/presence/"))return route.fulfill({json:{participants:[],checked_at:task.created_at,expires_after_seconds:90,shared:true,notice:""}});
    if(url.pathname===`/api/catalog/admin/recommendation-issues/${issue}/`){if(req.method()==="PUT"){const body=req.postDataJSON();writes.push(body);value={...value,...body,edit_version:"v2",selection_workspace:{...body.selection_workspace,materials:value.selection_workspace?.materials}};}return route.fulfill({json:value});}
    if(url.pathname.endsWith(`/${issue}/assistant/`)){if(req.method()==="POST"){actions.push(req.postDataJSON());return route.fulfill({status:202,json:task});}return route.fulfill({json:{count:1,page:1,total_pages:1,results:[task]}});}
    if(url.pathname.endsWith(`/assistant/${jobId}/`)){if(req.method()==="POST"){const body=req.postDataJSON();actions.push(body);expect(req.headers()["x-editor-owner"]).toBe("1");if(body.action==="adopt"&&!task.adopted_ids.length){task={...task,adopted_ids:[suggestion],edit_version:"v3"};value={...value,edit_version:"v3",body_blocks:[...value.body_blocks,{id:suggestion,type:"analysis",style:"paragraph",text:body.edits?.[suggestion]||"待审阅的建议",references:[{type:"node",id:node}]}]};}if(body.action==="dismiss")task={...task,dismissed_ids:[suggestion]};if(unknown){unknown=false;return route.abort("failed");}}return route.fulfill({json:task});}
    if(url.pathname==="/api/catalog/discovery-search/"){queries.push(req.postDataJSON());return route.fulfill({status:202,json:{id:jobId}});}
    if(url.pathname===`/api/catalog/discovery-search/${jobId}/`)return route.fulfill({json:{id:jobId,status:"completed",mode:"standard",query:"技术与社会",passages:[{id:span,excerpt:"隔离验收原文",work:{id:node,title:"验收资料"},authors:["验收作者"],asset_id:node,document_revision_id:revision,evidence_span_id:span,pdf_page:3,reader_url:`/reader/${node}?page=3`,source_kind:"span",locator_precision:"span",match_basis:["公开索引匹配"]}],entities:[],curation:[],next_cursor:null,count:1,warnings:[],coverage_summary:{},completed_channels:[],task_progress:{completed:1,total:1,status:"completed"},retrieval_identity:{},poll_after_ms:null}});
    if(url.pathname.endsWith(`/${issue}/sources/`))return route.fulfill({json:{count:1,next:null,previous:null,results:[{target:{type:"span",id:span,document_revision_id:revision},source:{type:"span",id:span,title:"验收资料",text:"原始只读文本",public_eligible:true,page_start:3}}]}});
    return route.fulfill({json:{count:0,results:[],next:null,previous:null}});
  });
  await page.goto(`/admin/recommendations/issues/${issue}`);await page.getByRole("button",{name:"策划选材与智能助手",exact:true}).click();await expect(page.getByRole("heading",{name:"策划选材与智能助手",exact:true})).toBeVisible();
  return {writes,actions,queries,value:()=>value};
}
async function openTask(page:Page){const assistant=page.getByRole("complementary",{name:"智能助手建议"});await assistant.getByRole("button",{name:"历史记录",exact:true}).click();await assistant.getByRole("region",{name:"助手任务历史"}).getByRole("button",{name:/内容修改/}).click();return assistant;}

test("selection save keeps exact identities and excludes readonly source payloads",async({page})=>{
  const state=await setup(page);await page.getByRole("button",{name:"修改问题",exact:true}).click();await page.getByRole("textbox",{name:"策划问题",exact:true}).fill("新策划问题");await page.getByRole("button",{name:"保存",exact:true}).click();await expect.poll(()=>state.writes.length).toBe(1);
  expect(state.writes[0].selection_workspace).toMatchObject({question:"新策划问题",references:[{type:"node",id:node}]});expect(state.writes[0].selection_workspace).not.toHaveProperty("materials");expect(state.value().body_blocks[0].text).toBe("必须保留的人工段落");
});
test("material query uses the existing discovery endpoint and rechecks exact revision",async({page})=>{
  const state=await setup(page);await page.getByRole("button",{name:"按当前范围查找原文"}).click();await expect(page.getByText("隔离验收原文",{exact:true})).toBeVisible();expect(state.queries).toEqual([{q:"技术与社会",filters:{year_min:1800,year_max:2020,document_types:["book"]}}]);await page.getByRole("button",{name:"加入已选",exact:true}).click();await page.getByRole("button",{name:"保存",exact:true}).click();await expect.poll(()=>state.writes.length).toBe(1);expect((state.writes[0].selection_workspace as {references:unknown[]}).references).toContainEqual({type:"span",id:span,document_revision_id:revision});
});
test("edited adoption retries one receipt and appends without replacing manual prose",async({page})=>{
  const state=await setup(page,{unknownAdopt:true}),assistant=await openTask(page);await assistant.getByRole("button",{name:"修改",exact:true}).click();await assistant.getByRole("textbox",{name:"审阅修改"}).fill("管理员审阅后的文字");await assistant.getByRole("button",{name:"采用",exact:true}).click();
  await expect(page.getByRole("button",{name:"继续编辑 →",exact:true})).toBeDisabled();await expect(page.getByRole("button",{name:"智能材料建议",exact:true}).last()).toBeDisabled();await expect(page.getByRole("button",{name:"保存",exact:true})).toBeDisabled();
  await assistant.getByRole("button",{name:"重试同一请求"}).click();await expect(assistant.getByText("已追加到文章草稿，原有人工段落保留。",{exact:true})).toBeVisible();expect(state.actions).toHaveLength(2);expect(state.actions[1]).toEqual(state.actions[0]);expect(state.value().body_blocks.map(row=>row.text)).toEqual(["必须保留的人工段落","管理员审阅后的文字"]);
});
test("stale suggestions cannot be adopted but may be explicitly ignored",async({page})=>{
  const state=await setup(page,{stale:true}),assistant=await openTask(page);await expect(assistant.getByRole("button",{name:"采用",exact:true})).toBeDisabled();await assistant.getByRole("button",{name:"忽略",exact:true}).click();await expect(assistant.getByText("导读 · 已忽略",{exact:true})).toBeVisible();expect(state.actions[0].action).toBe("dismiss");expect(state.value().body_blocks).toHaveLength(1);
});
test("model failure keeps selected materials and never generates on opening",async({page})=>{
  const state=await setup(page,{failed:true}),assistant=await openTask(page);await expect(assistant.getByRole("heading",{name:"智能助手暂不可用"})).toBeVisible();await expect(page.getByRole("complementary",{name:"馆藏范围与已选材料"}).getByRole("heading",{name:"隔离验收概念"})).toBeVisible();expect(state.actions).toHaveLength(0);expect(state.queries).toHaveLength(0);
});
test("mobile workbench switches between selection and assistant without overflow",async({page})=>{
  await page.setViewportSize({width:390,height:844});await setup(page);await page.getByRole("navigation",{name:"策划选材视图"}).getByRole("button",{name:"提纲建议",exact:true}).click();await expect(page.getByRole("complementary",{name:"智能助手建议"})).toBeVisible();await expect(page.getByRole("complementary",{name:"馆藏范围与已选材料"})).toBeHidden();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.getByRole("button",{name:"继续编辑 →",exact:true}).click();await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue("选材隔离验收");
});
