#!/usr/bin/python3
"""Append immutable CI incident phases to the existing notification journal.

No execution, provider call, repair decision, webhook subscription or model.
Callers retain responsibility for verifying the evidence they report.
"""
import argparse,hashlib,json,re,sqlite3,sys,time
from notification_journal import sanitize,ci_context
DB='/var/lib/operations-alerts/alerts.sqlite'
REASONS={'down':{'ci_job_failed','ci_export_failed','ci_timeout','ci_executor_unavailable'},
 'attention':{'ci_repair_failed','ci_export_failed','ci_timeout','ci_executor_unavailable'},
 'recovered':{'ci_requalified'}}
def identity(key):
 if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,240}',key):raise ValueError('dedupe_key')
 return 'ci_'+hashlib.sha256(key.encode()).hexdigest()[:40]
def append(db,request,now=None):
 if not isinstance(request,dict) or set(request)!={'dedupe_key','phase','reason','test','context'}:raise ValueError('request_fields')
 incident=identity(request['dedupe_key']);phase=request['phase'];reason=request['reason']
 if phase not in REASONS or reason not in REASONS[phase] or type(request['test']) is not bool:raise ValueError('phase_reason')
 context=ci_context(request['context'])
 reserved=request['dedupe_key'].startswith('controller-attention')
 if reserved:
  match=re.fullmatch(r'controller-attention:([0-9a-f]{64})',request['dedupe_key'])
  if (not match or phase!='attention' or reason!='ci_executor_unavailable'
      or context['provider'] not in ('github','gitlab')
      or context['receipt_path']!='/var/lib/fdisbull-ci/control/recovery/production/incidents/'+match.group(1)+'/controller-attention-state.json'):
   raise ValueError('controller_attention_binding')
 now=int(time.time()) if now is None else now
 event_id='conn_'+incident+'_'+phase
 db.execute('BEGIN IMMEDIATE')
 try:
  row=db.execute('SELECT body FROM events WHERE id=?',(event_id,)).fetchone()
  if row:
   old=json.loads(row[0])['data']
   if old['reason']!=reason or old['test']!=request['test'] or old['context']!=context:raise ValueError('conflicting_phase_replay')
   db.commit();return {'stage':'journaled','event_id':event_id,'incident_id':incident,'phase':phase,'already_present':True,'delivery_status':'not_observed_here','execution_performed':False}
  down=db.execute("SELECT body FROM events WHERE incident=? AND phase='down'",(incident,)).fetchone()
  recovered=db.execute("SELECT 1 FROM events WHERE incident=? AND phase='recovered'",(incident,)).fetchone()
  if recovered or (phase!='down' and not down and not reserved):raise ValueError('invalid_transition')
  if down:
   original=json.loads(down[0])['data']
   if original['test']!=request['test']:raise ValueError('mixed_test_incident')
   if any(original['context'][key]!=context[key] for key in ['provider','project']):raise ValueError('cross_project_incident')
  since=json.loads(down[0])['data']['outage_since_epoch'] if down else now
  data={'component':'ci_run','incident_id':incident,'phase':phase,'attention_required':phase=='attention',
    'status':'healthy' if phase=='recovered' else 'needs_operator' if phase=='attention' else 'failure','reason':reason,
    'observed_epoch':now,'outage_since_epoch':since,'duration_seconds':max(0,now-since),'restart_count':0,'test':request['test'],'context':context}
  event=sanitize({'eventId':event_id,'name':'connection.state_changed','data':data})
  db.execute('INSERT INTO events(id,incident,phase,body,created) VALUES(?,?,?,?,?)',(event_id,incident,phase,json.dumps(event,separators=(',',':')),now))
  # No Dot callback is manufactured or silently expanded; existing iMessage
  # journal replay performs delivery using the same durable event ID.
  db.commit()
  return {'stage':'journaled','event_id':event_id,'incident_id':incident,'phase':phase,'already_present':False,'delivery_status':'not_observed_here','execution_performed':False}
 except BaseException:db.rollback();raise

def read(db,key):
 incident=identity(key)
 return {'incident_id':incident,'stage':'journal_read','delivery_status':'not_observed_here','events':[sanitize(json.loads(r[0])) for r in db.execute('SELECT body FROM events WHERE incident=? ORDER BY seq',(incident,))]}
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);sub.add_parser('append');r=sub.add_parser('read');r.add_argument('--dedupe-key',required=True);args=p.parse_args()
 mode='rw' if args.action=='append' else 'ro';db=sqlite3.connect('file:'+DB+'?mode='+mode,uri=True,timeout=5)
 try:
  if args.action=='append':
   raw=sys.stdin.buffer.read(8193)
   if len(raw)>8192:raise ValueError('request_size')
   result=append(db,json.loads(raw))
  else:result=read(db,args.dedupe_key)
  print(json.dumps(result,separators=(',',':')))
 finally:db.close()
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):raise SystemExit('CI incident request rejected; private diagnostics withheld') from None
