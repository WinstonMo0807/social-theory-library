"""Check maintained architecture Markdown without network or application imports.

Checks local links, heading/line anchors, fenced blocks, and inventory coverage.
Mermaid syntax and actual SVG layout require a separate renderer.
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/architecture'
FILES = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md']
FILES += [ROOT / 'docs' / name for name in ('ARCHITECTURE.md', 'CURRENT_STATE.md', 'DEPLOYMENT.md')]
FILES += sorted(DOCS.rglob('*.md'))
LINK = re.compile(r'!?\[(?:\\.|[^\]\\]|\[[^\]]*\])*\]\(([^)]+)\)')
HTML_LINK = re.compile(r'(?:src|href)=["\']([^"\']+)["\']')
FENCE = re.compile(r'^```([^\n]*)\n(.*?)^```\s*$', re.M | re.S)
errors = []
cache = {}
links = 0
diagrams = []


def content(path):
    if path not in cache:
        cache[path] = path.read_text(encoding='utf-8-sig')
    return cache[path]


def anchors(path):
    result, seen = set(), {}
    body = FENCE.sub('', content(path))
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', body, re.M):
        heading = re.sub(r'<[^>]+>', '', heading).replace('`', '').replace('*', '')
        slug = ''.join(c for c in heading.lower() if c in '_- ' or not unicodedata.category(c).startswith(('P', 'S'))).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug + (f'-{count}' if count else ''))
    result.update(re.findall(r'(?:id|name)=["\']([^"\']+)["\']', body))
    return result


for file in FILES:
    body = content(file)
    relative = file.relative_to(ROOT).as_posix()
    if len(re.findall(r'^```', body, re.M)) % 2:
        errors.append(f'{relative}: unpaired code fence')
    for block in FENCE.finditer(body):
        if block.group(1).strip() == 'mermaid':
            text = block.group(2).strip()
            diagrams.append({'file': relative, 'type': text.splitlines()[0], 'line': body[:block.start()].count('\n') + 1})
    prose = FENCE.sub('', body)
    for raw in LINK.findall(prose) + HTML_LINK.findall(prose):
        raw = raw.strip().strip('<>')
        if urlsplit(raw).scheme or raw.startswith('//'):
            continue
        links += 1
        pathpart, _, fragment = raw.partition('#')
        target = (file.parent / unquote(pathpart.split('?')[0])).resolve() if pathpart else file
        if not target.exists():
            errors.append(f'{relative}: missing local target {raw}')
        elif fragment and target.is_file():
            fragment = unquote(fragment)
            line = re.fullmatch(r'L(\d+)(?:-L(\d+))?', fragment)
            if line and max(int(x) for x in line.groups() if x) > len(content(target).splitlines()):
                errors.append(f'{relative}: source line out of range {raw}')
            elif not line and target.suffix == '.md' and fragment not in anchors(target):
                errors.append(f'{relative}: missing heading {raw}')

required = {'flowchart', 'erDiagram', 'sequenceDiagram', 'stateDiagram-v2'}
present = {d['type'].split()[0] for d in diagrams}
for heading in ('C4 · System Context', 'C4 · Container'):
    if heading not in content(DOCS / '01_SYSTEM_ARCHITECTURE.md'):
        errors.append(f'Missing C4 view: {heading}')
if required - present:
    errors.append(f'Missing diagram types: {sorted(required - present)}')
with (DOCS / 'inventory/admin-pages.csv').open(encoding='utf-8-sig', newline='') as stream:
    admin_count = sum(1 for _ in csv.DictReader(stream))
source_admin_count = sum(1 for p in (ROOT / 'web/app/admin').rglob('*') if p.name in ('page.tsx', 'route.ts'))
if admin_count != source_admin_count:
    errors.append(f'Admin inventory stale: {admin_count} rows / {source_admin_count} source entries')

print(json.dumps({'markdown_files': len(FILES), 'local_links': links, 'mermaid_blocks': len(diagrams), 'diagram_types': sorted(present), 'admin_entries': admin_count, 'errors': errors}, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
