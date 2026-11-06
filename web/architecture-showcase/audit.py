"""Refresh reproducible source references. No API, database or secret reads.

Curated module/edge interpretations below are reviewed, not inferred from imports.
Route inventory and direct imports are extracted; implementation is never equated
with runtime acceptance. Anchor drift fails the build instead of inventing lines.
"""
from pathlib import Path
import csv, hashlib, json, re, subprocess
from datetime import datetime, timezone, timedelta

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCES = {
 'opinion-entry': ('web/components/opinion-search-entry.tsx','export function OpinionSearchEntry'),
 'opinion-client': ('web/lib/api/opinion-entry.client.ts','export async function loadOpinionScope'),
 'citation-overlay': ('web/components/shared-citation-overlay.tsx','function Workspace'),
 'research-workspace': ('web/components/research/research-session-detail.tsx','function '),
 'upload-ui': ('web/components/admin/workflow/upload-batch-view.tsx','export function'),
 'upload-policy': ('web/components/admin-upload.tsx','policy:{expected_count:'),
 'outline-ui': ('web/components/admin/library/document-outline-workspace.tsx','export function'),
 'publication-ui': ('web/components/admin/workflow/publication-review.tsx','export function'),
 'nav': ('web/components/site-header.tsx','const navigation ='),
 'brand': ('web/components/brand-image.tsx','export function BrandImage'),
 'tokens': ('web/styles/tokens/design.css',':root'),
 'type': ('web/styles/tokens/typeface.css','html[data-typeset="A"]'),
 'controls': ('web/components/ui/controls.tsx','export function Button'),
 'dialog': ('web/components/ui/dialog.tsx','export function Dialog'),
 'home': ('web/app/page.tsx','import'),
 'welcome': ('web/app/welcome/page.tsx','import'),
 'opinions': ('web/app/explore/opinions/page.tsx','export default'),
 'evidence-page': ('web/app/explore/evidence/page.tsx','export default'),
 'discovery-ui': ('web/components/discovery-search-workspace.tsx','export function DiscoverySearchWorkspace'),
 'discovery-client': ('web/lib/api/discovery.client.ts','const endpoint ='),
 'discovery-api': ('api/catalog/discovery_views.py','class DiscoverySearchView'),
 'discovery-session': ('api/catalog/services/discovery_sessions.py','def _create_session'),
 'discovery-task': ('api/catalog/discovery_tasks.py','def run_discovery_search'),
 'projection': ('api/catalog/services/discovery_projection.py','def validate_discovery_results'),
 'indexing': ('api/catalog/services/discovery_indexing.py','from'),
 'deep': ('api/catalog/services/retrieval/deep_pipeline.py','PIPELINE_VERSION ='),
 'evidence-ui': ('web/components/discovery-evidence-detail.tsx','item.reader_url'),
 'reader': ('web/app/reader/[assetId]/page.tsx','export default'),
 'reader-shell': ('web/components/reader-shell.tsx','useReaderCitation'),
 'citation': ('web/lib/api/shared-citation.client.ts','export function previewSharedCitation'),
 'citation-api': ('api/reading/shared_citation_views.py','class PublicCitationPreviewView'),
 'reader-citation': ('web/components/reader/use-reader-citation.ts','export function'),
 'research-client': ('web/lib/api/research.client.ts','export function changeResearchSelection'),
 'research-selection': ('api/reading/research.py','def change_selection'),
 'research-memory-scope': ('api/reading/research.py','def plan_memory_rows'),
 'document-outline': ('api/catalog/services/document_outline.py','def run_outline_job'),
 'publication-state': ('api/catalog/services/publication_commands.py','def catalog_publication_state'),
 'reader-access': ('web/lib/reader-access.server.ts','export async function requireReaderSession'),
 'permissions': ('api/common/permissions.py','class CanReadLibrary'),
 'admin-permissions': ('api/common/permissions.py','class CanAccessBackOffice'),
 'admin': ('web/components/admin-shell.tsx','import'),
 'models': ('api/catalog/models.py','class Work('),
 'edition': ('api/catalog/models.py','class Edition('),
 'asset': ('api/catalog/models.py','class Asset('),
 'revision': ('api/catalog/models.py','class DocumentRevision('),
 'span': ('api/catalog/models.py','class EvidenceSpan('),
 'research': ('api/reading/research_views.py','class PrivateRecordViewSet'),
 'research-model': ('api/reading/research_models.py','class PrivateResearchRecord'),
 'research-ui': ('web/app/account/research/[id]/page.tsx','import'),
 'memory': ('api/reading/research.py','def search_memories'),
 'plans': ('api/reading/plan_rules.py','def '),
 'audit': ('web/app/account/citation-audits/page.tsx','import'),
 'ingestion': ('api/ingestion/tasks.py','def process_upload_item'),
 'ocr': ('api/ingestion/services/catalog_ocr.py','def '),
 'ocr-service': ('ocr_service/requirements.txt','rapidocr=='),
 'outline': ('api/catalog/services/outline_automatic.py','from'),
 'outline-export': ('api/catalog/services/outline_exports.py','def '),
 'outline-record': ('docs/stl4/AUTOMATIC_OUTLINE_20261106.md','## 两份公开扫描文献的实际结果'),
 'publication': ('api/catalog/services/publication_commands.py','def activate_revision'),
 'pipeline': ('api/ingestion/services/pipeline.py','def run_pipeline'),
 'pipeline-index': ('api/ingestion/services/pipeline.py','result = index_asset(normalized, is_public=False)'),
 'publication-check': ('api/ingestion/services/publication.py','def publish_edition'),
 'editorial': ('api/catalog/services/editorial_issues.py','def publish_site'),
 'knowledge': ('api/catalog/services/knowledge_publication.py','def '),
 'api': ('api/config/urls.py','urlpatterns ='),
 'database': ('api/config/settings.py','DATABASES ='),
 'queue': ('api/config/settings.py','CELERY_TASK_ROUTES ='),
 'storage': ('api/config/settings.py','MEDIA_ROOT ='),
 'distribution': ('api/distribution/views.py','CanReadLibrary'),
 'dependencies': ('web/package.json','"dependencies"'),
 'compose': ('compose.yaml','  postgres:'),
 'inference': ('api/catalog/services/discovery_inference.py','def '),
 'ai': ('api/common/ai_runtime.py','PRIVATE_RESEARCH ='),
 'oauth': ('web/components/auth-form.tsx','export function AuthForm'),
 'closure': ('docs/stl4/DELIVERY_CLOSURE_20261026.md','206'),
 'progress': ('CURRENT_PROGRESS.md','## 2026-11-06 18:25'),
 'account-launch': ('CURRENT_PROGRESS.md','## 2026-11-06 首发账号、免费邮件与统一内网收口'),
}

