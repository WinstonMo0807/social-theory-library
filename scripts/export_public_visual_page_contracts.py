"""Persist per-consumer field/control/API references, not acceptance claims."""
from pathlib import Path
from collections import defaultdict
import csv
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/stl4/public-visual-20261110'
RAW=ROOT/'output/public-visual-20261110/audit'
web=json.loads((RAW/'WEB_SOURCE_MAP.json').read_text(encoding='utf-8'))
def read(name):
    with (OUT/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]));writer.writeheader();writer.writerows(rows)
coverage=read('COVERAGE.csv')
by_route={row['route']:row for row in coverage}
links=defaultdict(list)
for row in read('PAGE_API_LINKS.csv'):links[row['page']].append(row)
apis={(row['method'],row['path']):row for row in read('API_CONTRACTS.csv')}
controls={}
for page in web['routes']:
    for row in page['controls']:
        key=(row['file'],row['line'],row['tag'],json.dumps(row['attributes'],ensure_ascii=False,sort_keys=True))
        item=controls.setdefault(key,{'source':row['file']+':'+str(row['line']),'tag':row['tag'],'attributes':key[3],'consumers':set()})
        item['consumers'].add(by_route[page['route']]['id'])
control_rows=[]
control_ids=defaultdict(list)
for i,item in enumerate(controls.values(),1):
    identifier=f'CTL{i:04d}'
    for consumer in item['consumers']:control_ids[consumer].append(identifier)
    control_rows.append({'id':identifier,**item,'consumers':';'.join(sorted(item['consumers'])),
        'evidence':'JSX source declaration; conditional visibility and runtime are separate evidence'})
write('UI_CONTROLS.csv',control_rows)
contracts=[]
for page in web['routes']:
    row=by_route[page['route']]
    schemas,keys,validations=set(),set(),set()
    for link in links[page['route']]:
        api=apis.get((link['method_candidate'],link['api_path']))
        if api:
            keys.add(api['method']+' '+api['public_path_template'])
            schemas.update(filter(None,api.get('resolved_schemas','').split(';')))
            validations.update(json.loads(api.get('validation_sources') or '{}'))
    contracts.append({'id':row['id'],'route':row['route'],'source':row['source'],
       'classification':row['classification'],'role':row['role'],
       'parameters':page['parameters'],'state_persistence_calls':page['stateSignals'],
       'controls':control_ids[row['id']], 'request_contracts':sorted(keys),
       'field_schemas':sorted(schemas),'validation_sources':sorted(validations),
       'behavior_notes':row['key_states_operations'],
       'evidence_scope':'Per-route source closure. Shared consumers individually mapped, not individually runtime-tested. Runtime evidence remains VERIFICATION.md/FIXTURE_ROLE_HTTP.json.'})
    row['control_contracts']=f'PAGE_BEHAVIOR.json#{row["id"]};UI_CONTROLS.csv'
    row['field_contracts']=';'.join(sorted(schemas))
    row['api_contracts']=';'.join(sorted(keys))
for row in coverage:
    row.setdefault('control_contracts','N/A: redirect, excluded reference, or global state; see source')
    row.setdefault('field_contracts','')
    row.setdefault('api_contracts','')
write('COVERAGE.csv',coverage)
(OUT/'PAGE_BEHAVIOR.json').write_text(json.dumps({'scope':'source inventory, not runtime acceptance','pages':contracts},ensure_ascii=False,indent=2),encoding='utf-8')
dynamic=[]
for row in web['requests']:
    if row.get('path'):continue
    expression=row.get('expression') or ''
    category='caller-bound path' if expression in {'path','url','endpoint','current'} else 'dynamic source/action URL or helper; inspect source'
    dynamic.append({'source':row['file']+':'+str(row['line']),'transport':row['transport'],'expression':expression,
        'category':category,'evidence':'Source expression retained; not an additional unnamed API. Match caller and API_CONTRACTS, preserve existing auth/owner checks.'})
write('DYNAMIC_REQUESTS.csv',dynamic)
print(json.dumps({'pages':len(contracts),'controls':len(control_rows),'dynamic_sites':len(dynamic),
    'active_pages_without_api_mapping':[row['route'] for row in contracts if row['classification'] in {'business_candidate','active_shared_template'} and not row['request_contracts']]}))
