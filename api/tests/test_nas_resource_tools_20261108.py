import base64
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from unittest.mock import patch

import pytest


def script(name):
    path = Path(__file__).resolve().parents[2] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compaction_preserves_unique_business_arguments_and_unknown_messages():
    module = script('compact_celery_backlog')
    def message(task, identity, args=None):
        return json.dumps({'headers': {'task': task, 'id': identity},
            'body': base64.b64encode(json.dumps([args or [], {}, {}]).encode()).decode()}).encode()
    ocr = message('ingestion.tasks.process_ocr_job', 'same', ['job-a'])
    other = message('ingestion.tasks.process_ocr_job', 'same', ['job-b'])
    periodic = 'catalog.tasks.run_scheduled_health_probes'
    newest, oldest = message(periodic, 'new'), message(periodic, 'old')
    scoped = message(periodic, 'scoped', ['specific'])
    rows = [ocr, newest, other, ocr, oldest, scoped, b'not-json']
    kept, counts = module.plan(rows)
    assert kept == [ocr, newest, other, scoped, b'not-json']
    assert counts == {'same_delivery': 1, 'superseded_periodic': 1, 'unparsed_preserved': 1}


def test_service_manager_never_force_kills_active_work_and_validates_all_ownership():
    module = script('nas_on_demand')
    rows = [{'Name': '/' + name, 'Config': {'Labels': {'com.docker.compose.project': 'social-science-library'}},
             'State': {'Running': key == 'heavy'}} for key, name in module.CONTAINERS.items()]
    demand = dict.fromkeys(module.CONTAINERS, False)
    commands = []
    run = lambda args, **kwargs: commands.append(args)
    demand['heavy'] = True
    busy = {'heavy': 0}
    module.tick(busy, now=1000, inspect=rows, run=run, demand=demand)
    assert not commands and busy['heavy'] == 1000
    demand['heavy'] = False
    module.tick(busy, now=1091, inspect=rows, run=run, demand=demand)
    assert commands == [['docker', 'kill', '--signal', 'TERM', module.CONTAINERS['heavy']]]
    commands.clear()
    rows[-1]['Config']['Labels'] = {}
    with pytest.raises(ValueError):
        module.tick({}, now=1000, inspect=rows, run=run, demand=demand)
    assert not commands


def test_service_snapshot_includes_reserved_tasks_without_waking_models():
    module = script('nas_on_demand')
    reserved = json.dumps([{'headers': {'id': 'in-flight'}}, '', 'ingestion'])
    with patch.object(module, 'redis', return_value=['', '', '', '', 0, 0, 0, [reserved]]):
        assert module.snapshot() == {'inference': False, 'docx': False, 'searxng': False,
                                     'heavy': True, 'query': False, 'ocr': False}


def test_workstation_image_preserves_runtime_metadata_and_file_permissions(tmp_path):
    module = script('pack_runtime_image')
    rootfs, metadata = tmp_path / 'base.tar', tmp_path / 'image.json'
    with tarfile.open(rootfs, 'w') as archive:
        entry = tarfile.TarInfo('app/run.py'); entry.size = 3; entry.mode = 0o750; entry.uid = 1000
        archive.addfile(entry, io.BytesIO(b'old'))
    config = {'User': '1000', 'Cmd': ['python', 'run.py'], 'WorkingDir': '/app',
              'Healthcheck': {'Test': ['CMD', 'true']}}
    metadata.write_text(json.dumps({'Os': 'linux', 'Architecture': 'amd64', 'Config': config}))
    replacement = tmp_path / 'run.py'; replacement.write_bytes(b'new-code')
    output = tmp_path / 'runtime.tar'
    result = module.pack(rootfs, metadata, {'/app/run.py': str(replacement)}, 'test/runtime:check', output)
    assert result['layers'] == 1
    with tarfile.open(output) as archive:
        manifest = json.load(archive.extractfile('manifest.json'))[0]
        saved = json.load(archive.extractfile(manifest['Config']))
        assert saved['config'] == config
        with tarfile.open(fileobj=archive.extractfile(manifest['Layers'][0])) as layer:
            entry = layer.getmember('app/run.py')
            assert entry.mode == 0o750 and entry.uid == 1000
            assert layer.extractfile(entry).read() == b'new-code'