def module(id,title,subtitle,kind,refs,children=(),routes=(),status='pending',note='',boundary=''):
 return dict(id=id,title=title,subtitle=subtitle,type=kind,level=0 if id=='stl' else 1 if children else 2,
             sources=list(refs),children=list(children),routes=list(routes),status=status,note=note,boundary=boundary)

NODES = [
 module('stl','社会理论书库','Social Theory Library','product',['nav','api','models'],['discovery','knowledge','reader','research','publishing','operations'],note='前台、私人研究与后台共用 Django 业务服务。图中分组依据当前导航和代码职责。'),
 module('discovery','发现与检索','从问题进入原文','domain',['nav','opinions','discovery-ui'],['catalogue','viewpoints','evidence'],['/explore','/explore/original','/explore/opinions','/explore/evidence'],boundary='探索与检索须登录。浏览网页与访问正文分别检查权限。'),
 module('knowledge','知识与策划','学者、理论、主题与作品','domain',['nav','knowledge','editorial'],['scholars','theories','topics','curation'],['/scholars','/theories','/topics','/recommendations'],boundary='读者页面仅展示已发布的内容和关联。'),
 module('reader','阅读与引用','原文定位、阅读与引用','domain',['reader','reader-shell','citation'],['pdf','parallel','citations'],['/reader/[assetId]'],boundary='正文与下载须登录。版本、PDF 页码与原文位置共同确定来源。'),
 module('research','私人研究','研究会话、笔记与计划','domain',['research','research-model','research-ui'],['sessions','notes','plans','audits','private-ai'],['/account/research','/account/notes','/account/plans','/account/citation-audits'],boundary='接口仅返回所属读者的记录。私人记录不直接用作公共馆藏证据。'),
 module('publishing','馆藏与内容管理','从文件到正式公开版本','domain',['admin','ingestion','publication','editorial'],['intake','processing','outline','publish'],['/admin/uploads','/admin/intake/[itemId]','/admin/processing','/admin/publication'],boundary='上传、编目、预览和发布分别检查权限。保存草稿不会自动发布。'),
 module('operations','系统与权限','身份、任务、模型与存储','domain',['admin-permissions','api','queue','ai'],['identity','jobs','model-runtime','storage-ops'],['/admin/users','/admin/system-health','/admin/settings','/admin/storage'],boundary='后台操作分别检查权限。仅具备指定配置权限的管理员可设置地址与密钥。'),
 module('catalogue','馆藏发现','作品、版本与筛选','feature',['models','edition','nav'],routes=['/explore/original','/works/[slug]']),
 module('viewpoints','观点检索','查询、筛选与后台检索','feature',['opinions','discovery-client','discovery-api','discovery-session'],routes=['/explore/opinions','/explore/evidence']),
 module('evidence','原文证据','节选、上下文与页码','feature',['span','projection','evidence-ui'],routes=['/explore/evidence']),
 module('scholars','学者','目录、详情与关联作品','feature',['nav','knowledge'],routes=['/scholars','/scholars/[slug]']),
 module('theories','理论与流派','目录、关系图与时间线','feature',['nav','knowledge'],routes=['/theories','/theories/graph','/theories/timeline','/theory-schools']),
 module('topics','主题','主题入口与内容关联','feature',['nav','knowledge'],routes=['/topics','/topics/[slug]']),
 module('curation','特别策划','专刊、文章与网站内容','feature',['editorial','welcome'],routes=['/recommendations','/recommendations/[slug]','/welcome']),
 module('pdf','PDF 阅读器','连续阅读、目录与书内检索','feature',['reader','reader-shell'],routes=['/reader/[assetId]']),
 module('parallel','并读','在同一阅读器中对照阅读','feature',['reader'],routes=['/reader/[assetId]?mode=parallel'],note='并读使用现有阅读器路由，通过 mode=parallel 切换。'),
 module('citations','引用','预览、复制与下载引用','feature',['citation','reader-shell'],note='前端调用 reading/citation-preview。结果保留 edition、原文引用与页码。'),
 module('sessions','研究会话','选取材料、比较观点与查看历史','feature',['research','research-ui','research-model'],routes=['/account/research/[id]','/account/research/[id]/compare','/account/research/[id]/counter-evidence','/account/research/[id]/history'],note='研究页面与接口已有代码。模型生成结果仍需单独验证。'),
 module('notes','笔记与记忆','阅读笔记、确认与授权','feature',['memory','research-model'],routes=['/account/notes','/account/confirmed-notes'],boundary='只使用本人明确授权的笔记。'),
 module('plans','阅读计划','规则排序与本人调整','feature',['plans','research'],routes=['/account/plans','/account/plans/[id]']),
 module('audits','引文体检','稿件解析、问题与报告','feature',['audit','research'],routes=['/account/citation-audits','/account/citation-audits/[id]']),
 module('private-ai','私人研究 API','单独配置研究模型服务','feature',['ai','progress'],status='partial',note='配置入口和凭据加密已有代码。项目记录显示，中转服务尚未配置，外部模型尚未调用。'),
 module('intake','收件与编目','上传、识别、去重与版本确认','feature',['ingestion','pipeline'],routes=['/admin/uploads','/admin/intake/[itemId]','/admin/cataloging/[sessionId]']),
 module('processing','文档处理','文本、OCR、目录与任务','feature',['ingestion','ocr','ocr-service','revision'],routes=['/admin/processing']),
 module('outline','自动目录','自动识别目录并生成 PDF 副本','feature',['outline','outline-export','outline-record'],status='pending',note='项目记录中的 2 份公开扫描件分别生成 1 项和 38 项书签。本展示引用已有记录，未重跑样本。更多书种及识别质量仍待验收。'),
 module('publish','发布与修订','预览、公开、撤回与历史','feature',['publication','publication-check','editorial','knowledge'],routes=['/admin/publication','/admin/welcome','/admin/content']),
 module('identity','身份与能力','登录会话、读者身份与管理权限','feature',['permissions','admin-permissions','research'],routes=['/login','/register','/admin/users']),
 module('jobs','异步任务','保存任务记录，由后台队列执行','feature',['queue','discovery-session','ingestion']),
 module('model-runtime','模型管理','分别管理嵌入、重排与生成模型','feature',['inference','deep','ai'],note='已有模型调用代码。嵌入、重排与生成服务须分别检查配置和运行状态。'),
 module('storage-ops','存储与分发','原件、副本与访问权限','feature',['storage','distribution','asset'],routes=['/admin/storage','/admin/distribution']),
 module('web','Web 界面','React / Next 约定 / Vinext','service',['dependencies','nav','reader']),
 module('django','业务服务','Django REST API','service',['api','permissions']),
 module('postgres','业务数据','PostgreSQL','store',['database','models','research-model','compose']),
 module('redis','任务队列','Redis / Celery','service',['queue','compose','discovery-session']),
 module('meili','检索索引','Meilisearch 索引','store',['indexing','projection','compose']),
 module('models-runtime','检索模型','嵌入与重排','service',['inference','deep']),
 module('ocr-runtime','文档解析','RapidOCR / ONNX Runtime','service',['ocr-service','ocr','ingestion']),
 module('files','文件存储','NAS 中的原件与处理后副本','store',['storage','distribution','outline-export']),
 module('design-tokens','基础规范','纸白、炭黑、砂金与字体','design',['tokens','type','brand']),
 module('design-controls','基础控件','Button / Input / Dialog','design',['controls','dialog']),
 module('design-shells','共用框架','SiteHeader / AdminShell / ReaderShell','design',['nav','admin','reader-shell']),
 module('design-pages','页面结构','内容浏览、研究工作台与后台','design',['home','evidence-page','research-ui','admin']),
 module('oauth','第三方登录','Google 后续接入','feature',['oauth','account-launch'],status='planned',note='首发仅用书库账号。项目记录确认 Apple 不接入，Google 后续再接。'),
]

