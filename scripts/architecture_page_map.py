"""Render reviewable route and component tables from the static TS inventory.

The flow assignment is editorial metadata; imports/JSX/query reads are extracted.
It does not infer that every exported component in a module executes on a route.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/architecture'
data = json.loads((ROOT/'tmp/architecture-inventory/frontend.json').read_text(encoding='utf-8'))
modules = data['modules']

def link(file, line=None):
    return f'[{file.removeprefix("web/")}]({"../../"+file}{"#L"+str(line) if line else ""})'

def cell(value):
    return str(value).replace('|', '&#124;').replace('\n', ' ')

def flow(url):
    if url.endswith('/processing'): return 'M15'
    if any(key in url for key in ['/processing/', '/system-health', '/status', '/settings', '/semantic-index', '/query-lexicon']): return 'M16'
    if re.search(r'/(uploads|intake|review|cataloging)(/|$)', url): return 'M01'
    if '/library/assets/' in url: return 'M03'
    if '/library' in url: return 'M02'
    if '/preview/evidence' in url: return 'M10'
    if '/preview/works' in url or '/publication' in url or '/preview/knowledge' in url: return 'M04'
    if '/people' in url: return 'M05'
    if '/scholars' in url: return 'M06'
    if '/reading-paths' in url: return 'M09'
    if '/disciplines' in url or '/subdisciplines' in url: return 'M08'
    if '/topics' in url or '/taxonomy' in url: return 'M08'
    if '/theor' in url or url.endswith('/knowledge') or url.endswith('/candidates'): return 'M07'
    if '/recommendations' in url: return 'M11'
    if '/content' in url: return 'M12'
    if '/about' in url or '/welcome' in url: return 'M13'
    if '/media' in url: return 'M14'
    if '/storage' in url or '/backups' in url or '/distribution' in url or '/recycle' in url: return 'M17'
    if '/users' in url: return 'M18'
    if '/support' in url: return 'M19'
    if url.endswith('/visual-review'): return 'M20'
    return 'M00'

routes = [r for r in data['routes'] if r['url']=='/admin' or r['url'].startswith('/admin/')]
lines = ['# 管理端完整页面清单', '', '[架构目录](README.md) · [模块调用链](ADMIN_MODULE_CONTRACTS.md) · [组件使用表](ADMIN_COMPONENT_INVENTORY.md)', '',
         '由 `scripts/architecture_page_map.py` 根据 TypeScript AST 生成，共79个入口。page/handler与兼容跳转分别保留；同一组件复用不等于独立业务。M编号连接人工核对的业务契约。全部业务页面经过 `app/admin/layout.tsx → AdminShell`；route handler只执行重定向，不运行React布局。', '',
         '| URL | 入口与类型 | JSX入口/跳转 | 入口直接读取的 query | 业务链 |', '| --- | --- | --- | --- | --- |']
core = set()
for r in routes:
    rendered = sorted(set(x['name'] for x in r['renders']))
    imports = [x['target'] for x in r['imports'] if not x['typeOnly'] and '/components/' in x['target']]
    core.update(imports)
    behavior = ', '.join(rendered) or ('handler：legacyTheorySchoolAdminTarget → /admin/theory-nodes' if r['kind']=='handler' else '重定向 / 包装入口')
    if r['redirects']: behavior += '；' + '; '.join(r['redirects'])
    lines.append('| ' + ' | '.join([f'`{r["url"]}`', link(r['source'])+' · '+r['kind'], cell(behavior), ', '.join(r['queryKeys']) or '—（见组件参数）', f'[{flow(r["url"])}](ADMIN_MODULE_CONTRACTS.md#{flow(r["url"]).lower()})']) + ' |')
lines += ['', '## 兼容与次级入口', '',
'''- `KnowledgeLegacyRedirect` 依据 selected/object 类型和ID映射到人物、主题、学科、路径、作品或理论；保留筛选、分页、return_to和hash。`taxonomy`额外识别旧kind/type/theory。
- `/admin/theory-schools/[entityId]` 是307 handler，加入 `node_type=theory_tradition` 和 `legacy_id`，继续经 `/admin/theory-nodes` 到新页面。
- `/admin/review/[itemId]` 进入同一收件工作区的 bibliography；cataloging candidates 复用工作台并打开助手，不是第二套编目数据库。
- `/admin/publication?site=...` 转网站历史；`item` 转收件发布段。`/publication/knowledge/...` 是历史页；真正审核在 `/preview/knowledge/...?...review=1`。
- `/admin/recommendations` 默认项目工作台；`view=home`进入首页推荐位置，`view=legacy`进入旧推荐期列表。文章编辑器与preview route仍独立存在。
- `/admin/preview/**` 的 frame/review、作品的 edition、files/outline/OCR次级入口，以及视觉复核入口均在此表保留；侧栏不可见不等于不存在。
- `/admin/settings` 的旧栏目映射由 `LegacySettingsRoute` 决定；运行维护统一迁往 `/admin/processing/*`。具体键与组件中的 `searchParams.get` 位置见静态索引，不把重定向当成功保存。
''']
(OUT/'ADMIN_PAGE_INVENTORY.md').write_text('\n'.join(lines),encoding='utf-8')

# Include one layer of actual component imports, but record each module independently.
for file in list(core):
    for imp in modules.get(file,{}).get('imports',[]):
        if not imp['typeOnly'] and '/components/admin/' in imp['target']: core.add(imp['target'])
lines=['# 管理端组件与状态使用表','','[架构目录](README.md) · [页面清单](ADMIN_PAGE_INVENTORY.md) · [组件图](05_ADMIN_COMPONENT_MAP.md)','',
       '依据实际 import 与 JSX AST，不依据目录名称推测。每行描述一个源文件；含多个export的文件，其所有JSX/hook不能全数归到某一个页面。入口映射见页面表；精确使用行见 component-renders.csv，完整导入边见 component-imports.csv。','',
       '| 源文件 | 实际出现的业务子组件 | 状态 hooks | 读取的 query 键 |','| --- | --- | --- | --- |']
for file in sorted(core):
    row=modules.get(file,{})
    children=sorted({x['name'] for x in row.get('renders',[]) if not x['name'].startswith(('Loading','Link','Image'))})
    lines.append('| '+' | '.join([link(file), cell(', '.join(children)) or '无JSX / 转出模块', cell(', '.join(row.get('hooks',[]))) or '—',cell(', '.join(row.get('queryKeys',[]))) or '—'])+' |')
(OUT/'ADMIN_COMPONENT_INVENTORY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'{len(routes)} admin entries, {len(core)} component modules')
