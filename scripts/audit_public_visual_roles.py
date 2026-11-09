"""Evaluate existing capability rules with synthetic in-memory identities only."""
from pathlib import Path
from types import SimpleNamespace
import csv
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings',DATABASE_URL='sqlite:///:memory:',
    DJANGO_DEBUG='true',LIBRARY_OWNER_EMAIL='owner-v305@example.test',
    CELERY_BROKER_URL='memory://',CELERY_RESULT_BACKEND='cache+memory://')
sys.path.insert(0,str(ROOT/'api'))
import django
django.setup()
from django.db import connection
from common.capabilities import Capability,capability_snapshot

def no_database(execute,sql,params,many,context):
    raise RuntimeError('Role inventory must not access a database')

identities={}
for role in ('anonymous','inactive','reader','editor','reviewer','admin','owner'):
    identities[role]=SimpleNamespace(is_authenticated=role!='anonymous',is_active=role!='inactive',
        role='admin' if role=='owner' else role,email=f'{role}-v305@example.test',is_superuser=False)
with connection.execute_wrapper(no_database):
    snapshots={role:capability_snapshot(user) for role,user in identities.items()}
    rows=[{'capability':capability,**{role:capability in snapshot.capabilities for role,snapshot in snapshots.items()}}
        for capability in sorted(value for name,value in vars(Capability).items() if name.isupper())]
destination=ROOT/'docs/stl4/public-visual-20261110/ROLE_CAPABILITIES.csv'
with destination.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['capability',*identities]);writer.writeheader();writer.writerows(rows)
assert snapshots['reviewer']==snapshots['editor']
assert not snapshots['inactive'].capabilities
print(f'{len(rows)} capabilities; seven identity states; legacy reviewer resolves to editor; no DB')
