"""Repeat authored checks and passive Player integration. Does not launch the game."""
import argparse,hashlib,importlib.metadata,json,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from campaign import *


def package_version(name):
    """Installed metadata is optional when verifying a source-only fixture."""
    try:return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:return None


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern='test_*.py')
    with (args.output/'authored-tests.txt').open('w') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    from fdisbull_player.player import Player,ProcessBackend
    command=[sys.executable,'-B',str(ROOT/'tools/campaign_endpoint.py'),'--observation',
             str(ROOT/'evidence/recorded-partial-campaign.json'),'--catalog',str(ROOT/'evidence/campaign-catalog.json'),
             '--observed-no-override']
    backend=ProcessBackend(command,timeout=10);player=Player(backend);commands=[]
    try:
        before=backend.observe()
        for text in ['look','examine mission selection','examine research','examine research graph',
                     'examine modifications','examine equipment','research mods','go world','save game']:
            answer=player.execute_result(text);commands.append({'command':text,'result':answer})
        after=backend.observe();assert before==after
        assert all(not r['result']['action_sent'] for r in commands)
        assert commands[1]['result']['status']=='read'
        assert '25.00%' in commands[2]['result']['outcome']
    finally:backend.close()
    receipt={'scope':'Authored model tests and actual Player over a fresh recorded-state backend; no native game execution',
             'core':package_version('fdisbull'),'player':package_version('fdisbull-player'),
             'version_scope':'Installed distribution metadata when available; null means no installed metadata, not a missing source import',
             'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
             'commands':len(commands),'state_unchanged':before==after,'actions_sent':0,'native_execution':False}
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (args.output/'player-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    print(json.dumps(receipt))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
