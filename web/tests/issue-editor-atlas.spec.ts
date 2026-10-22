import {expect,test,type Page} from "@playwright/test";
import type {IssueDraft} from "../components/admin/curation/use-issue-draft";

const issueId="11111111-1111-4111-8111-111111111111", blockId="22222222-2222-4222-8222-222222222222", oldId="33333333-3333-4333-8333-333333333333";
const initial:IssueDraft={id:issueId,slug:"editor-contract-only",title:"仅供隔离验收的专题",issue_label:"",introduction:"人工导语",public_byline:"",cover_url:"",cover_rendition_id:null,display_from:null,published_at:null,items:[],edit_version:"v1",has_unpublished_changes:true,saved_at:"2026-10-22T00:00:00Z",saved_by:"验收编辑",saved_revision:1,body_blocks:[{id:blockId,type:"paragraph",text:"人工正文"}]};
async function setup(page:Page, options:{unknown?:boolean;conflict?:boolean;source?:boolean;unknownDiscard?:boolean;presenceFailure?:boolean}={}) {
  let value=structuredClone(initial);const writes:Record<string,unknown>[]=[];let fail=Boolean(options.unknown),discardFail=Boolean(options.unknownDiscard);const dismissals:Record<string,unknown>[]=[];let discarded=false;
  if(options.source)value.body_blocks=[{id:blockId,type:"evidence",text:"本页解释",target:{type:"span",id:oldId},resolved_sources:[{type:"span",id:oldId,title:"验收原文",text:"真实来源只读",page_start:3,reader_url:"/reader/test?page=3"}],source_status:"available"}];
  await page.context().addCookies([{name:"stl_access",value:"opaque-editor-contract",domain:"127.0.0.1",path:"/",httpOnly:true,sameSite:"Lax"}]);
  await page.route("**/api/**",async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.pathname==="/api/auth/me/")return route.fulfill({json:{id:1,email:"editor@example.test",display_name:"验收编辑",role:"admin",capabilities:["access_back_office","can_edit_metadata","can_publish_authority"],reading_preferences:{}}});
    if(url.pathname.endsWith("/work-notices/"))return route.fulfill({json:{count:0,results:[],checked_at:initial.saved_at}});
    if(url.pathname.endsWith(`/${issueId}/presence/`))return options.presenceFailure?route.fulfill({status:503,json:{detail:"协作状态暂时不可用"}}):route.fulfill({json:{participants:[{id:"1",name:"验收编辑",is_self:true,mode:"viewing",last_seen:initial.saved_at}],checked_at:initial.saved_at,expires_after_seconds:90,shared:true,notice:"显示最近90秒内实际连接状态；不代表内容已保存。"}});
    if(url.pathname.endsWith(`/${issueId}/suggestions/`)){
      if(req.method()==="POST"){dismissals.push(req.postDataJSON());if(discardFail){discardFail=false;return route.abort("failed");}discarded=true;return route.fulfill({json:{dismissed:true,key:"candidate-1"}});}
      return route.fulfill({json:{results:discarded?[]:[{key:"candidate-1",token:"opaque-test-candidate",kind:"concept",target:{type:"node",id:oldId},source:{type:"node",id:oldId,title:"隔离验收概念",summary:"供契约验收的资料说明",href:"/theories/nodes/contract"},reason:"匹配已保存文章关键词，请核对关系。"}],query:"隔离验收",kind:"all",batch:1,has_more:false,edit_version:value.edit_version,checked_at:initial.saved_at,notice:"建议尚未写入正文。"}});
    }
    if(url.pathname.endsWith(`/${issueId}/history/`))return route.fulfill({json:{count:1,next:null,previous:null,results:[{id:oldId,revision:1,status:"superseded",created_at:initial.saved_at,created_by:"另一位编辑",note:"保存草稿",is_current:false,block_count:1}]}});
    if(url.pathname===`/api/catalog/admin/recommendation-issues/${issueId}/`){
      if(req.method()==="PUT"){
        const body=req.postDataJSON();writes.push(body);
        expect(req.headers()["x-editor-owner"]).toBe("1");
        if(options.conflict)return route.fulfill({status:409,json:{detail:"另一位管理员已修改"}});
        if(fail){fail=false;return route.abort("failed");}
        value={...value,...body,edit_version:"v2",saved_revision:2,request_found:true,is_current_revision:true};return route.fulfill({json:value});
      }
      if(url.searchParams.has("request_id"))return route.fulfill({json:{...value,request_found:false}});
      if(url.searchParams.has("revision"))return route.fulfill({json:{...initial,title:"历史标题",viewed_revision_id:oldId,viewed_revision:1}});
      return route.fulfill({json:value});
    }
    if(url.pathname.endsWith(`/${issueId}/preview/`))return route.fulfill({json:value});
    return route.fulfill({json:{results:[],count:0,next:null,previous:null}});
  });
  await page.goto(`/admin/recommendations/issues/${issueId}`);
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue(initial.title);
  return {writes,dismissals};
}

