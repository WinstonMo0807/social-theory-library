"""Extract Django declarations without importing Django or accessing a database.

Regenerate alongside architecture-inventory.mjs. Calls and references are static
evidence; review inherited/dynamic dispatch and public visibility separately.
"""
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/architecture/inventory'
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = ROOT / 'tmp/architecture-inventory'
SCRATCH.mkdir(parents=True, exist_ok=True)
apps = ['accounts', 'catalog', 'common', 'config', 'distribution', 'ingestion', 'reading']
files = [p for app in apps for p in (ROOT/'api'/app).rglob('*.py') if not {'migrations', 'tests', '__pycache__'} & set(p.parts)]
modules = {}
models = []
definitions = {}
for path in sorted(files):
    code = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(code)
    name = path.relative_to(ROOT/'api').with_suffix('').as_posix().replace('/', '.')
    if name.endswith('.__init__'):
        name = name[:-9]
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = name.split('.')[:-node.level] if node.level else []
            module = '.'.join([*base, *([node.module] if node.module else [])])
            for alias in node.names:
                imports[alias.asname or alias.name] = module + '.' + alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
    row = {'file': path.relative_to(ROOT).as_posix(), 'imports': imports, 'definitions': {}}
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        calls = sorted({ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)})
        definition = {'line': node.lineno, 'end_line': node.end_lineno, 'kind': type(node).__name__, 'calls': calls,
                      'import_references': {k: v for k, v in imports.items() if k in used},
                      'bases': [ast.unparse(x) for x in node.bases] if isinstance(node, ast.ClassDef) else [],
                      'methods': [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] if isinstance(node, ast.ClassDef) else []}
        row['definitions'][node.name] = definition
        definitions[name+'.'+node.name] = {'file': row['file'], **definition}
        if not path.name.endswith('models.py') or not isinstance(node, ast.ClassDef):
            continue
        bases = definition['bases']
        if any('TextChoices' in b or 'QuerySet' in b or 'Manager' in b or 'Mixin' in node.name for b in bases):
            continue
        fields = []
        for field in node.body:
            if isinstance(field, ast.Assign) and isinstance(field.value, ast.Call) and ast.unparse(field.value.func).startswith('models.'):
                fields.append({'name': ast.unparse(field.targets[0]), 'type': ast.unparse(field.value.func).split('.')[-1],
                               'declaration': ast.unparse(field.value), 'line': field.lineno})
        if fields:
            table = name.split('.')[0] + '_' + node.name.lower()
            abstract = False
            for meta in node.body:
                if isinstance(meta, ast.ClassDef) and meta.name == 'Meta':
                    for setting in meta.body:
                        if isinstance(setting, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'db_table' for t in setting.targets):
                            table = ast.literal_eval(setting.value)
                        if isinstance(setting, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'abstract' for t in setting.targets):
                            abstract = ast.literal_eval(setting.value)
            models.append({'app': name.split('.')[0], 'model': node.name, 'file': row['file'], 'line': node.lineno,
                           'table': '' if abstract else table, 'abstract': abstract, 'bases': bases, 'fields': fields})
    modules[name] = row

def resolve(symbol, seen=None):
    seen = seen or set()
    if symbol in seen:
        return None
    seen.add(symbol)
    if symbol in definitions:
        return {'symbol': symbol, **definitions[symbol]}
    mod, _, short = symbol.rpartition('.')
    target = modules.get(mod, {}).get('imports', {}).get(short)
    return resolve(target, seen) if target else None

endpoints = []
prefixes = {'accounts': '/api/auth/', 'catalog': '/api/catalog/', 'ingestion': '/api/ingestion/', 'reading': '/api/reading/', 'distribution': '/api/distribution/', 'common': '/api/capability-worker/', 'config': '/'}
for name, module in modules.items():
    if not (name.endswith('.urls') or name.endswith('.content_placement_urls') or name.endswith('.remote_worker_urls')):
        continue
    tree = ast.parse((ROOT/module['file']).read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'path' or len(node.args) < 2:
            continue
        if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        target = ast.unparse(node.args[1])
        if target.startswith('include('):
            continue
        short = target.split('.as_view')[0]
        definition = resolve(module['imports'].get(short, name+'.'+short))
        endpoints.append({'url': prefixes.get(name.split('.')[0], '') + node.args[0].value,
                          'url_file': module['file'], 'url_line': node.lineno, 'view': target,
                          'definition': definition})

model_names = {m['model'] for m in models}
consumers = []
for symbol, d in definitions.items():
    refs = {k: v for k, v in d['import_references'].items() if v.split('.')[-1] in model_names and ('_models.' in v or '.models.' in v)}
    for ref in refs.values():
        consumers.append({'model': ref.split('.')[-1], 'consumer': symbol, 'file': d['file'], 'line': d['line']})

def write_csv(name, fields, rows):
    with (OUT/name).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

(SCRATCH/'backend.json').write_text(json.dumps({'method': 'Python AST, no imports or database access. Direct source references only; dynamic dispatch requires manual review.', 'endpoints': endpoints, 'models': models, 'modules': modules}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
write_csv('api-views-services.csv', ['url', 'url_file', 'url_line', 'view', 'view_file', 'view_line', 'methods', 'service_references', 'model_references'], [
    {'url': e['url'], 'url_file': e['url_file'], 'url_line': e['url_line'], 'view': e['view'],
     'view_file': (e['definition'] or {}).get('file', ''), 'view_line': (e['definition'] or {}).get('line', ''),
     'methods': '; '.join((e['definition'] or {}).get('methods', [])),
     'service_references': '; '.join(v for v in (e['definition'] or {}).get('import_references', {}).values() if '.services.' in v),
     'model_references': '; '.join(v for v in (e['definition'] or {}).get('import_references', {}).values() if '.models.' in v)} for e in endpoints])
write_csv('model-consumers.csv', ['model', 'consumer', 'file', 'line'], consumers)
write_csv('model-fields.csv', ['app', 'model', 'table', 'file', 'line', 'field', 'type', 'declaration'], [
    {'app': m['app'], 'model': m['model'], 'table': m['table'], 'file': m['file'], 'line': f['line'], 'field': f['name'], 'type': f['type'], 'declaration': f['declaration']} for m in models for f in m['fields']])
print(json.dumps({'modules': len(modules), 'definitions': len(definitions), 'endpoints': len(endpoints), 'resolved_views': sum(e['definition'] is not None for e in endpoints), 'models': len(models), 'model_consumers': len(consumers)}))
