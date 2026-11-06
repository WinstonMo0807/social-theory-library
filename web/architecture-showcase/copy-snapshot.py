"""Extract JSON display strings so STC checks Chinese copy, not JSON syntax."""
from pathlib import Path
import json, re

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'output/playwright/architecture-showcase-v3'
OUT.mkdir(parents=True, exist_ok=True)
lines = []
def visit(value):
    if isinstance(value, str) and re.search(r'[\u4e00-\u9fff]', value):
        lines.append(value)
    elif isinstance(value, list):
        for item in value:
            visit(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in {'sources', 'routes', 'runtime', 'route', 'file', 'anchor', 'scope', 'exclusions'}:
                visit(item)

for filename in ['journeys.json', 'module-facts.json']:
    visit(json.loads((HERE / filename).read_text('utf-8')))
data = json.loads((HERE / 'architecture.json').read_text('utf-8'))
visit(data['nodes'])
visit(data['statuses'])
visit([edge['label'] for edge in data['edges']])
visit([route['group'] for route in data['routes']])
visit(data['scope'])
visit(data['exclusions'])
(OUT / 'display-copy.txt').write_text('\n'.join(dict.fromkeys(lines)) + '\n', 'utf-8')
print('Extracted display copy from architecture and journey data.')
