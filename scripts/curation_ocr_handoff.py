"""Read the curation OCR handoff, or explicitly resume its paused checkpoints.

The local service must be started by the curation chat first. This command never
uploads books, forces all-page OCR, or edits an OCR completion flag directly.
"""
import argparse
import subprocess

MANAGEMENT = r'''
import json
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.db.models import Q,Count
from django.contrib.auth import get_user_model
from django.utils import timezone
from catalog.models import SiteSetting
from ingestion.models import ProcessingJob,AuditEvent,UploadItem
from ingestion.services.processing import (processing_workload_paused,set_processing_workload_paused,
    PROCESSING_PAUSE_KEYS,resume_processing_job)
from ingestion.services.catalog_ocr import check_resume_source
from common.capabilities import Capability,has_capability
marker=Path('/data/backups/nas-resource-20261108/curation-handoff.json')
record=json.loads(marker.read_text())
scope=Q(pk__in=record['test_job_ids'])|Q(upload_item_id__in=record['test_upload_ids'])
jobs=ProcessingJob.objects.filter(scope,job_type='ocr')
print(json.dumps({'global_ocr_paused':processing_workload_paused('ocr'),
 'jobs':list(jobs.values('status').annotate(n=Count('id'))),
 'processed_pages':sum(int(job.stats.get('processed_pages')or 0) for job in jobs),
 'uploads':list(UploadItem.objects.filter(pk__in=record['test_upload_ids']).values('status').annotate(n=Count('id'))),
 'local_endpoint':settings.OCR_TEST_SERVICE_URL},ensure_ascii=False),flush=True)
if RESUME:
 import httpx
 assert settings.OCR_TEST_SERVICE_URL=='http://192.168.5.3:18091','Temporary endpoint changed'
 assert set(record['test_upload_ids']).issubset(settings.OCR_TEST_UPLOAD_IDS),'Temporary scope changed'
 # A real inference probe uses the same service and models; it sends no books.
 with httpx.Client(trust_env=False,timeout=45) as client:
  response=client.get(settings.OCR_TEST_SERVICE_URL+'/ready?deep=true')
  response.raise_for_status()
  health=response.json()
  assert health.get('runtime_verified') and health.get('model')=='PP-OCRv6-tiny'
 actor=get_user_model().objects.get(pk=record['actor_id'],is_active=True)
 assert has_capability(actor,Capability.RETRY_JOBS)
 with transaction.atomic():
  setting=SiteSetting.objects.select_for_update().get(key=PROCESSING_PAUSE_KEYS['ocr'])
  assert setting.value is True and setting.updated_at.isoformat()==record['paused_setting_version'], 'Pause control changed; inspect the current decision before resuming'
  assert not record['global_paused'],'OCR was already globally paused before this handoff'
  set_processing_workload_paused('ocr',False,actor=actor)
  AuditEvent.objects.create(actor=actor,action='processing.resume_curation_handoff',object_type='processing_workload',object_id='ocr',
   before={'paused_setting_version':record['paused_setting_version']},after={'global_paused':False})
 resumed=[];held=[]
 for job in jobs.filter(status='paused').exclude(pk__in=record['preexisting_paused_jobs']).select_related('asset__edition','edition'):
  try:
   check_resume_source(job)
   current=resume_processing_job(job,actor=actor)
   resumed.append(str(current.pk))
  except ValueError as exc:
   held.append({'job':str(job.pk),'reason':str(exc)})
 record['resumed_at']=timezone.now().isoformat();record['resumed_jobs']=resumed;record['held_jobs']=held
 marker.with_name('curation-handoff-resumed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
 marker.with_name('curation-handoff-resumed.json').chmod(0o600)
 print(json.dumps({'resumed':len(resumed),'held':held},ensure_ascii=False),flush=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'resume'], default='status', nargs='?')
    args = parser.parse_args()
    code = 'RESUME = ' + repr(args.action == 'resume') + '\n' + MANAGEMENT
    compile(code, '<curation-handoff>', 'exec')
    remote = 'import subprocess\np=subprocess.run(' + repr([
        'docker', 'exec', 'social-science-library-api-1', 'python', 'manage.py', 'shell', '-c', code
    ]) + ',timeout=180)\nraise SystemExit(p.returncode)'
    ssh = ['ssh','-T','-i','C:/Users/12297/.ssh/stl_nas_codex_rsa','-o','BatchMode=yes',
           '-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15',
           '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','Winston@192.168.5.6',
           'sudo','-n','python3','-']
    result = subprocess.run(ssh,input=remote.encode(),timeout=210)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
