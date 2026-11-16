"""Verify exported demo results, model parity, inputs and local links."""
import argparse, hashlib, json, re, sys
from pathlib import Path
from dataclasses import fields
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stablecoin_risk.stress import Balance
from stablecoin_risk.midterm import experiment, configuration_key, STRATEGIES, PATH_FIELDS
import pandas as pd

def validate(out):
    text=(out/'data.js').read_text();d=json.loads(text.removeprefix('window.STUDY = ').removesuffix(';\n'))
    assert len(d['grid'])==300
    b=Balance(**{f.name:d['balance'][f.name] for f in fields(Balance)})
    csv=pd.read_csv(out/'results/demo_grid_results.csv')
    assert len(csv)==1200 and not csv.duplicated(['configuration','strategy']).any()
    for key,runs in d['grid'].items():
        assert [r['summary']['strategy'] for r in runs]==STRATEGIES
        for run in runs:
            s=run['summary'];rows=run['path']
            assert len(rows)==30 and [p[0] for p in rows]==list(range(1,31))
            assert all(len(p)==len(PATH_FIELDS) for p in rows)
            saved=csv[csv.configuration.eq(key)&csv.strategy.eq(s['strategy'])].iloc[0]
            for f in ['peak_unpaid_redemptions','total_economic_cost','ending_financing_debt','unpaid_at_horizon','unpaid_dollar_days']:
                assert abs(saved[f]-s[f])<.0001,(key,f)
            assert abs(max(p[1] for p in rows)-s['peak_unpaid_redemptions'])<.0001
            assert abs(sum(p[1] for p in rows)-s['unpaid_dollar_days'])<.0001
            assert (s['days_with_unpaid']==0)==(s['recovery_status']=='never_backlogged')
    # Model parity at endpoints and a delayed-credit scenario, independent from CSV rendering.
    for values in [(20,10,1,1),(20,10,1,5),(50,45,.1,10),(10,3,3,1)]:
        assert d['grid'][configuration_key(*values)]==experiment(b,*values)
    bd=pd.read_csv(out/'results/boundary_all_results.csv');assert len(bd)==4800
    for boundary in d['boundaries']:
        g=bd[bd.strategy.eq(boundary['strategy'])&bd.blocked_days.eq(boundary['blocked_days'])&((bd.treasury_daily_sale_fraction*100-boundary['daily_sale_percent']).abs()<1e-9)].sort_values('redemption_fraction')
        assert len(g)==80
        failures=g[g.unpaid_at_horizon>.05]
        actual=None if failures.empty else round(failures.iloc[0].redemption_fraction*100)
        assert boundary['first_tested_failure_percent']==actual
    for event in d['events']:
        assert len(event['points'])==29
        assert [p['day'] for p in event['points']]==list(range(-14,15))
        assert event['can_simulate']==(event['id']=='svb2023')
    missing=[]
    for page in ['index.html'] + [name for name in ['report-en.html','report.html'] if (out/name).is_file()]:
        for ref in re.findall(r'(?:src|href)="([^"]+)"',(out/page).read_text()):
            if not ref.startswith(('http:','https:','#')) and not (out/ref).exists():missing.append(ref)
    assert not missing,missing
    report=dict(status='passed',demo_runs=1200,boundary_runs=4800,model_parity_cases=4,event_windows=6,local_links='all present',data_js_sha256=hashlib.sha256((out/'data.js').read_bytes()).hexdigest())
    (out/'export_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();validate(a.results)
