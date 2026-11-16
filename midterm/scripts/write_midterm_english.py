"""Localize the presentation layer without modifying simulation results."""
import argparse, hashlib, html, json, shutil
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
TITLE='Stablecoin Depegging Risk Prediction and Reserve Stress Testing'
SUBTITLE='Midterm Prototype: Historical Events and Intervention Analysis'
EVENT_NAMES={'tether2018':'Tether Discount','investigation2019':'Bitfinex / Tether Investigation','terra2022':'Terra / UST Shock','ftx2022':'FTX Liquidity Crisis','svb2023':'SVB Shock and USDC Depegging','curve2023':'Curve 3pool Imbalance'}
LABELS={'no_intervention':'No intervention','cash_buffer':'Larger cash buffer','credit_line':'Additional liquidity support','combined':'Combined intervention'}

def localize(out):
    manifest=json.loads((out/'manifest.json').read_text())
    manifest.update(project_title=TITLE,prototype_subtitle=SUBTITLE,prototype_scope='Reserve stress-testing stage; prediction remains exploratory; no validated forecast-to-intervention pipeline',proposal_alignment='Larger cash buffer reallocates existing assets before the shock; additional liquidity support is secured borrowing; combined intervention is an exploratory combination, not a separate reserve-rebalancing strategy. Separate reserve rebalancing remains unimplemented.')
    for file in ['scripts/build_midterm.py','scripts/write_midterm_english.py','midterm_web/index.html','midterm_web/app.js','midterm_web/style.css']:
        manifest['code_sha256'][Path(file).name]=hashlib.sha256((ROOT/file).read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    raw=(out/'data.js').read_text();data=json.loads(raw.removeprefix('window.STUDY = ').removesuffix(';\n'))
    for event in data['events']:event['name']=EVENT_NAMES[event['id']]
    data['manifest']=manifest
    (out/'data.js').write_text('window.STUDY = '+json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')
    for name in ['index.html','app.js','style.css']:shutil.copy2(ROOT/'midterm_web'/name,out/name)
    events=pd.read_csv(out/'results/historical_event_windows.csv');events['event_name']=events.event_id.map(EVENT_NAMES);events.to_csv(out/'results/historical_event_windows.csv',index=False,encoding='utf-8-sig')
    b=data['balance']
    (out/'evidence/source-notes-en.txt').write_text(f'''DATA PROVENANCE

Market prices: the supplied stablecoin_final_market_data.xlsx workbook, complete price-calendar sheet, labelled Coin Metrics / UTC daily. The historical data vintage has not been independently re-downloaded or verified. Event dates are selected reference cases, not independently counted crises.

Reserve snapshot: Circle USDC report as of 2023-02-28. Amounts were previously reconciled. Signature date: 2023-03-30; public release time is unverified. This is a retrospective input, not information established as available before SVB.
Source: {b['source_url']}
Original PDF SHA256: {b['source_sha256']}

Net cash includes the signed settlement adjustment, assumed settled before the shock. Treasury holdings are look-through fund assets; direct sale and collateral rights have not been established. All redemption, freeze, liquidation and financing parameters are illustrative assumptions.

Proposal title: {TITLE}
Midterm scope: historical case analysis and reserve stress testing. A separate reserve-rebalancing strategy and a validated prediction-to-intervention pipeline have not been implemented.
''')
    case=pd.read_csv(out/'results/case_comparison.csv');timing=pd.read_csv(out/'results/timing_comparison.csv');boundaries=pd.read_csv(out/'results/failure_boundaries.csv')
    def recovery(r):
        if r.recovery_status=='never_backlogged':return 'No backlog'
        return 'Not cleared in 30 days' if pd.isna(r.clearance_day) else f'Day {int(r.clearance_day)}'
    def table(headers,rows):
        return '<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    def bn(v):return f'{v/1e9:,.3f}'
    case_table=table(['Intervention','Backlog clearance','Peak backlog','Economic cost','Ending debt','Min. net coverage'],[[LABELS[r.strategy],recovery(r),bn(r.peak_unpaid_redemptions),f'{r.total_economic_cost/1e9:,.4f}',bn(r.ending_financing_debt),f'{r.min_net_coverage*100:.3f}%'] for r in case.itertuples()])
    timing_table=table(['Intervention','Credit starts','Clearance','Peak backlog','Economic cost','Ending debt'],[[LABELS[r.strategy],f'Day {r.credit_activation_day}',recovery(r),bn(r.peak_unpaid_redemptions),f'{r.total_economic_cost/1e9:,.4f}',bn(r.ending_financing_debt)] for r in timing.itertuples()])
    subset=boundaries[boundaries.blocked_days.eq(10)&boundaries.daily_sale_percent.eq(1)]
    boundary_table=table(['Intervention','First backlog failure bracket','First negative-equity point'],[[LABELS[r.strategy], 'None through 80%' if pd.isna(r.first_tested_failure_percent) else f'({int(r.previous_tested_clear_percent)}%, {int(r.first_tested_failure_percent)}%]', 'None through 80%' if pd.isna(r.first_tested_negative_equity_percent) else f'{int(r.first_tested_negative_equity_percent)}%'] for r in subset.itertuples()])
    report=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE} | Midterm Results</title><link rel="stylesheet" href="style.css"></head><body class="report"><main>
<header><div class="eyebrow">FTEC5510 / ADVANCED FINANCIAL INFRASTRUCTURE</div><h1 class="hero-title">{TITLE}</h1><p>{SUBTITLE}</p><a class="button" href="index.html">Open the interactive prototype →</a></header>
<section><h2>1. Alignment with the proposal</h2><p>The project retains the proposal's two-stage framing: depegging risk prediction and issuer reserve stress testing. This midterm prototype demonstrates the second stage through historical event analysis and conditional intervention comparisons. Prediction experiments remain exploratory; the prototype does not establish a validated forecast-to-intervention pipeline.</p><p>The larger cash buffer reallocates existing assets before the shock. Additional liquidity support is modelled as a secured credit facility with fees, interest, collateral constraints, and outstanding debt. The combined intervention is an additional comparison, not a relabelled reserve-rebalancing policy. A distinct reserve-rebalancing strategy remains future work.</p></section>
<section><h2>2. Inputs and assumptions</h2><p>Six selected events can be explored using observed daily prices. Only the SVB-USDC case has an attached reserve simulation. The February 2023 USDC report provides total reserves of USD {bn(b['reserve_total'])} billion and initial stablecoin liabilities of USD {bn(b['stablecoin_liabilities'])} billion. Modelled net cash is USD {bn(b['cash'])} billion, including signed settlement adjustments assumed settled before the shock.</p><p>The report was signed on March 30, 2023, after the event; publication timing is unverified. The snapshot is therefore a retrospective input, not evidence of information available for advance intervention.</p><p>The default scenario assumes cumulative redemptions of 20%, 60% of baseline net cash frozen for 10 days and released on day 11, no Treasury market-value shock, a 1% liquidation haircut, and a daily sales cap of 1% of original Treasury holdings. The horizon is 30 days. Requests arrive over the first five days in proportions of 40%, 25%, 15%, 10%, and 10%.</p><p>The cash-buffer target is 30% of initial liabilities, prepared 30 days before the shock at a 4% annual opportunity spread. Credit is capped at 10% of initial liabilities, costs 8% annual interest plus a 0.5% annual commitment fee, and requires collateral equal to 110% of principal. Extra cash is assumed outside the frozen channel; credit is assumed precommitted. These are scenario assumptions, not fitted historical parameters.</p><p><a href="evidence/source-notes-en.txt">Source notes</a> · <a href="evidence/balance.json">Reserve mapping</a> · <a href="{html.escape(b['source_url'])}">Original Circle report</a></p></section>
<section><h2>3. Intervention comparison</h2><p>Amounts below are in USD billion. Recovery refers to clearing redemption backlogs, not restoration of the secondary-market peg. Economic cost includes the opportunity cost of cash; outstanding debt is reported separately.</p>{case_table}<img src="figures/01_case_queue_and_debt.png" alt="Backlog and outstanding debt by intervention"><p>In this scenario, the larger cash buffer reduces the peak backlog. Credit available from day 1 and the combined intervention avoid a backlog, but both retain financing obligations at the end of the horizon. Their resource inputs differ; the results do not establish equal-budget superiority.</p></section>
<section><h2>4. Intervention timing</h2><p>Only the credit activation day changes. All interventions face the same exogenous requests and shock. Cash buffers are always prepared before the shock. Amounts are in USD billion.</p>{timing_table}<img src="figures/02_activation_timing.png" alt="Credit activation timing, peak backlog and economic cost"><p>Later funding cannot erase a backlog that has already occurred. This demonstrates conditional timing effects, not the predictive ability to issue an early warning.</p></section>
<section><h2>5. Failure boundaries and solvency</h2><p>Liquidity failure means a remaining backlog on day 30. A solvency warning means negative equity on at least one day. The boundary grid tests redemptions from 1% to 80%, in one-percentage-point increments, across freeze durations of 3, 10, 20, 30, and 45 days and daily sales caps of 0.1%, 1%, and 3%. Credit starts on day 1.</p><p>The table below fixes the freeze at 10 days and the daily sales cap at 1%. Brackets locate the first tested backlog failure, not an exact or real-world safety threshold.</p>{boundary_table}<p>Liquidity support can extend payment capacity while its fees and interest consume a thin equity cushion. In this slice, negative equity appears earlier under credit alone even though the first backlog failure occurs at a larger redemption shock. Once equity becomes negative, subsequent paths are accounting scenarios, not executable commitments: insolvency resolution is not modelled.</p><img src="figures/03_failure_map.png" alt="Unpaid redemptions at day 30 under a 0.1% daily sales cap"><p>The heatmap fixes the daily sales cap at 0.1%. A 30-day and a 45-day freeze both prevent release within the observation window, so they produce identical terminal outcomes here.</p></section>
<section><h2>6. Validation and limitations</h2><p>The prototype includes {manifest['demo_configurations']} selectable configurations and {manifest['demo_strategy_runs']:,} intervention runs, plus {manifest['boundary_strategy_runs']:,} boundary runs. All {manifest['ledger_days_checked']:,} daily ledgers were checked for balance-sheet identities, redemption accounting, collateral constraints, loss reconciliation, and clearance dates. Maximum accounting error: USD {manifest['max_accounting_error_usd']:.8f}.</p><p>Historical prices do not capture intraday lows. Public disclosure timing and direct reserve operating rights remain unverified. Requests are exogenous and identical across interventions; confidence feedback, endogenous runs, market-price formation, repayment, refinancing, and insolvency resolution are not modelled. The findings are conditional scenario outcomes, not causal estimates of real-world policy effects.</p><p>Next steps are evidence-based parameter ranges, equal-budget comparisons, a separate reserve-rebalancing policy, and a second case with adequate reserve evidence.</p><p><a href="results/case_comparison.csv">Case CSV</a> · <a href="results/timing_comparison.csv">Timing CSV</a> · <a href="results/failure_boundaries.csv">Boundary CSV</a> · <a href="audit.json">Accounting checks</a> · <a href="manifest.json">Manifest</a> · <a href="presentation-notes.txt">Presentation notes</a></p></section></main></body></html>'''
    (out/'report-en.html').write_text(report)
    (out/'presentation-notes.txt').write_text(f'''{TITLE}
{SUBTITLE}

1. Motivation
Severe depegging observations are scarce and clustered around a few events. We retain the proposal's project title and two-stage framework, but the midterm demonstration focuses on reserve stress testing. We have not validated an end-to-end early-warning pipeline.

2. Design
The prototype presents six historical event windows and a detailed retrospective SVB-USDC stress scenario. Four responses are compared under the same requests and initial balance sheet: no intervention, a larger prepositioned cash buffer, additional secured liquidity support, and their combination. A separate reserve-rebalancing strategy remains future work.

3. Default results
At 20% redemptions and a 10-day freeze of 60% of baseline cash, the no-intervention backlog peaks at approximately USD 2.915 billion. The larger cash buffer reduces this to USD 1.286 billion. Credit from day 1 and the combined intervention avoid a backlog, but leave approximately USD 4.196 billion and USD 2.242 billion in financing debt. These are conditional simulations, not reconstructed historical policy outcomes.

4. Timing and boundaries
We vary credit activation across days 1, 3, 5, and 10. We also test terminal backlogs across redemption sizes, freeze durations, and sales limits. Payment resilience and solvency are separate: financing may reduce liquidity shortfalls while its fees and interest erode equity. Boundary brackets come from a one-percentage-point grid and are not real-world safety limits.

5. Limits and next steps
The reserve report was signed after SVB; shock and financing parameters are illustrative. We do not model endogenous runs, market prices, or insolvency resolution. Next steps include better parameter evidence, equal-budget comparisons, distinct reserve rebalancing, and another supported case.

Demonstration sequence
Select SVB. Compare the four default interventions. Move credit activation to day 5. Then select 40% redemptions, a 45-day freeze and a 0.1% daily sales cap. Review terminal backlogs, debt and the failure brackets. Export the results and configuration.
''')
    print('English presentation updated; simulation values unchanged.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();localize(a.results)
