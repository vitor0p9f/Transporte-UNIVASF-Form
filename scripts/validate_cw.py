"""Regenerate the four deterministic reports and check CW acceptance criteria.

Run sequentially so per-scenario wall times are not inflated by worker contention:
    python scripts/validate_cw.py --metrics .venv/cw-acceptance.json
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main
from scripts import run_controlled_reports as controlled
from scripts import run_top_real_fleet as real
from utils.paths import path_distance, path_time_minutes
from utils.scenarios import load_scenarios, pick_scenarios, parse_node_labels
from utils.fleet import load_fleet, parse_fleet_ids


def main_validation():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', type=Path)
    parser.add_argument('--repeat', type=int, default=2)
    args = parser.parse_args()
    if args.repeat < 2:
        parser.error('At least two runs are required to check determinism')
    scenarios = pick_scenarios(load_scenarios(ROOT))
    metrics = []
    previous = None
    for repetition in range(args.repeat):
        print(f'PASS {repetition+1}/{args.repeat}',flush=True)
        runs = []
        for s in scenarios:
            buses=load_fleet(ROOT/'fleet.csv',parse_fleet_ids(s['fleet_bus_ids']))
            for heuristic in (main.TOP_NAME,main.CW_NAME):
                print(f"START {s['scenario_id']} {heuristic}",flush=True)
                run=main.run_heuristic(s,buses,heuristic)
                assert not run.error
                assert len(run.plans) <= len(buses)
                for p in run.plans:
                    assert p.origin in parse_node_labels(s['origin'])
                    assert p.destination in parse_node_labels(s['destination_labels'])
                    assert p.travel_time_minutes == path_time_minutes(run.data.time,p.stops)
                    assert p.travel_time_minutes <= int(s['max_time_limit'])
                    capacity=(min(b.passenger_capacity for b in buses) if heuristic==main.CW_NAME
                              else next(b.passenger_capacity for b in buses if b.id==p.bus_id))
                    assert p.peak_load <= capacity
                served=sum(p.served_passengers for p in run.plans)
                assert served + run.summary.unserved_passengers == int(run.data.demand.sum())
                row=dict(repetition=repetition+1,scenario=s['scenario_id'],heuristic=heuristic,
                         served=served,total=int(run.data.demand.sum()),elapsed=round(run.elapsed,6))
                metrics.append(row)
                print(json.dumps(row),flush=True)
                if heuristic==main.CW_NAME:
                    assert run.elapsed <= 15, f"Performance target missed: {row}"
                    if s['scenario_id'] in ('65','69'):
                        assert served >= 50, f"Service target missed: {row}"
                runs.append(run)
        outputs={'results.md':main.render_markdown(runs,'',reproducible=True)}
        outputs['resultados_top_frota_real.md']=real.render_markdown(
            [r for r in runs if r.heuristic==main.TOP_NAME],'',reproducible=True)
        control_scenarios=controlled.select_scenarios()
        for config in controlled.CONFIGS.values():
            rows=[]
            for s in control_scenarios:
                print(f"START {config.filename} {s['scenario_id']}",flush=True)
                started=time.perf_counter()
                rows.extend(controlled.scenario_rows(s,config))
                print(f"DONE {s['scenario_id']} {time.perf_counter()-started:.3f}s",flush=True)
            outputs[config.filename]=controlled.render_report(config,rows,'',reproducible=True)
        encoded={name:text.encode('utf-8') for name,text in outputs.items()}
        if previous is not None:
            assert encoded == previous, 'Same seed/input did not generate identical report bytes'
        for filename,content in encoded.items():
            (ROOT/filename).write_bytes(content)
        previous=encoded
    payload=dict(seed=42,iterations=5000,post_improvement_iterations=500,measurements=metrics,
                 report_sha256={name:hashlib.sha256(content).hexdigest() for name,content in previous.items()})
    if args.metrics:
        args.metrics.parent.mkdir(parents=True,exist_ok=True)
        args.metrics.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('ALL ACCEPTANCE CHECKS PASSED; FOUR REPORTS IDENTICAL',flush=True)


if __name__=='__main__':
    main_validation()
