#!/usr/bin/python3
"""Read-only, paginated, sanitized incident journal for the iMessage dispatcher."""
import argparse,json,re,sqlite3,time
from pathlib import Path,PurePosixPath
COMPONENTS={'tailnet_connection','vps_availability','n8n_service','n8n_mcp','n8n_monitor_workflow','n8n_assistant_key','ci_run'}
FIELDS=('component','incident_id','phase','attention_required','status','reason','observed_epoch','outage_since_epoch','duration_seconds','restart_count','test')
def ci_context(value):
 if not isinstance(value,dict) or set(value)!={'provider','project','run_id','job_id','commit_sha','job_name','receipt_path'}:raise ValueError('ci_context_fields')
 if value['provider'] not in ['local','gitlab','github']:raise ValueError('ci_provider')
 patterns={'project':r'[A-Za-z0-9_./-]{1,200}','run_id':r'[A-Za-z0-9_.:-]{1,100}','job_id':r'[A-Za-z0-9_.:-]{1,100}',
  'commit_sha':r'(?:[a-f0-9]{40}|[a-f0-9]{64})','job_name':r'[A-Za-z0-9_.:/ -]{1,100}',
  'receipt_path':r'/[A-Za-z0-9_./@+ -]{1,599}'}
 for key,pattern in patterns.items():
  if not isinstance(value[key],str) or not re.fullmatch(pattern,value[key]):raise ValueError('ci_'+key)
 receipt=value['receipt_path']
 if '..' in PurePosixPath(receipt).parts or PurePosixPath(receipt).as_posix()!=receipt:raise ValueError('ci_receipt_path')
 roots=('/var/lib/fdisbull-ci/results/','/var/lib/fdisbull-ci/control/recovery/')
 if not any(receipt.startswith(root) and len(receipt)>len(root) for root in roots):raise ValueError('ci_receipt_root')
 return dict(value)

def sanitize(event):
 d=event['data']
 if event['name']!='connection.state_changed' or d['component'] not in COMPONENTS:raise ValueError('component')
 if not re.fullmatch(r'[A-Za-z0-9_]{1,120}',d['incident_id']) or d['phase'] not in ['down','attention','recovered']:raise ValueError('identity')
 if event['eventId']!='conn_'+d['incident_id']+'_'+d['phase']:raise ValueError('event_id')
 if not re.fullmatch(r'[A-Za-z0-9_]{1,80}',d['reason']):raise ValueError('reason')
 if d['status'] not in ['healthy','failure','degraded','unknown','needs_operator']:raise ValueError('status')
 for key in ['observed_epoch','outage_since_epoch','duration_seconds','restart_count']:
  if type(d[key]) is not int or d[key]<0:raise ValueError('number')
 if type(d['test']) is not bool or type(d['attention_required']) is not bool:raise ValueError('boolean')
 from datetime import datetime,timezone
 data={k:d[k] for k in FIELDS}
 if d['component']=='ci_run':data['context']=ci_context(d.get('context'))
 return {'eventId':event['eventId'],'name':'connection.state_changed','timestamp':datetime.fromtimestamp(d['observed_epoch'],timezone.utc).isoformat(),'data':data,'cursor':None}
def page(db,after,limit):
 if type(after) is not int or after<0 or not 1<=limit<=100:raise ValueError('cursor')
 tail=db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
 if after>tail:raise ValueError('journal_replaced_or_cursor_invalid')
 rows=db.execute('SELECT seq,body FROM events WHERE seq>? ORDER BY seq LIMIT ?',(after,limit)).fetchall()
 return {'version':1,'source':'vps_incident_journal','checked_epoch':int(time.time()),'after':after,
  'next_cursor':rows[-1][0] if rows else after,'tail_sequence':tail,
  'events':[{'sequence':r[0],'event':sanitize(json.loads(r[1]))} for r in rows]}
def main():
 p=argparse.ArgumentParser();p.add_argument('--after',type=int,default=0);p.add_argument('--limit',type=int,default=100);args=p.parse_args()
 db=sqlite3.connect('file:/var/lib/operations-alerts/alerts.sqlite?mode=ro',uri=True,timeout=3)
 try:print(json.dumps(page(db,args.after,args.limit),separators=(',',':')))
 finally:db.close()
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):raise SystemExit('Notification journal read failed; no private diagnostics emitted') from None
