'use strict';
const D = window.STUDY;
const $ = id => document.getElementById(id);
const labels = {no_intervention:'No intervention',cash_buffer:'Larger cash buffer',credit_line:'Additional liquidity support',combined:'Combined intervention'};
const colors = {no_intervention:'#6b778a',cash_buffer:'#2583ae',credit_line:'#ce8337',combined:'#148276'};
const fields = D.path_fields;
const amount = x => (x / 1e9).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const cost = x => (x / 1e9).toLocaleString('en-US',{minimumFractionDigits:4,maximumFractionDigits:4});
const pct = x => x == null ? '—' : (x*100).toFixed(3)+'%';
const status = s => s.recovery_status==='never_backlogged'?'No backlog':s.clearance_day==null?'Not cleared in 30 days':'Day '+s.clearance_day;
let eventId='svb2023';
function settings(){return {redemption:+$('redemption').value,freeze:+$('freeze').value,sale:+$('sale').value,activation:+$('activation').value};}
function key(p){return [p.redemption,p.freeze,p.sale,p.activation].join('|');}
function selected(){return [...document.querySelectorAll('.check input:checked')].map(x=>x.value);}
function runs(){return D.grid[key(settings())].filter(r=>selected().includes(r.summary.strategy));}
function legend(strategies){return strategies.map(s=>`<span style="--swatch:${colors[s]}">${labels[s]}</span>`).join('');}
function chart(target, series, {xlabel='Simulation day',ylabel='',eventLine=false,percent=false,includeZero=true}={}) {
  const W=800,H=290,L=65,R=20,T=20,B=46;
  const points=series.flatMap(s=>s.points).filter(p=>p[1]!=null&&Number.isFinite(p[1]));
  if(!points.length){$(target).textContent='No observations available in this window';return;}
  let xmin=Math.min(...points.map(p=>p[0])),xmax=Math.max(...points.map(p=>p[0]));
  let ymin=Math.min(...points.map(p=>p[1])),ymax=Math.max(...points.map(p=>p[1]));
  if(includeZero){ymin=Math.min(0,ymin);ymax=Math.max(0,ymax);}
  if(ymin===ymax){ymax=ymin+1;if(ymin!==0)ymin-=1;}
  const pad=(ymax-ymin)*.08;ymax+=pad;if(ymin<0)ymin-=pad;
  const x=v=>L+(v-xmin)/(xmax-xmin||1)*(W-L-R),y=v=>T+(ymax-v)/(ymax-ymin)*(H-T-B);
  const tick=v=>Math.abs(v)>=100?v.toFixed(0):Math.abs(v)>=1?v.toFixed(1):v.toFixed(2);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><title>${$(target).getAttribute('aria-label')||ylabel}</title>`;
  for(let i=0;i<=4;i++){const v=ymin+(ymax-ymin)*i/4;svg+=`<line x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}" stroke="#e7ebe6"/><text x="${L-10}" y="${y(v)+4}" fill="#71817f" text-anchor="end" font-size="11">${tick(v)}</text>`;}
  const xticks=eventLine?[-14,-7,0,7,14]:(xmax===10?[1,3,5,10]:[1,5,10,15,20,25,30]);
  for(const v of xticks)svg+=`<text x="${x(v)}" y="${H-B+23}" fill="#71817f" text-anchor="middle" font-size="11">${v>0&&eventLine?'+':''}${v}</text>`;
  if(eventLine)svg+=`<line x1="${x(0)}" y1="${T}" x2="${x(0)}" y2="${H-B}" stroke="#92a8a0" stroke-dasharray="5 5"/>`;
  if(ymin<0&&ymax>0)svg+=`<line x1="${L}" y1="${y(0)}" x2="${W-R}" y2="${y(0)}" stroke="#a6b7af" stroke-dasharray="3 5"/>`;
  for(const s of series){let path='',pen=false;for(const p of s.points){if(p[1]==null||!Number.isFinite(p[1])){pen=false;continue;}path+=(pen?'L':'M')+x(p[0]).toFixed(2)+','+y(p[1]).toFixed(2);pen=true;}svg+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.6" stroke-linejoin="round"/>`;for(const p of s.points){if(p[1]==null)continue;svg+=`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3" fill="${s.color}"><title>${s.name} · Day ${p[0]}: ${p[1].toFixed(4)}${percent?'%':''}</title></circle>`;}}
  svg+=`<text x="${(W+L)/2}" y="${H-5}" text-anchor="middle" font-size="11" fill="#71817f">${xlabel}</text><text x="${L}" y="12" font-size="10" fill="#71817f">${ylabel}</text></svg>`;
  $(target).innerHTML=svg;
}
function renderHistory(){
  const e=D.events.find(e=>e.id===eventId);
  $('events').innerHTML=D.events.map(ev=>`<button type="button" class="event-button ${ev.id===eventId?'active':''}" data-event="${ev.id}" aria-pressed="${ev.id===eventId}"><strong>${ev.name}</strong><small>${ev.date}${ev.can_simulate?' · Stress-test case':''}</small></button>`).join('');
  $('event-title').textContent=e.name+' · '+e.date;
  chart('history-chart',[{name:'USDT',color:'#148276',points:e.points.map(p=>[p.day,p.USDT==null?null:(p.USDT-1)*100])},{name:'USDC',color:'#ce8337',points:e.points.map(p=>[p.day,p.USDC==null?null:(p.USDC-1)*100])}],{eventLine:true,xlabel:'Days relative to the event',ylabel:'Deviation (%)',percent:true});
  $('simulation').hidden=!e.can_simulate;$('history-only').hidden=e.can_simulate;
  $('evidence-title').textContent=e.can_simulate?'USDC · Retrospective reserve snapshot':'Observed history · No reserve simulation';
  $('evidence-body').innerHTML=e.can_simulate?`<p>Amounts in the 2023-02-28 report have been checked. The report was signed after the event and cannot be treated as information available beforehand.</p><dl><dt>Total reserves</dt><dd>${amount(D.balance.reserve_total)} USD billion</dd><dt>Initial stablecoin liabilities</dt><dd>${amount(D.balance.stablecoin_liabilities)} USD billion</dd><dt>Modelled net cash</dt><dd>${amount(D.balance.cash)} USD billion</dd></dl><p>Net cash includes signed settlement adjustments assumed settled before the shock. Treasuries are fund look-through assets; operating rights are unverified.</p>`:'<p>The window uses the same complete daily price calendar; it does not capture all intraday moves.</p><p>Corresponding reserve and operating evidence is missing for this event. The 2023 snapshot is not used as a substitute for other years.</p><p>Not all cases exceed the 1% depegging threshold.</p>';
}
function renderResults(){
  const p=settings(),all=runs(),ids=all.map(r=>r.summary.strategy),old=$('focus').value;
  $('focus').innerHTML=ids.map(s=>`<option value="${s}">${labels[s]}</option>`).join('');
  $('focus').value=ids.includes(old)?old:ids.includes('combined')?'combined':ids[ids.length-1];
  const focus=all.find(r=>r.summary.strategy===$('focus').value).summary;
  $('scenario-caption').textContent=`Redemptions ${p.redemption}% · Freeze ${p.freeze}d · Sales cap ${p.sale}% · Credit day ${p.activation}`;
  const metrics=[['Peak backlog',amount(focus.peak_unpaid_redemptions),'USD billion'],['Backlog clearance',status(focus),'Clear after the final scheduled request'],['Total economic cost',cost(focus.total_economic_cost),'USD billion · Including opportunity cost'],['Ending financing debt',amount(focus.ending_financing_debt),'USD billion · Principal and interest']];
  $('metrics').innerHTML=metrics.map(m=>`<div class="metric"><div class="label">${m[0]}</div><div class="number" style="${m[1].length>9?'font-size:20px':''}">${m[1]}</div><div class="unit">${m[2]}</div></div>`).join('');
  const insolvent=all.filter(r=>r.summary.solvency_warning).map(r=>labels[r.summary.strategy]);
  $('risk-note').hidden=!insolvent.length;$('risk-note').textContent='Solvency warning: '+insolvent.join(', ')+' have negative equity during the simulation. Insolvency resolution is not modelled; subsequent payment paths are not executable commitments.';
  $('strategy-legend').innerHTML=legend(ids);
  const series=field=>all.map(r=>({name:labels[r.summary.strategy],color:colors[r.summary.strategy],points:r.path.map(v=>[v[0],v[fields.indexOf(field)]==null?null:v[fields.indexOf(field)]/(field==='net_reserve_coverage'?.01:1e9)])}));
  chart('queue-chart',series('unpaid_redemptions'),{ylabel:'USD billion'});
  const secondary=$('secondary-metric').value;
  const title={financing_debt:['What debt remains after recovery?','Financing principal + accrued interest · USD billion'],free_cash:['Available cash','Excluding frozen cash · USD billion'],net_reserve_coverage:['Net reserve coverage','Assets net of financing debt / stablecoin liabilities · %'],equity:['Net equity','Assets − stablecoin liabilities − financing debt · USD billion']}[secondary];
  const head=document.querySelector('.secondary-chart .chart-heading');head.querySelector('h3').textContent=title[0];head.querySelector('p').textContent=title[1];
  chart('secondary-chart',series(secondary),{ylabel:secondary==='net_reserve_coverage'?'%':'USD billion',includeZero:secondary!=='net_reserve_coverage'});
  $('comparison').innerHTML=all.map(r=>{const s=r.summary;return `<tr class="${s.strategy===focus.strategy?'focus':''}"><td>${labels[s.strategy]}</td><td>${status(s)}</td><td>${amount(s.peak_unpaid_redemptions)}</td><td>${amount(s.unpaid_dollar_days)}</td><td>${cost(s.total_economic_cost)}</td><td>${amount(s.ending_financing_debt)}</td><td>${pct(s.min_net_coverage)}</td></tr>`;}).join('');
  chart('timing-chart',['credit_line','combined'].map(s=>({name:labels[s],color:colors[s],points:[1,3,5,10].map(a=>[a,D.grid[key({...p,activation:a})].find(r=>r.summary.strategy===s).summary.peak_unpaid_redemptions/1e9])})),{xlabel:'Credit activation day',ylabel:'Peak backlog (USD billion)'});
  $('boundaries').innerHTML=Object.keys(labels).map(s=>D.boundaries.find(b=>b.blocked_days===p.freeze&&Math.abs(b.daily_sale_percent-p.sale)<1e-9&&b.strategy===s)).map(b=>`<tr><td>${labels[b.strategy]}</td><td>${b.first_tested_failure_percent==null?'None through 80%':`(${b.previous_tested_clear_percent??0}%, ${b.first_tested_failure_percent}%]`}</td><td>${b.first_tested_negative_equity_percent==null?'None through 80%':b.first_tested_negative_equity_percent+'%'}</td></tr>`).join('');
}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(rows){const cols=Object.keys(rows[0]);const cell=v=>v==null?'':`"${String(v).replaceAll('"','""')}"`;return '\ufeff'+[cols.map(cell).join(','),...rows.map(r=>cols.map(c=>cell(r[c])).join(','))].join('\r\n');}
$('events').addEventListener('click',e=>{const b=e.target.closest('[data-event]');if(b){eventId=b.dataset.event;renderHistory();}});
$('back-svb').addEventListener('click',()=>{eventId='svb2023';renderHistory();$('simulation').scrollIntoView({behavior:'smooth'});});
for(const id of ['redemption','freeze','sale','activation','secondary-metric','focus'])$(id).addEventListener('change',renderResults);
document.querySelectorAll('.check input').forEach(e=>e.addEventListener('change',renderResults));
$('reset').addEventListener('click',()=>{for(const [id,v] of Object.entries({redemption:20,freeze:10,sale:1,activation:1}))$(id).value=v;document.querySelectorAll('.check input').forEach(e=>e.checked=true);$('focus').value='combined';$('secondary-metric').value='financing_debt';renderResults();});
$('export-results').addEventListener('click',()=>download('intervention_results.csv',csv(runs().map(r=>r.summary)),'text/csv;charset=utf-8'));
$('export-paths').addEventListener('click',()=>download('daily_paths.csv',csv(runs().flatMap(r=>r.path.map(v=>Object.fromEntries([['strategy',r.summary.strategy],...fields.map((f,i)=>[f,v[i]])])))),'text/csv;charset=utf-8'));
$('export-config').addEventListener('click',()=>download('scenario_config.json',JSON.stringify({event_id:eventId,configuration_key:key(settings()),selected_strategies:selected(),settings:settings(),balance:D.balance,policy:{...D.policy,credit_activation_day:settings().activation},fixed_scenario:D.manifest.scenario_fixed,code_sha256:D.manifest.code_sha256,input_sha256:D.manifest.input_sha256,limits:D.manifest.limits},null,2),'application/json'));
renderHistory();renderResults();