# Relations are explicitly classified: a module belongs to a product, navigation
# carries a locator, an API call invokes a service; they are not all "data flow".
EDGES = []
def edge(a,b,kind,label,refs):
 EDGES.append(dict(source=a,target=b,type=kind,label=label,sources=refs))
for n in NODES:
 for child in n['children']: edge(n['id'],child,'contains','功能归属',n['sources'])
edge('viewpoints','evidence','data','查询 → 原文结果',['opinions','discovery-client','discovery-api'])
edge('evidence','pdf','navigation','原文位置 → 阅读器',['evidence-ui','reader'])
edge('pdf','citations','call','版本与选文 → 引用预览',['reader-shell','citation'])
edge('intake','processing','call','入库任务 → 文档处理',['ingestion','pipeline'])
edge('processing','meili','data','处理结果 → 非公开索引准备',['pipeline-index','indexing'])
edge('web','django','call','API 请求',['discovery-client','api'])
edge('django','postgres','data','业务记录',['discovery-session','database'])
edge('django','redis','call','事务提交后投递',['discovery-session','queue'])
edge('redis','meili','call','执行检索 / 更新索引',['discovery-task','indexing','projection'])
edge('redis','models-runtime','call','嵌入 / 重排',['discovery-task','inference','deep'])
edge('redis','ocr-runtime','call','文档处理任务',['ingestion','ocr'])
edge('django','files','data','按权限读取文件',['distribution','storage'])
edge('design-tokens','design-controls','uses','样式规范',['tokens','controls'])
edge('design-controls','design-shells','uses','复用控件',['nav','admin','reader-shell'])
edge('design-shells','design-pages','uses','组合页面',['home','evidence-page','research-ui'])

