import { publicDemo } from './mode';
import tour from './overview-tour.json';
export const overviewModules=tour.modules;
export const overviewTour=[
 {phase:'overview',node:null,label:'全站总览',note:'六个功能领域围绕馆藏与原文协作。',duration:tour.opening},
 ...tour.modules.flatMap(m=>[
  {phase:'click',node:m.id,label:`进入${m.label}`,note:m.note,duration:tour.click},
  {phase:'detail',node:m.id,label:m.label,note:m.note,duration:tour.detail},
  {phase:'return',node:m.id,label:'返回总览',note:`返回全站总览，接续下一部分。`,duration:tour.return}
 ]),
 {phase:'overview',node:null,label:'全站总览',note:'六个功能领域共用业务与权限服务。',duration:tour.closing},
];
// Narrative and layout are separate from the audited architecture graph.
export const scenes = [
 {id:'overview',name:'全站总览',english:'Library architecture',title:'书库的功能与协作关系',intro:'6 个功能领域围绕馆藏与原文协作，共用业务和权限服务。',stages:overviewTour.map(p=>p.label),notes:overviewTour.map(p=>p.note)},
 {id:'sitemap',name:'网站页面',english:'Website pages',title:'网站页面与访问权限',intro:'4 组页面分别服务浏览、阅读、私人研究与管理。',stages:['全部页面','浏览书库','发现与阅读','私人研究','管理工作区','页面总览'],notes:['页面按使用任务分组，分别检查访问权限。','公开页面呈现已发布的书目与知识内容。','检索、PDF 正文与下载须登录后使用。','研究会话、笔记与计划仅供所属读者访问。','管理操作按职责分别检查权限。','前台、私人研究与管理端共用业务和权限服务。']},
 {id:'workflow',name:'使用演示',english:'Search, read & cite',title:'从检索问题到原文引用',intro:'查询创建检索会话。结果携带原文位置，供阅读器和引用接口使用。',stages:['提出问题','返回证据','定位原文','生成引用'],notes:['观点检索页将查询和筛选条件传给原文证据页，再创建检索会话。','后台异步整理结果。返回前重新检查来源状态与访问权限。','阅读器根据结果中的版本、页码与原文位置打开原文。','共享引用接口组合书目与选文。演示只说明数据结构。']},
 {id:'technology',name:'底层架构',english:'Services & data',title:'业务服务、异步任务与存储',intro:'业务记录保存在数据库中。检索索引与派生文件分别维护。',stages:['界面与服务','保存与投递','异步检索','文档与文件'],notes:['React 与 Vinext 渲染界面。Django API 处理业务与权限。','数据库先保存会话。事务提交后再向 Celery 投递任务。','后台任务调用检索索引和模型服务。返回结果前检查来源是否仍可访问。','文档处理任务调用文字识别（OCR）。文件服务按权限提供原件或处理后的副本。']},
 {id:'design',name:'品牌标识',english:'Brand identity',title:'品牌标识与界面应用',intro:'页面沿用已确认的品牌、字体、颜色和控件。',stages:['品牌与基础','共用组件','页面组合'],notes:['品牌沿用 2026-10-27 标识。标题采用宋体，正文与操作采用黑体。','基础控件、对话框与公共页头复用现有组件。','浏览页、研究工作台与管理工作台按各自任务组合组件。']},
] as const;
export type Placement={id:string,x:number,y:number,w?:number,h?:number,reveal?:number};
export const overview:Placement[]=[
 {id:'stl',x:442,y:160,w:314,h:144,reveal:0},
 {id:'discovery',x:10,y:10,reveal:1},{id:'reader',x:10,y:180,reveal:2},{id:'research',x:10,y:350,reveal:2},
 {id:'knowledge',x:920,y:10,reveal:1},{id:'publishing',x:920,y:180,reveal:3},{id:'operations',x:920,y:350,reveal:3},
];
export const technology:Placement[]=[
 {id:'web',x:0,y:175,w:216,reveal:0},{id:'django',x:295,y:175,w:224,reveal:0},
 {id:'postgres',x:602,y:5,w:230,reveal:1},{id:'redis',x:602,y:175,w:230,reveal:1},{id:'files',x:602,y:345,w:230,reveal:3},
 {id:'meili',x:972,y:5,w:226,reveal:2},{id:'models-runtime',x:972,y:175,w:226,reveal:2},{id:'ocr-runtime',x:972,y:345,w:226,reveal:3},
];
export const sitemapGroups=[
 {title:'浏览书库',access:'公开页面',reveal:0,items:[['首页与欢迎','/ · /welcome','curation'],['学者、理论与主题','/scholars · /theories · /topics','knowledge'],['特别策划与作品','/recommendations · /works/[slug]','curation'],['关于与帮助','/about · /help','stl']]},
 {title:'发现与阅读',access:'登录后使用',reveal:1,items:[['馆藏与观点检索','/explore/original · /explore/opinions','discovery'],['原文证据','/explore/evidence','evidence'],['PDF 阅读与并读','/reader/[assetId]','reader'],['引用与下载','阅读器操作与文件下载接口','citations']]},
 {title:'私人研究',access:'本人记录',reveal:1,items:[['连续研究','/account/research','sessions'],['笔记与确认','/account/notes · /account/confirmed-notes','notes'],['计划与书单','/account/plans · /account/collections','plans'],['引文体检与隐私','/account/citation-audits · /account/settings/privacy','audits']]},
 {title:'管理工作区',access:'按管理权限使用',reveal:2,items:[['收件与编目',(publicDemo?'':'/admin/uploads · /admin/intake/[itemId]'),'intake'],['文档与索引',(publicDemo?'':'/admin/processing'),'processing'],['发布与内容',(publicDemo?'':'/admin/publication · /admin/content'),'publish'],['系统与权限',(publicDemo?'':'/admin/system-health · /admin/users'),'operations']]},
];
export const workflowSteps=[
 {id:'viewpoints',title:'提出问题',action:'输入问题，限定范围',output:'查询 + 筛选条件',source:'discovery-client'},
 {id:'evidence',title:'取得证据',action:'查看节选，展开上下文',output:'原文 + 来源 + 位置',source:'projection'},
 {id:'pdf',title:'回到原文',action:'打开对应版本与页码',output:'选文 + 版本 + 页码',source:'reader'},
 {id:'citations',title:'形成引用',action:'选择格式，复制或导出',output:'含来源信息的引用文本',source:'citation'},
];