test("saved title autosaves after idle without publishing",async({page})=>{
  await page.clock.install();const state=await setup(page);
  await page.getByRole("textbox",{name:"标题",exact:true}).fill("修改后的专题");
  await page.clock.fastForward(10050);
  await expect(page.getByText("草稿已自动保存。",{exact:true})).toBeVisible();
  expect(state.writes).toHaveLength(1);expect(state.writes[0].autosave).toBe(true);
  expect(state.writes[0].request_id).toEqual(expect.any(String));
});
test("unknown response retries exactly the original command",async({page})=>{
  const state=await setup(page,{unknown:true});
  await page.getByRole("textbox",{name:"标题",exact:true}).fill("断线输入");
  await page.getByRole("button",{name:"保存",exact:true}).click();
  await expect(page.getByRole("button",{name:"查回保存结果"})).toBeVisible();
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"查回保存结果"}).click();
  await expect(page.getByText("尚未查到这次保存。",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"重试原保存"}).click();
  await expect(page.getByText("草稿已保存。",{exact:true})).toBeVisible();
  expect(state.writes).toHaveLength(2);expect(state.writes[1]).toEqual(state.writes[0]);
});
test("reload offers local input without caching readonly source excerpts",async({page})=>{
  await setup(page,{source:true});
  await page.getByRole("textbox",{name:"标题",exact:true}).fill("尚未保存的输入");
  await expect.poll(()=>page.evaluate(()=>sessionStorage.getItem("stl:issue-draft:v1:1:11111111-1111-4111-8111-111111111111"))).toContain("尚未保存的输入");
  const raw=await page.evaluate(()=>sessionStorage.getItem("stl:issue-draft:v1:1:11111111-1111-4111-8111-111111111111"));expect(raw).not.toContain("真实来源只读");
  page.on("dialog",dialog=>dialog.accept());await page.reload();
  await page.getByRole("button",{name:"恢复本标签页输入"}).click();
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue("尚未保存的输入");
});
test("source text stays readonly while guide remains editable",async({page})=>{
  await setup(page,{source:true});
  await page.getByRole("button",{name:/原文 本页解释/}).click();
  await expect(page.getByText("真实来源只读",{exact:true}).first()).toBeVisible();
  await expect(page.getByRole("textbox",{name:"本页导读 / 说明"})).toHaveValue("本页解释");
  expect(await page.locator("textarea").evaluateAll(rows=>rows.some(row=>(row as HTMLTextAreaElement).value==="真实来源只读"))).toBe(false);
});
test("historical restore remains unsaved until explicit save",async({page})=>{
  await page.clock.install();const state=await setup(page);
  await page.getByLabel("更多编辑操作").click();await page.getByRole("button",{name:"版本历史",exact:true}).click();
  const history=page.getByRole("dialog",{name:"专题版本历史"});await history.getByRole("button",{name:/修订 1/}).click();
  await history.getByRole("button",{name:"将修订 1 恢复到编辑区"}).click();
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue("历史标题");
  await page.clock.fastForward(15000);expect(state.writes).toHaveLength(0);
  await page.getByRole("button",{name:"保存",exact:true}).click();
  await expect.poll(()=>state.writes.length).toBe(1);expect(state.writes[0].restore_revision_id).toBe(oldId);
});
test("conflict preserves typed content and exposes explicit comparison",async({page})=>{
  await setup(page,{conflict:true});await page.getByRole("textbox",{name:"标题",exact:true}).fill("冲突中的输入");
  await page.getByRole("button",{name:"保存",exact:true}).click();
  await expect(page.getByRole("textbox",{name:"标题",exact:true})).toHaveValue("冲突中的输入");
  await page.getByRole("button",{name:"读取最新内容并比较"}).click();
  await expect(page.getByRole("heading",{name:"最新已保存内容"})).toBeVisible();
  await expect(page.getByRole("button",{name:"发布",exact:true})).toBeDisabled();
});
test("mobile edit preview structure and modal focus remain reachable",async({page})=>{
  await page.setViewportSize({width:390,height:844});await setup(page);
  const tabs=page.getByRole("navigation",{name:"编辑器视图"});await tabs.getByRole("button",{name:"预览",exact:true}).click();
  await expect(page.getByRole("heading",{name:initial.title,exact:true})).toBeVisible();
  await tabs.getByRole("button",{name:"结构",exact:true}).click();
  await page.getByRole("navigation",{name:"正文结构定位"}).getByRole("button",{name:/人工正文/}).click();
  await expect(page.getByRole("textbox",{name:"内容",exact:true})).toHaveValue("人工正文");
  const insert=page.getByRole("button",{name:"插入内容块",exact:true});await insert.click();
  await expect(page.getByRole("dialog",{name:"插入内容块"})).toBeVisible();await page.keyboard.press("Escape");await expect(insert).toBeFocused();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test("formatting is saved on guide only and shared by the article preview",async({page})=>{
  const state=await setup(page,{source:true});await page.getByRole("button",{name:/原文 本页解释/}).click();
  const guide=page.getByRole("textbox",{name:"本页导读 / 说明"});await guide.fill("中文😀导读");
  await guide.evaluate((node:HTMLTextAreaElement)=>{node.focus();node.setSelectionRange(0,4);node.dispatchEvent(new Event("select",{bubbles:true}));});
  await page.getByRole("button",{name:"加粗所选文字"}).click();
  await expect(page.getByRole("complementary",{name:"文章预览与结构"}).locator("strong").filter({hasText:"中文😀"})).toBeVisible();
  await page.getByRole("button",{name:"保存",exact:true}).click();await expect.poll(()=>state.writes.length).toBe(1);
  const block=(state.writes[0].body_blocks as Array<Record<string,unknown>>)[0];expect(block.text_marks).toEqual([{start:0,end:4,kind:"strong"}]);expect(block).not.toHaveProperty("resolved_sources");
  expect(JSON.stringify(state.writes[0])).not.toContain("真实来源只读");
});
test("unsafe prose links cannot be applied",async({page})=>{
  await setup(page);await page.getByRole("button",{name:/导读 人工正文/}).click();
  await page.getByRole("textbox",{name:"内容",exact:true}).evaluate((node:HTMLTextAreaElement)=>{node.focus();node.setSelectionRange(0,2);node.dispatchEvent(new Event("select",{bubbles:true}));});
  await page.getByRole("button",{name:"为所选文字添加链接"}).click();const dialog=page.getByRole("dialog",{name:"设置导读链接"});
  await dialog.getByRole("textbox",{name:"链接地址"}).fill("javascript:alert(1)");await expect(dialog.getByRole("button",{name:"应用链接"})).toBeDisabled();
  await dialog.getByRole("textbox",{name:"链接地址"}).fill("/topics/contract");await dialog.getByRole("button",{name:"应用链接"}).click();
  await expect(page.getByRole("complementary",{name:"文章预览与结构"}).getByRole("link",{name:"人工"})).toHaveAttribute("href","/topics/contract");
});
test("material insertion preserves the canonical target and remains a draft",async({page})=>{
  const state=await setup(page);await page.getByRole("button",{name:"智能材料建议",exact:true}).last().click();
  const panel=page.getByRole("region",{name:"智能材料建议"});await expect(panel.getByRole("heading",{name:"隔离验收概念"})).toBeVisible();
  expect(state.writes).toHaveLength(0);await panel.getByRole("button",{name:"插入到文章",exact:true}).click();
  await expect(panel.getByRole("button",{name:"已在正文",exact:true})).toBeDisabled();expect(state.writes).toHaveLength(0);
  await page.getByRole("button",{name:"保存",exact:true}).click();await expect.poll(()=>state.writes.length).toBe(1);
  const added=(state.writes[0].body_blocks as Array<Record<string,unknown>>)[1];expect(added.target).toEqual({type:"node",id:oldId});expect(added).not.toHaveProperty("resolved_sources");expect(added.text).toBe("");
});
test("unknown discard retries the same receipt and never edits article",async({page})=>{
  const state=await setup(page,{unknownDiscard:true});await page.getByRole("button",{name:"智能材料建议",exact:true}).last().click();
  const panel=page.getByRole("region",{name:"智能材料建议"});await panel.getByRole("button",{name:"放弃这条建议"}).click();await panel.getByRole("button",{name:"重试放弃"}).click();
  await expect(panel.getByText("已放弃这条建议，当前正文保持原样。",{exact:true})).toBeVisible();expect(state.dismissals).toHaveLength(2);expect(state.dismissals[1]).toEqual(state.dismissals[0]);expect(state.writes).toHaveLength(0);
});
test("presence failure is shown explicitly without invented online people",async({page})=>{
  await setup(page,{presenceFailure:true});const panel=page.getByRole("region",{name:"协作与版本"});await expect(panel.getByText(/协作状态暂时不可用/)).toBeVisible();await expect(panel.getByText(/浏览中/)).toHaveCount(0);await expect(panel.getByRole("button",{name:"查看全部版本"})).toBeVisible();
});
test("mobile suggestions expose real material and close detail with keyboard",async({page})=>{
  await page.setViewportSize({width:390,height:844});await setup(page);await page.getByRole("button",{name:"智能材料建议",exact:true}).last().click();
  const panel=page.getByRole("region",{name:"智能材料建议"});await panel.getByRole("button",{name:"概念",exact:true}).click();const button=panel.getByRole("button",{name:"查看",exact:true});await button.click();
  await expect(page.getByRole("dialog",{name:"材料建议详情"}).getByRole("link",{name:"打开资料原页 ↗"})).toHaveAttribute("href","/theories/nodes/contract");await page.keyboard.press("Escape");await expect(button).toBeFocused();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
