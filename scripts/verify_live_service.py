"""Exercise the real local service with curl and preserve truthful Unit 7 evidence."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:5057'
OUT=ROOT/'evidence/05-live-service.json'
if OUT.exists():
    raise SystemExit('Preserve existing evidence; refusing to overwrite the live run.')

def call(method, route, payload=None):
    command=['curl','--silent','--show-error','--max-time','120','-X',method,BASE+route]
    if payload is not None:
        command+=['-H','Content-Type: application/json','--data-binary',json.dumps(payload,ensure_ascii=False)]
    command+=['--write-out','\n%{http_code}']
    process=subprocess.run(command,check=True,capture_output=True,text=True)
    body,status=process.stdout.rsplit('\n',1)
    return {'method':method,'route':route,'request':payload,'http_status':int(status),
            'response':json.loads(body),'curl_command':command}

samples=json.loads((ROOT/'examples/calibration.json').read_text())['samples']
report={'scope':'Unit 7 live development check; real model, no mocks; not Unit 8 accuracy evaluation',
        'started_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'files_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in
            ['criteria.md','app.py','config.py','scoring.py','stylometry.py','detector.py','audit.py','examples/calibration.json']},
        'packages':{name:importlib.metadata.version(name)for name in ['flask','torch','transformers']},
        'health_before':call('GET','/health'), 'calibration':[]}
for sample in samples:
    result=call('POST','/submit',{'text':sample['text'],'creator_id':'calibration-'+sample['id']})
    assert result['http_status']==200, result
    result['sample_id']=sample['id']
    report['calibration'].append(result)
    print(sample['id'],result['response']['guess'],result['response']['confidence'],flush=True)
assert {c['response']['guess']for c in report['calibration']}=={'ai','human','unsure'}
report['health_after']=call('GET','/health')
assert report['health_after']['response']['detector_loaded'] is True
sample=next(s for s in samples if s['id']=='ai_repetitive')
report['sample_submit']=call('POST','/submit',{'text':sample['text'],'creator_id':'sample-run'})
content_id=report['sample_submit']['response']['content_id']
reasoning='For this demonstration, please review the process notes for this sample. This is a test appeal, not a claim of human authorship.'
report['sample_appeal']=call('POST','/appeal',{'content_id':content_id,'reasoning':reasoning})
report['sample_log']=call('GET','/log?limit=2')
report['content']=call('GET','/content/'+content_id)
assert report['sample_appeal']['http_status']==200
assert report['content']['response']['status']=='under_review'
entries=report['sample_log']['response']['entries']
assert len(entries)==2 and all(e['content_id']==content_id for e in entries)
assert entries[0]['status']=='decided' and entries[1]['status']=='under_review'
assert entries[1]['reasoning']==reasoning
report['finished_utc']=datetime.now(timezone.utc).isoformat()
report['status']='passed'
OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print('Live endpoint and appeal checks passed.',flush=True)
