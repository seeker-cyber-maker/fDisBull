"""Serve a recorded campaign projection to the unchanged fDisBull Player."""
import argparse,json,sys
from pathlib import Path
from campaign import CampaignProvider


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--observation',type=Path,required=True)
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--observed-no-override',action='store_true')
    args=ap.parse_args()
    p=CampaignProvider(json.loads(args.observation.read_text()),json.loads(args.catalog.read_text()),
                       override=False if args.observed_no_override else None)
    while True:
        line=sys.stdin.readline(1024*1024+1)
        if not line:break
        if len(line)>1024*1024 or not line.endswith('\n'):
            raise ValueError('Oversized/incomplete protocol line')
        try:
            request=json.loads(line)
            if not isinstance(request,dict):raise ValueError('Expected request object')
            if request.get('op')=='observe':answer=p.observe()
            else:answer=p.act(request.get('action',{}))
        except (ValueError,TypeError,KeyError) as error:
            answer={'status':'rejected','complete':True,'effects':'none-confirmed','message':str(error)}
        print(json.dumps(answer,separators=(',',':')),flush=True)

if __name__=='__main__':main()
