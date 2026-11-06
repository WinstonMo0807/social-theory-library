// Narrative and layout are separate from the audited architecture graph.
export const scenes = [
 {id:'overview',name:'全站总览',english:'The connected library',title:'以原文为中心，连接整个书库。',intro:'六个协作领域，一套共同的内容与证据基础。',stages:['整体结构','发现与理解','阅读与研究','管理与支撑'],notes:['从中央的书库出发，沿两侧展开产品职责。','发现入口通向原文，知识页面提供学者、理论与主题的组织。','阅读与引用延续到本人研究空间，权限随操作分别校验。','后台维护馆藏与正式内容，系统能力支撑前后端运行。']},
 {id:'sitemap',name:'页面地图',english:'Places & permissions',title:'页面有层级，访问有边界。',intro:'从真实路由提取入口，按实际使用与授权方式组织。',stages:['浏览入口','登录后使用','管理工作区'],notes:['首页与欢迎页独立；公开页面呈现已发布的书目与知识内容。','探索、PDF 与下载须登录；私人空间还须核验记录归属。','管理端与读者端共用业务服务，管理操作按能力授权。']},
 {id:'workflow',name:'研究工作流',english:'From question to source',title:'一个问题，如何抵达一段原文？',intro:'沿真实调用链，看查询、证据、阅读与引用如何接续。',stages:['提出问题','返回证据','定位原文','生成引用'],notes:['观点页把查询和范围传给原文证据页，创建检索会话。','后台异步整理结果；返回前重新核验来源与访问资格。','结果携带 Reader 位置，进入对应版本、页码与证据。','共享引用接口组合书目与选文；本图不模拟真实搜索或生成内容。']},
 {id:'technology',name:'技术与数据',english:'One system, distinct duties',title:'同一套服务，各自保存该保存的事实。',intro:'以一次原文检索为线索，展开界面、业务、任务与数据。',stages:['界面与服务','持久化与投递','异步检索','文档与文件'],notes:['React 与 Vinext 承担界面，Django API 处理业务与权限。','会话先保存；事务提交后再向 Celery 队列投递任务。','工作任务调用派生索引及模型适配；结果仍须核验原文资格。','OCR 是文档处理支路，原件与派生文件由既有存储及分发服务管理。']},
 {id:'design',name:'设计系统',english:'A shared visual language',title:'同一种设计语言，不同的研究场景。',intro:'直接复用已确认的品牌、字体与组件，以组合延续一致性。',stages:['品牌与基础','共用组件','页面组合'],notes:['品牌沿用 2026-10-27 标识；宋体标题、黑体操作与纸白基底。','基础控件、对话框与公共页头保持同一组交互约定。','内容浏览、研究工作台与管理工作台在共同基础上各负其责。']},
 {id:'status',name:'实现与证据',english:'What the evidence supports',title:'完成到哪里，证据就说到哪里。',intro:'代码存在、运行观察与正式验收，使用不同的证据口径。',stages:['本次观察','已实现待验收','明确未闭环'],notes:['本次只读观察公开页面与匿名登录门禁；不据此宣称业务全链通过。','自动目录已有两份样本的验证记录；更多书种与项目完整验收继续保留原 B 状态。','外部模型配置与第三方登录分别标记；暂停与未定范围不补造。']},
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
 {title:'发现与阅读',access:'登录后使用',reveal:1,items:[['馆藏与观点检索','/explore/original · /explore/opinions','discovery'],['原文证据','/explore/evidence','evidence'],['PDF 与并读','/reader/[assetId]','reader'],['引用与下载','Reader 操作与受控文件接口','citations']]},
 {title:'私人研究',access:'本人记录',reveal:1,items:[['连续研究','/account/research','sessions'],['笔记与确认','/account/notes · /account/confirmed-notes','notes'],['计划与书单','/account/plans · /account/collections','plans'],['引文体检与隐私','/account/citation-audits · /account/settings/privacy','audits']]},
 {title:'管理工作区',access:'管理能力授权',reveal:2,items:[['收件与编目','/admin/uploads · /admin/intake/[itemId]','intake'],['文档与索引','/admin/processing','processing'],['发布与内容','/admin/publication · /admin/content','publish'],['系统与权限','/admin/system-health · /admin/users','operations']]},
];
export const workflowSteps=[
 {id:'viewpoints',title:'提出问题',action:'输入问题，限定范围',output:'查询 + 筛选条件',source:'discovery-client'},
 {id:'evidence',title:'取得证据',action:'查看节选，展开上下文',output:'原文 + 来源 + 位置',source:'projection'},
 {id:'pdf',title:'回到原文',action:'打开对应版本与页码',output:'选文 + 版本 + 页码',source:'reader'},
 {id:'citations',title:'形成引用',action:'选择格式，复制或导出',output:'可追溯的引用文本',source:'citation'},
];
