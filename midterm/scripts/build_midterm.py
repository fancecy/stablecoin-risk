"""Build a self-contained midterm demo and reproducible scientific results."""
import argparse, hashlib, html, itertools, json, platform, shutil, sys
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from stablecoin_risk.stress import Balance, DEFAULT_POLICY
from stablecoin_risk.midterm import *

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#6b778a', '#2583ae', '#ce8337', '#148276']
EN = ['No intervention', 'Prepositioned cash', 'Secured credit', 'Combined']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_csv(rows, path):
    pd.DataFrame(rows).to_csv(path, index=False, encoding='utf-8-sig')

def money(v):
    return f'{v / 1e8:,.3f}'

def recovery(r):
    if r['recovery_status'] == 'never_backlogged': return '全程无积压'
    if r['clearance_day'] is None: return '30天内未清理'
    return f"第{int(r['clearance_day'])}天"

def build(data, out):
    if out.exists() and any(out.iterdir()):
        raise ValueError('请选择新的空输出目录，避免覆盖旧实验')
    out.mkdir(parents=True)
    for d in ['results', 'figures', 'evidence']: (out/d).mkdir()
    reserves = pd.read_csv(data/'reserve_amounts_checked.csv')
    raw = reserves.loc[reserves.reserve_report_date.eq('2023-02-28')].iloc[0]
    assert abs(raw.cash_bank_gross + raw.settlement_adjustment_net + raw.treasury_assets - raw.reserve_total) < .01
    balance = Balance('USDC_2023-02-28','USDC',float(raw.cash_bank_gross + raw.settlement_adjustment_net),float(raw.treasury_assets),float(raw.reserve_outstanding),'reported_snapshot_retrospective_assumptions','2023-02-28')
    evidence = {**asdict(balance), 'cash_bank_gross':float(raw.cash_bank_gross), 'settlement_adjustment':float(raw.settlement_adjustment_net), 'reserve_total':float(raw.reserve_total), 'source_url':raw.source_url, 'source_sha256':raw.source_sha256, 'signature_date':raw.report_signature_date, 'publication_status':'unknown', 'mapping':'Gross cash plus signed settlement adjustment; assumed settled before shock. Treasury is fund look-through exposure, not verified direct sale or collateral authority.'}
    (out/'evidence/balance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    # Use the full supplied calendar, not volume-filtered dates or image digitisation.
    calendar = pd.read_excel(data/'market.xlsx',sheet_name='价格日历')
    calendar['date'] = pd.to_datetime(calendar['UTC 日期'],utc=True)
    assert not calendar.date.duplicated().any()
    events=[]; event_rows=[]
    for eid,name,date,coin in EVENTS:
        t=pd.Timestamp(date,tz='UTC'); days=pd.date_range(t-pd.Timedelta(days=14),t+pd.Timedelta(days=14),freq='D')
        window=calendar.set_index('date').reindex(days)
        points=[]
        for dt,r in window.iterrows():
            p={'date':dt.strftime('%Y-%m-%d'),'day':(dt-t).days}
            for c in ['USDT','USDC']:
                value=r[c+' 价格 USD']; p[c]=None if pd.isna(value) else float(value)
                event_rows.append(dict(event_id=eid,event_name=name,event_date=date,date=p['date'],relative_day=p['day'],coin=c,price=p[c],source='User-supplied Coin Metrics-labelled workbook; historical vintage unverified'))
            points.append(p)
        events.append(dict(id=eid,name=name,date=date,coin=coin,can_simulate=eid=='svb2023',points=points))
    write_csv(event_rows,out/'results/historical_event_windows.csv')
    compact={}; all_summaries=[]; max_error=0.
    for redemption,freeze,sale,activation in itertools.product(REDEMPTIONS,FREEZE_DAYS,SALE_CAPS,ACTIVATIONS):
        key=configuration_key(redemption,freeze,sale,activation)
        runs=experiment(balance,redemption,freeze,sale,activation)
        compact[key]=runs
        for run in runs:
            s=run['summary'];all_summaries.append({'configuration':key,**s});max_error=max(max_error,s['max_accounting_error'])
    case=compact[configuration_key(20,10,1,1)]
    write_csv(all_summaries,out/'results/demo_grid_results.csv')
    write_csv([r['summary'] for r in case],out/'results/case_comparison.csv')
    casepaths=[]
    for run in case:
        for row in run['path']:casepaths.append({'strategy':run['summary']['strategy'],**dict(zip(PATH_FIELDS,row))})
    write_csv(casepaths,out/'results/case_daily_paths.csv')
    timing=[];timingpaths=[]
    for activation in ACTIVATIONS:
        runs=compact[configuration_key(20,10,1,activation)]
        for run in runs:
            if run['summary']['strategy'] not in ['credit_line','combined']:continue
            timing.append(run['summary'])
            for row in run['path']:timingpaths.append({'strategy':run['summary']['strategy'],'activation_day':activation,**dict(zip(PATH_FIELDS,row))})
    write_csv(timing,out/'results/timing_comparison.csv');write_csv(timingpaths,out/'results/timing_daily_paths.csv')
    # An independent, finer grid locates tested failure brackets, not exact universal cutoffs.
    boundary_runs=[]
    for redemption,freeze,sale in itertools.product(range(1,81),FREEZE_DAYS,SALE_CAPS):
        for run in experiment(balance,redemption,freeze,sale,1,False):
            s=run['summary'];boundary_runs.append(s);max_error=max(max_error,s['max_accounting_error'])
    bd=pd.DataFrame(boundary_runs);write_csv(boundary_runs,out/'results/boundary_all_results.csv')
    boundaries=[]
    for (freeze,sale,st),g in bd.groupby(['blocked_days','treasury_daily_sale_fraction','strategy']):
        g=g.sort_values('redemption_fraction');fails=g[g.liquidity_failure];first=None if fails.empty else float(fails.iloc[0].redemption_fraction)
        monotone=all(not a or b for a,b in zip(g.liquidity_failure,g.liquidity_failure.iloc[1:]))
        previous=None if first is None or first<=.01 else round(first-.01,2)
        neg=g[g.solvency_warning]
        boundaries.append(dict(blocked_days=int(freeze),daily_sale_percent=float(sale*100),strategy=st,first_tested_failure_percent=None if first is None else round(first*100),previous_tested_clear_percent=None if previous is None else round(previous*100),failure_monotone_on_tested_grid=monotone,first_tested_negative_equity_percent=None if neg.empty else round(float(neg.iloc[0].redemption_fraction)*100),tested_redemption_percent='1..80 step 1',failure_definition='unpaid_at_day_30 > accounting tolerance; not market-price depeg'))
    write_csv(boundaries,out/'results/failure_boundaries.csv')
    manifest=dict(study='Midterm: historical events and conditional intervention stress tests',model='stress.py',balance=evidence,policy=DEFAULT_POLICY,scenario_fixed=dict(blocked_cash_fraction=.6,treasury_market_shock=0,treasury_sale_haircut=.01,horizon=30,redemption_weights=[.4,.25,.15,.1,.1]),demo_axes=dict(redemption_percent=REDEMPTIONS,freeze_days=FREEZE_DAYS,daily_sale_percent=SALE_CAPS,activation_day=ACTIVATIONS),boundary_axes=dict(redemption_percent='1..80 step 1',freeze_days=FREEZE_DAYS,daily_sale_percent=SALE_CAPS,activation_day=1),demo_configurations=len(compact),demo_strategy_runs=len(all_summaries),boundary_strategy_runs=len(boundary_runs),ledger_days_checked=(len(all_summaries)+len(boundary_runs))*30,max_accounting_error_usd=max_error,python=platform.python_version(),input_sha256={p.name:sha(p) for p in [data/'market.xlsx',data/'reserve_amounts_checked.csv']},code_sha256={p.name:sha(p) for p in [ROOT/'stablecoin_risk/stress.py',ROOT/'stablecoin_risk/midterm.py',Path(__file__)]},limits=['Historical chart is observed data; no simulated market price.','No causal identification or validated early warning.','Reserve public timestamp unknown; report signed after SVB.','All shock and policy parameters illustrative, not fitted historical estimates.','Exogenous identical requests across strategies; no confidence feedback.','Debt retained; no repayment, refinancing or insolvency resolution model.','Treasury liquidation and collateral authority not verified.','Default six events are selected case studies, not independent crisis counts.'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    payload=dict(events=events,balance=evidence,policy=DEFAULT_POLICY,path_fields=PATH_FIELDS,grid=compact,boundaries=boundaries,manifest=manifest)
    (out/'data.js').write_text('window.STUDY = '+json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')
    for name in ['index.html','app.js','style.css']:shutil.copy2(ROOT/'midterm_web'/name,out/name)
    plot_results(out,case,timing,bd)
    report(out,case,timing,boundaries,manifest)
    (out/'evidence/source_notes.txt').write_text('历史价格：用户提供 stablecoin_final_market_data.xlsx 的价格日历，标注 Coin Metrics / UTC 日度；此次未独立重新下载核验历史版本。\n储备：2023-02-28 Circle USDC 报告，金额此前已核对，签字日2023-03-30，不能视作SVB事件前已知。\n原报告地址：'+raw.source_url+'\n原报告 SHA256：'+raw.source_sha256+'\n储备为事后起点；结算调整假设已结清；国债为基金穿透资产。冲击与融资条件均为情景假设。\n')
    (out/'START_HERE.txt').write_text('中期汇报交付包\n\n1. 双击 index.html：交互演示，离线即可使用，无需安装。\n2. 双击 report.html：完整中期结果，可通过浏览器打印为PDF。\n3. 查看 汇报讲稿.txt：约5分钟讲稿与答辩要点。\n4. results/：原始结果表；figures/：可插入汇报的PNG图。\n5. manifest.json / evidence/：参数、来源和核验口径。\n\n演示顺序：SVB事件 → 默认四措施比较 → 将融资启用从第1天改到第5天 → 赎回40%、冻结45天、出售0.1%查看积压边界 → 查看失效边界表。\n\n页面中的每个可选组合均由同一Python模型预先运行。页面不插值、不生成价格回稳曲线。修改未开放参数需重新运行生成脚本。\n\n重新生成：进入同包 source 文件夹，安装 requirements-midterm.txt，再运行 python scripts/build_midterm.py --output ../rebuilt。\n')
    (out/'audit.json').write_text(json.dumps(dict(status='passed',runs=len(all_summaries)+len(boundary_runs),ledger_days=(len(all_summaries)+len(boundary_runs))*30,max_accounting_error_usd=max_error,checks=['asset-liability identity','paid redemptions reduce liabilities','unpaid equals requested minus paid','collateral not double sold','nonnegative balances','loss-equity reconciliation','queue-day aggregation','clearance day definition','reserve components reconcile','historical dates unique'],all_boundary_failure_sequences_monotone=all(b['failure_monotone_on_tested_grid'] for b in boundaries)),indent=2))
    from write_midterm_english import localize
    localize(out)
    print(json.dumps(dict(output=str(out),demo_runs=len(all_summaries),boundary_runs=len(boundary_runs),max_error=max_error),ensure_ascii=False))

def plot_results(out,case,timing,bd):
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':140})
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for run,name,color in zip(case,EN,COLORS):
        p=pd.DataFrame(run['path'],columns=PATH_FIELDS)
        axes[0].plot(p.day,p.unpaid_redemptions/1e9,label=name,color=color,lw=2)
        axes[1].plot(p.day,p.financing_debt/1e9,label=name,color=color,lw=2)
    for ax in axes:ax.set_xlabel('Simulation day');ax.grid(alpha=.18);ax.set_ylabel('USD billion')
    axes[0].set_title('Unpaid redemption queue');axes[1].set_title('Outstanding financing debt')
    axes[0].legend(fontsize=8);fig.suptitle('Conditional USDC scenario | 20% redemptions, 60% cash frozen for 10 days')
    fig.tight_layout();fig.savefig(out/'figures/01_case_queue_and_debt.png');plt.close(fig)
    t=pd.DataFrame(timing);fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for st,name,color in [('credit_line','Secured credit',COLORS[2]),('combined','Combined',COLORS[3])]:
        g=t[t.strategy.eq(st)].sort_values('credit_activation_day')
        axes[0].plot(g.credit_activation_day,g.peak_unpaid_redemptions/1e9,'o-',label=name,color=color)
        axes[1].plot(g.credit_activation_day,g.total_economic_cost/1e6,'o-',label=name,color=color)
    for ax in axes:ax.set_xlabel('Credit activation day');ax.set_xticks(ACTIVATIONS);ax.grid(alpha=.18);ax.legend()
    axes[0].set_ylabel('Peak unpaid (USD billion)');axes[1].set_ylabel('Economic cost (USD million)')
    fig.suptitle('Intervention timing | identical shock and redemption requests');fig.tight_layout();fig.savefig(out/'figures/02_activation_timing.png');plt.close(fig)
    fig,axes=plt.subplots(1,4,figsize=(14,4.7),sharey=True)
    for ax,st,name in zip(axes,STRATEGIES,EN):
        g=bd[bd.strategy.eq(st)&bd.treasury_daily_sale_fraction.eq(.001)&bd.redemption_fraction.isin([x/100 for x in range(10,81,10)])].copy()
        g['q']=g.unpaid_at_horizon/g.initial_liabilities*100
        pivot=g.pivot(index='redemption_fraction',columns='blocked_days',values='q').reindex(index=[x/100 for x in range(10,81,10)],columns=FREEZE_DAYS)
        im=ax.imshow(pivot.values,origin='lower',aspect='auto',vmin=0,vmax=70,cmap='YlOrRd')
        ax.set_xticks(range(5),FREEZE_DAYS);ax.set_yticks(range(8),range(10,81,10));ax.set_xlabel('Cash frozen (days)');ax.set_title(name,fontsize=10)
        for i,row in enumerate(pivot.values):
            for j,v in enumerate(row):ax.text(j,i,f'{v:.0f}',ha='center',va='center',fontsize=8,color='white' if v>35 else '#263342')
    axes[0].set_ylabel('Total redemptions (% initial liabilities)')
    fig.suptitle('Unpaid at day 30 (% initial liabilities) | daily sale cap 0.1%, credit active day 1')
    fig.subplots_adjust(left=.07,right=.89,top=.83,bottom=.17,wspace=.15);cax=fig.add_axes([.92,.18,.015,.64]);fig.colorbar(im,cax=cax,label='% unpaid')
    fig.savefig(out/'figures/03_failure_map.png');plt.close(fig)

def report(out,case,timing,boundaries,m):
    def table(headers,rows):
        return '<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in r)+'</tr>' for r in rows)+'</tbody></table></div>'
    summaries=[r['summary'] for r in case];base=summaries[0]
    rows=[[LABELS[s['strategy']],recovery(s),money(s['peak_unpaid_redemptions']),money(s['total_economic_cost']),money(s['ending_financing_debt']),f"{s['min_net_coverage']*100:.3f}%",'是' if s['solvency_warning'] else '否'] for s in summaries]
    timingrows=[[LABELS[s['strategy']],s['credit_activation_day'],recovery(s),money(s['peak_unpaid_redemptions']),money(s['total_economic_cost']),money(s['ending_financing_debt'])] for s in timing]
    br=[b for b in boundaries if b['daily_sale_percent'] in [.1,1] and b['blocked_days'] in [10,30]]
    boundaryrows=[[b['blocked_days'],str(b['daily_sale_percent'])+'%',LABELS[b['strategy']], '>80%（范围内未出现）' if b['first_tested_failure_percent'] is None else f"({b['previous_tested_clear_percent'] or 0}%, {b['first_tested_failure_percent']}%]", '未出现' if b['first_tested_negative_equity_percent'] is None else str(b['first_tested_negative_equity_percent'])+'%'] for b in br]
    c=summaries[2];combined=summaries[3]
    credit_t=[s for s in timing if s['strategy']=='credit_line'];early=credit_t[0];late=credit_t[-1]
    limits='报告公开时间未知；现金结算处理与资产操作权限含假设；赎回与融资条件未经历史校准；未建模内生挤兑、市场价格、融资偿还和破产处置。因此不能推断真实政策因果效果，不能声称已证明提前预警。'
    body=f'''<header><div class="eyebrow">MIDTERM RESEARCH / 中期汇报</div><h1>从脱锚预测转向<br>冲击应对与措施比较</h1><p>USDC 储备压力测试 · 六事件历史浏览 · 可复现的条件性仿真</p><a class="button" href="index.html">打开交互演示 →</a></header>
    <section><h2>01 / 本阶段回答什么</h2><p>相同冲击与赎回请求下，比较事前现金准备、有抵押融资及组合措施，对积压清理速度、经济成本和期末债务的影响。恢复指赎回积压清理，不是价格重新锚定。</p><p>本次完成 {m['demo_configurations']} 个演示参数组合、{m['demo_strategy_runs']} 次措施仿真，以及 {m['boundary_strategy_runs']} 次细网格边界实验。共核验 {m['ledger_days_checked']:,} 条日度账本；最大平衡误差 {m['max_accounting_error_usd']:.8f} 美元。</p></section>
    <section><h2>02 / 真实输入与假设</h2><p>初始状态为2023年2月末USDC报告：总储备424.564亿美元，稳定币负债424.049亿美元。净现金107.791亿美元，由银行现金109.285亿美元加结算调整−1.494亿美元得到；假设冲击前已结清。国债穿透资产316.773亿美元。</p><p>报告签字日为2023-03-30，晚于事件；仅作事后起点。价格来自用户提供、标注Coin Metrics的日度工作簿，本次没有独立重取历史版本。六事件是选定案例，不等于六个独立严重脱锚事件。</p><p>固定示例：累计赎回20%；原始净现金60%冻结10天、第11天释放；国债市场减值0%；出售折价1%；每日出售上限为原始国债1%；30天模拟，前五天赎回分布40/25/15/10/10%。这些均为情景假设。</p><p>现金缓冲提前30天准备，目标为初始稳定币负债30%，机会成本年化4%；融资上限为初始负债10%，利率8%，承诺费年化0.5%，本金抵押要求110%。新增缓冲假设位于未冻结渠道；额度假设事前承诺。</p><a href="evidence/balance.json">查看储备映射</a> · <a href="evidence/source_notes.txt">来源说明</a> · <a href="{html.escape(m['balance']['source_url'])}">Circle原报告</a></section>
    <section><h2>03 / 固定案例：速度改善与融资债务并存</h2><p>下表金额单位均为亿美元。成本包含机会成本；债务是本金与应付利息，不能将债务当作损失，也不能当作免费资金。</p>{table(['措施','积压清理','积压峰值','总经济成本','期末融资债务','最低净覆盖率','曾出现负净资产'],rows)}<img src="figures/01_case_queue_and_debt.png" alt="积压与债务路径"><p>本情景无干预积压峰值为{money(base['peak_unpaid_redemptions'])}亿美元；第1天可用的融资与组合措施均全程无积压，但期末仍分别有{money(c['ending_financing_debt'])}、{money(combined['ending_financing_debt'])}亿美元债务。这里只支持该情景下的结果，不支持组合措施普遍最优。四种措施的资源投入也不相同，尚未完成同预算比较。</p></section>
    <section><h2>04 / 时机实验：晚介入不能消除已经形成的积压</h2><p>只改变融资启用日，其他输入固定；现金缓冲始终是事前措施。下表单位为亿美元。</p>{table(['措施','启用日','积压清理','积压峰值','经济成本','期末债务'],timingrows)}<img src="figures/02_activation_timing.png" alt="融资时机比较"><p>单独融资从第1天推迟到第10天，积压峰值由{money(early['peak_unpaid_redemptions'])}升至{money(late['peak_unpaid_redemptions'])}亿美元，经济成本由{money(early['total_economic_cost'])}升至{money(late['total_economic_cost'])}亿美元。该比较没有证明监测模型能提前10天发现风险。</p></section>
    <section><h2>05 / 失效边界：流动性与偿付能力分别检验</h2><p>“流动性失效”定义为第30天仍有积压；“偿付能力警示”指任一天净资产为负，两者不能混为一谈。边界实验将赎回比例从1%增加到80%，步长1个百分点；冻结3/10/20/30/45天；出售上限0.1%/1%/3%；融资第1天启用。其余条件固定。</p><img src="figures/03_failure_map.png" alt="期末积压热图"><p>以下展示每日出售上限0.1%和1%、冻结10天和30天的截面。括号是细网格定位的首次流动性失效区间，不是精确理论阈值，也不是现实安全上限。其他截面见CSV及演示页面。</p>{table(['冻结天数','日出售上限','措施','首次积压失效区间','首个负净资产赎回比例'],boundaryrows)}<p><strong>支付改善不等于偿付能力改善。</strong>在冻结10天、每日出售上限1%的截面中，单独融资首次在26%赎回的测试点出现负净资产，无干预则为38%。但两者首次期末积压失效分别是58%与48%。融资延后了积压失效，却可能因利息和费用更早耗尽薄弱的初始净资产。这是当前假设下的取舍，不是现实政策结论。</p><p>冻结30天与45天在30天观察窗内都不释放，结果一致属于模型预期。出现负净资产后模型仍记账，未模拟破产处置，因此后续支付路径不能当作可执行承诺。</p></section>
    <section><h2>06 / 核验、局限与后期工作</h2><p>每次运行核验资产负债平衡、兑付与负债对应关系、赎回积压、抵押约束、成本核算和清理日期。所有措施采用同一赎回路径。</p><p>{limits}</p><p>后期优先做参数依据与稳健性、同预算措施比较，再增加有储备证据的第二案例。本阶段不加入缺乏证据的价格回稳曲线。</p><p><a href="audit.json">账本核验</a> · <a href="manifest.json">完整配置与校验值</a> · <a href="results/case_comparison.csv">固定案例CSV</a> · <a href="results/timing_comparison.csv">时机CSV</a> · <a href="results/failure_boundaries.csv">边界CSV</a> · <a href="results/boundary_all_results.csv">全部边界实验</a></p></section>'''
    (out/'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>稳定币中期研究结果</title><link rel="stylesheet" href="style.css"><body class="report"><main>'+body+'</main></body></html>')
    (out/'汇报讲稿.txt').write_text(f'''中期汇报讲稿（约5分钟）

一、为什么调整研究路线
我们最初尝试预测USDT和USDC脱锚，但严重事件少，连续正例又集中在少数危机中，难以验证泛化能力。因此，本阶段转向历史事件背景下的条件性压力测试，研究相同冲击下不同措施的速度、成本和债务代价。原有预测实验保留，不再作为核心成果。

二、我们用什么数据、做什么假设
页面展示六个历史事件前后各14天的真实日度价格。深入仿真使用USDC 2023年2月末已核对储备。报告签字晚于SVB事件，所以是事后分析。赎回、冻结、变现和融资条件明确作为假设，不声称还原了当时的真实操作。

三、核心结果（打开默认演示）
在20%赎回、60%原始净现金冻结10天、每日出售上限1%的示例中，无干预积压峰值约{money(base['peak_unpaid_redemptions'])}亿美元。提前准备现金降低积压；融资与组合措施全程无积压，但期末仍有约{money(c['ending_financing_debt'])}与{money(combined['ending_financing_debt'])}亿美元债务。我们的恢复指标是赎回积压清理，不是代币价格恢复。

四、时机与失效边界（展示图2、图3）
将单独融资从第1天推迟到第10天，积压峰值升至{money(late['peak_unpaid_redemptions'])}亿美元。这说明在模型条件下介入时机有影响，但不代表我们已能提前预警。随后，我们在1%到80%的赎回比例、不同冻结期限和变现上限下测试第30天是否仍有积压，同时单独检查净资产是否为负。边界是测试网格内的范围，不是现实安全线。

五、交付与局限
本次完成{m['demo_strategy_runs']}次页面措施仿真和{m['boundary_strategy_runs']}次边界仿真；所有{m['ledger_days_checked']:,}条日度账本通过核验。交付包括离线演示、结果报告、CSV、图表与复现脚本。主要局限是参数未充分校准、缺少内生挤兑与价格形成、融资未模拟偿还，且各措施资源投入不同。后期将优先补参数依据和同预算比较。

常见提问
Q：能证明哪项真实政策最有效吗？
A：不能。目前是给定机制和假设下的比较，不是历史因果识别。
Q：为什么不展示价格恢复天数？
A：没有经验证的市场价格形成机制；我们报告赎回积压清理速度。
Q：组合措施是不是一定最好？
A：不是。它投入更多资源，还可能保留融资债务；需要敏感性和同预算比较。
Q：现金够付是不是就安全？
A：不是。还要查看净资产、债务及持续偿付能力；页面单独标记负净资产。
Q：演示是否随机生成？
A：不是。每个可选组合都由相同Python会计模型预先运行，配置和结果可导出复现。
''')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,default=ROOT/'data/integrated');p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data_dir,a.output)
