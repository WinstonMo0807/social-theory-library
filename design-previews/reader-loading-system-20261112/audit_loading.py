from pathlib import Path
import re,json,csv,subprocess,collections
R=Path(__file__).resolve().parents[2]
O=R/'output/design/reader-loading-system-20261112';O.mkdir(parents=True,exist_ok=True)
paths=[p.replace('\\','/') for p in subprocess.check_output(['rg','--files','web/app','web/components','web/lib','-g','*.tsx','-g','*.ts'],cwd=R,text=True,encoding='utf8').splitlines() if '/generated/' not in p.replace('\\','/') and '.test.' not in p]
dirty={x.replace('\\','/') for x in subprocess.check_output(['git','diff','HEAD','--name-only','--','web'],cwd=R,text=True,encoding='utf8').splitlines()}
new={x.replace('\\','/') for x in subprocess.check_output(['git','ls-files','--others','--exclude-standard','web'],cwd=R,text=True,encoding='utf8').splitlines()}
rules=[('STL品牌组件',r'<LoadingState\b'),('Skeleton转品牌组件',r'<Skeleton\b'),('旋转指示',r'<Loader(?:Circle|2)?\b|className=[^\n]{0,80}(?:spin|spinner)'),('路由或边界',r'<Suspense\b|aria-busy=|className="route-loading"'),('实际进度',r'<progress\b|onProgress=|stage_progress'),('文字或条件状态',r'正在(?:加载|载入|读取|保存|检索|核对|生成|连接|上传|恢复|处理)|["\x27](?:加载中|读取中|保存中|处理中)|\{[^\n]{0,60}(?:\.loading|\bisLoading\b|sourceLoading|recordsLoading|listLoading)\s*[?&]')]
def category(path):
 if path.endswith('/loading.tsx') or path.endswith('route-transition.tsx'):return '路由与首次进入'
 if any(x in path for x in ['pdf-canvas','pdf-continuous','reader/parallel','outline-pdf-preview','work-file-preview','page-mapping-thumbnails']):return 'PDF文档与逐页渲染'
 if any(x in path for x in ['shared-citation','reader-shell','reader/use-reader','reader/reader-']):return '阅读侧栏与引用选段'
 if any(x in path for x in ['upload','ocr','processing','discovery-index','index-maintenance','semantic-index','publication-']):return '上传与后台长任务'
 if any(x in path for x in ['picker','aliases-dialog','existing-scholar','timeline-participants']):return '选择器与局部查找'
 if '/research/' in path or 'explore-ask' in path:return '私人研究与书单'
 if any(x in path for x in ['auth','activation','email','recovery-appeal','verify-email']):return '登录与账户核验'
 if 'media' in path or 'portrait' in path:return '媒体与图像'
 if '/admin/' in path or '/admin-' in path or 'workspace' in path or 'review-queue' in path:return '管理工作区与列表'
 if any(x in path for x in ['action-feedback','save-work','save-topic','asset-download','add-work']):return '单项操作与按钮'
 if path.startswith('web/lib/') or '/ui/' in path:return '共享组件或状态基础'
 return '公开内容与检索'
rows=[];files=[];duplicates=[];lazy=[]
for raw in paths:
 path=raw.replace('\\','/')
 if '/generated/' in path or '.test.' in path:continue
 text=(R/path).read_text('utf8');lines=text.splitlines();found=[]
 for n,line in enumerate(lines,1):
  if line.strip().startswith(('import ','//','*')):continue
  kinds=[name for name,pat in rules if re.search(pat,line)]
  if not kinds:continue
  first=min(m.start() for _,pat in rules if (m:=re.search(pat,line)))
  excerpt=line[max(0,first-70):first+360].strip()
  record={'文件':path,'行号':n,'场景':category(path),'现有呈现':' / '.join(kinds),'改动状态':'新增未跟踪' if path in new else '已跟踪有未提交改动' if path in dirty else '无未提交改动','核对状态':'静态检索定位，按场景验收；非逐页运行通过','源码片段':excerpt}
  rows.append(record);found.append(record)
  if '<LoadingState' in line and re.search(r'<Loader(?:Circle|2)?\b',line):duplicates.append({'file':path,'line':n})
 if not found and (path.endswith('/loading.tsx') or path.endswith('/route-transition.tsx')):
  record={'文件':path,'行号':1,'场景':category(path),'现有呈现':'路由或边界','改动状态':'新增未跟踪' if path in new else '已跟踪有未提交改动' if path in dirty else '无未提交改动','核对状态':'路由兜底显式纳入；非逐页运行通过','源码片段':'路由级等待边界，需按真实目标布局区分'}
  rows.append(record);found.append(record)
 if found:files.append({'file':path,'category':category(path),'sites':len(found),'dirty':path in dirty or path in new,'mechanisms':sorted({k for row in found for k in row['现有呈现'].split(' / ')})})
 if re.search(r'loading=[\"\x27]lazy[\"\x27]',text):lazy.append(path)
with (O/'loading-source-inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
report={'scope':'web/app, web/components, web/lib; source .ts/.tsx excluding generated and tests','scanned_files':len(paths),'candidate_lines':len(rows),'candidate_files':len(files),'dirty_candidate_files':sum(x['dirty'] for x in files),'categories':dict(collections.Counter(x['category'] for x in files)),'mechanisms':dict(collections.Counter(k for x in files for k in x['mechanisms'])),'duplicate_branded_spinner':duplicates,'native_lazy_files':len(lazy),'files':files}
css_paths=subprocess.check_output(['rg','--files','web/app','web/components','web/styles','-g','*.css'],cwd=R,text=True,encoding='utf8').splitlines()
css_rows=[]
for raw in css_paths:
 path=raw.replace('\\','/')
 for n,line in enumerate((R/path).read_text('utf8').splitlines(),1):
  if re.search(r'loading|skeleton|shimmer|spinner|(?:animation:|@keyframes)[^;\n]*(?:spin|pulse|progress)',line,re.I):
   css_rows.append({'文件':path,'行号':n,'改动状态':'有未提交改动' if path in dirty or path in new else '无未提交改动','核对状态':'静态样式命中；仍需确认选择器调用与场景','源码片段':line.strip()[:700]})
with (O/'loading-style-inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(css_rows[0]));w.writeheader();w.writerows(css_rows)
report['style_scanned_files']=len(css_paths)
report['style_candidate_files']=len({x['文件'] for x in css_rows})
report['style_candidate_lines']=len(css_rows)
(O/'loading-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({k:v for k,v in report.items() if k!='files'},ensure_ascii=False,indent=2))