def main():
 refs={}
 for id,(filename,anchor) in SOURCES.items():
  raw=(ROOT/filename).read_bytes(); lines=raw.decode('utf-8-sig').splitlines()
  line=next((i+1 for i,s in enumerate(lines) if anchor in s),None)
  if not line: raise ValueError(f'Anchor drift: {id}: {filename}: {anchor}')
  refs[id]=dict(id=id,file=filename,line=line,anchor=anchor,sha256=hashlib.sha256(raw).hexdigest(),kind='record' if filename.endswith('.md') else 'source')
 routes=[]
 for file in sorted((ROOT/'web/app').rglob('page.tsx')):
  route='/'+file.parent.relative_to(ROOT/'web/app').as_posix()
  route=route.replace('/.','/')
  source=file.read_text('utf-8-sig')
  group='管理端' if route.startswith('/admin') else '私人空间' if route.startswith('/account') else '开发或暂停' if 'preview' in route or route=='/policy' else '网站页面'
  imports=re.findall(r'from\s+[\'"]([^\'"]+)[\'"]',source)
  routes.append(dict(route=route,file=file.relative_to(ROOT).as_posix(),group=group,imports=imports))
 for n in NODES:
  for key in n['sources']: assert key in refs,(n['id'],key)
  for child in n['children']: assert any(x['id']==child for x in NODES)
  n['parent']=next((p['id'] for p in NODES if n['id'] in p['children']),None)
  n['implementation']='源码已存在' if n['status']=='pending' else '规划未实施' if n['status']=='planned' else '存在待接入或待配置项'
 for e in EDGES:
  assert e['source'] in {n['id'] for n in NODES} and e['target'] in {n['id'] for n in NODES}
  assert e['type'] in {'contains','data','navigation','call','uses'}
  assert all(ref in refs for ref in e['sources'])
 data=dict(schemaVersion=1,auditedAt=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),commit=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip(),
           scope='当前工作区，包含继承的未提交修改。源码检查不等于业务验收。',
           statuses={'verified':'限定范围已验证','pending':'已实现 · 待验收','partial':'待接入或待配置','planned':'规划 · 未实施'},
           sources=refs,nodes=NODES,edges=EDGES,routes=routes,
           exclusions=['政策研究已暂停，本展示不包含该模块。','RAG / LLMWiki 的后续方案未定，未列为已交付功能。','文件清单包含开发预览和兼容路由，页面地图仅展示主要入口。'],
           runtime=[])
 runtime=HERE/'runtime-evidence.json'
 if runtime.exists(): data['runtime']=json.loads(runtime.read_text('utf-8'))
 journeys=json.loads((HERE/'journeys.json').read_text('utf-8'))
 for journey in journeys:
  for step in journey['steps']:
   assert step['node'] in {n['id'] for n in NODES}, step['id']
   assert all(source in refs for source in step['sources']), step['id']
   assert step['duration'] >= 1000 and step['input'] and step['output'] and step['boundary']
 data['journeys']=journeys
 facts=json.loads((HERE/'module-facts.json').read_text('utf-8'))
 for node_id,fact in facts.items():
  assert node_id in {n['id'] for n in NODES}
  assert all(source in refs for source in fact['sources'])
 data['moduleFacts']=facts
 (HERE/'architecture.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
 with (HERE/'evidence-index.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f); w.writerow(['node_id','module','implementation_status','source_kind','file','line','sha256'])
  for n in NODES:
   for id in n['sources']:
    r=refs[id]; w.writerow([n['id'],n['title'],n['status'],r['kind'],r['file'],r['line'],r['sha256']])
  for journey in journeys:
   for step in journey['steps']:
    for id in step['sources']:
     r=refs[id]; w.writerow([f"{journey['id']}/{step['id']}",step['label'],'source-reviewed',r['kind'],r['file'],r['line'],r['sha256']])
  for node_id,fact in facts.items():
   for id in fact['sources']:
    r=refs[id]; w.writerow([node_id,'职责与数据记录','source-reviewed',r['kind'],r['file'],r['line'],r['sha256']])
 print(f'{len(NODES)} nodes, {len(EDGES)} typed relations, {len(refs)} references, {len(routes)} route files. Source anchors verified.')

if __name__=='__main__': main()
