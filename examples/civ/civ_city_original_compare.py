"""Compare original instructions -> UIL -> native ARM64, without a shared oracle."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import subprocess

from examples.civ.civ_city_original import OriginalCity
from examples.civ.civ_city_uil import _primitive_program, build_city_udc
from fdisbull.interaction_il import execute_il


def compare(source, output):
    output = Path(output).resolve()
    if any((p/".git").exists() for p in (output,*output.parents)):
        raise ValueError("original/native artifacts must stay outside Git")
    output.mkdir(exist_ok=False)
    oracle = OriginalCity(source)
    cases = list(itertools.product((-32768,-1,0,5,999,1000,32767),
                                   (-32768,-1,0,3,32767),(False,True)))
    rows=[]
    for index,(stock,delta,disorder) in enumerate(cases):
        original = oracle.observe(stock,delta,disorder,
            city=(0,1,63,127)[index%4],frame=(0x8800,0x9000)[index%2],maintenance=7)
        initial = {"$shield_box":original["sanitized_stock"],"$shield_delta":delta,
                   "$disorder":disorder,"$sanitized":True}
        modeled = execute_il(_primitive_program(), state=initial)
        if modeled["status"]!="complete" or modeled["state"]["$shield_box"]!=original["result"]:
            raise ValueError("source-to-UIL mismatch; native compilation cannot qualify this model")
        built = build_city_udc(source,output/str(index),project_path=output/(str(index)+".fdb"),
                               initial=initial,target="macos-arm64")
        proc = subprocess.run([str(output/str(index)/"program")],capture_output=True,text=True,timeout=30,check=True)
        native = json.loads(proc.stdout.splitlines()[-1])
        if native["status"]!=0 or native["state"]["$shield_box"]!=original["result"]:
            raise ValueError("original-to-native mismatch")
        rows.append(dict(stock=stock,delta=delta,disorder=disorder,
            sanitized_stock=original["sanitized_stock"],original_result=original["result"],
            uil_result=modeled["state"]["$shield_box"],native_result=native["state"]["$shield_box"],
            original_reset_code_sha256=original["reset"]["source_code_sha256"],
            original_update_code_sha256=original["update"]["source_code_sha256"],
            native_sha256=built["native_build"]["output"]["sha256"]))
    result=dict(format="fdisbull-civ-city-original-comparison-1",original_sha256=original["original_sha256"],
                cases=rows,matched=len(rows),mismatches=0,
                scope="finite original-instruction/UIL/native ARM64 comparisons; no whole-game claim")
    (output/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("source");p.add_argument("output")
    args=p.parse_args();r=compare(args.source,args.output)
    print(json.dumps(dict(matched=r["matched"],mismatches=r["mismatches"])))
