"""Accounting-consistent conditional stress simulator, not a market-price model."""
from dataclasses import dataclass,asdict
import math

@dataclass(frozen=True)
class Balance:
    balance_id:str
    coin:str
    cash:float
    treasury:float
    stablecoin_liabilities:float
    data_kind:str='hypothetical'
    report_date:str=''
    other_assets:float=0.0
    def validate(self):
        nums=[self.cash,self.treasury,self.other_assets,self.stablecoin_liabilities]
        if not all(math.isfinite(v) and v>=0 for v in nums) or self.stablecoin_liabilities<=0:
            raise ValueError('Balance amounts must be finite/nonnegative; liabilities positive')

@dataclass(frozen=True)
class Scenario:
    redemption_fraction:float
    blocked_cash_fraction:float
    blocked_days:int
    treasury_market_shock:float
    treasury_sale_haircut:float
    treasury_daily_sale_fraction:float
    horizon:int=30
    def validate(self):
        for n in ['redemption_fraction','blocked_cash_fraction','treasury_market_shock','treasury_daily_sale_fraction']:
            if not math.isfinite(getattr(self,n)) or not 0<=getattr(self,n)<=1:raise ValueError(n)
        if not 0<=self.treasury_sale_haircut<1:raise ValueError('sale haircut must be <1')
        if not isinstance(self.horizon,int) or self.horizon<1 or not isinstance(self.blocked_days,int) or self.blocked_days<0:raise ValueError('day counts')

DEFAULT_POLICY=dict(cash_buffer_target_fraction_of_liabilities=.30,buffer_opportunity_spread_annual=.04,buffer_preposition_days=30,
 credit_limit_fraction_of_initial_liabilities=.10,credit_rate_annual=.08,credit_commitment_fee_annual=.005,collateral_per_dollar_principal=1.10,credit_activation_day=1)

def simulate(balance,scenario,strategy='no_intervention',policy=None,weights=(.4,.25,.15,.1,.1)):
    balance.validate();scenario.validate();policy={**DEFAULT_POLICY,**(policy or {})}
    if strategy not in ['no_intervention','cash_buffer','credit_line','combined']:raise ValueError('unknown strategy')
    if not weights or len(weights)>scenario.horizon or any(not math.isfinite(w) or w<0 for w in weights) or not math.isclose(sum(weights),1,abs_tol=1e-12):raise ValueError('redemption weights must sum to 1 and fit horizon')
    for key,value in policy.items():
        if not math.isfinite(value) or value<0:raise ValueError('invalid policy '+key)
    if not isinstance(policy['credit_activation_day'],int) or policy['credit_activation_day']<1:raise ValueError('invalid activation day')
    if policy['collateral_per_dollar_principal']<1:raise ValueError('collateral must cover principal')
    if policy['credit_limit_fraction_of_initial_liabilities']>1 or policy['cash_buffer_target_fraction_of_liabilities']>1:raise ValueError('invalid policy fraction')
    L0=balance.stablecoin_liabilities;cash=balance.cash;treasury=balance.treasury;other=balance.other_assets
    initial_equity=cash+treasury+other-L0
    line=strategy in ['credit_line','combined'];buffer=strategy in ['cash_buffer','combined']
    reallocated=min(treasury,max(0,policy['cash_buffer_target_fraction_of_liabilities']*L0-cash)) if buffer else 0.
    treasury-=reallocated;cash+=reallocated
    opportunity_cost=reallocated*policy['buffer_opportunity_spread_annual']*policy['buffer_preposition_days']/365
    limit=policy['credit_limit_fraction_of_initial_liabilities']*L0 if line else 0.
    fee=limit*policy['credit_commitment_fee_annual']*scenario.horizon/365
    if fee>cash:raise ValueError('cash insufficient to pay initial commitment fee')
    cash-=fee
    # Fixed baseline bank exposure. Extra buffer is assumed held outside frozen bank.
    blocked=min(cash,balance.cash*scenario.blocked_cash_fraction);cash-=blocked
    price_loss=treasury*scenario.treasury_market_shock;treasury-=price_loss
    principal=interest=paid_total=requested_total=sale_loss=0.
    daily_cap=balance.treasury*scenario.treasury_daily_sale_fraction
    rows=[];last_request_day=max(i+1 for i,w in enumerate(weights) if w>0) if scenario.redemption_fraction else 0
    for day in range(1,scenario.horizon+1):
        released=blocked if day>scenario.blocked_days else 0.;cash+=released;blocked-=released
        requested=L0*scenario.redemption_fraction*(weights[day-1] if day<=len(weights) else 0)
        requested_total+=requested;queue_before=requested_total-paid_total
        shortage=max(0.,queue_before-cash)
        collateral_factor=policy['collateral_per_dollar_principal']
        drawn=min(shortage,max(0.,limit-principal),max(0.,treasury/collateral_factor-principal)) if line and day>=policy['credit_activation_day'] else 0.
        cash+=drawn;principal+=drawn
        shortage=max(0.,queue_before-cash)
        unpledged=max(0.,treasury-principal*collateral_factor)
        sold=min(unpledged,daily_cap,shortage/(1-scenario.treasury_sale_haircut))
        proceeds=sold*(1-scenario.treasury_sale_haircut);loss=sold-proceeds
        treasury-=sold;cash+=proceeds;sale_loss+=loss
        paid=min(cash,queue_before);cash-=paid;paid_total+=paid
        queue=max(0.,requested_total-paid_total);liabilities=L0-paid_total
        daily_interest=principal*policy['credit_rate_annual']/365 if line else 0.;interest+=daily_interest
        # Interest is an end-horizon payable, not free financing and not stablecoin debt.
        debt=principal+interest;assets=cash+blocked+treasury+other
        equity=assets-liabilities-debt
        expected_equity=initial_equity-fee-price_loss-sale_loss-interest
        error=equity-expected_equity
        tol=max(.01,L0*1e-12)
        if abs(error)>tol or min(cash,blocked,treasury,queue,liabilities)<-tol or principal*collateral_factor>treasury+tol or paid_total>requested_total+tol:
            raise AssertionError('Accounting or collateral invariant failed')
        rows.append(dict(day=day,new_redemption_requests=requested,cumulative_requests=requested_total,redemptions_paid=paid,cumulative_paid=paid_total,
         unpaid_redemptions=queue,free_cash=cash,blocked_cash=blocked,treasury=treasury,other_assets=other,treasury_sold=sold,
         daily_liquidation_loss=loss,cumulative_liquidation_loss=sale_loss,credit_drawn=drawn,credit_principal=principal,interest_payable=interest,
         financing_debt=debt,pledged_treasury=principal*collateral_factor,stablecoin_liabilities=liabilities,assets=assets,equity=equity,
         net_reserve_coverage=(assets-debt)/liabilities if liabilities>1e-9 else None,total_liability_coverage=assets/(liabilities+debt) if liabilities+debt>1e-9 else None,
         accounting_error=error))
    last=rows[-1];tol=max(.01,L0*1e-12)
    clear=[r['day'] for r in rows if r['day']>=last_request_day and r['unpaid_redemptions']<=tol]
    summary=dict(balance_id=balance.balance_id,coin=balance.coin,data_kind=balance.data_kind,strategy=strategy,
      **asdict(scenario),credit_activation_day=policy['credit_activation_day'],initial_liabilities=L0,initial_equity=initial_equity,reallocated_cash=reallocated,opportunity_cost=opportunity_cost,
      commitment_fee=fee,market_price_loss=price_loss,liquidation_loss=sale_loss,interest_cost=interest,
      total_balance_sheet_loss=fee+price_loss+sale_loss+interest,total_economic_cost=fee+price_loss+sale_loss+interest+opportunity_cost,
      peak_unpaid_redemptions=max(r['unpaid_redemptions'] for r in rows),unpaid_at_horizon=last['unpaid_redemptions'],
      unpaid_dollar_days=sum(r['unpaid_redemptions'] for r in rows),days_with_unpaid=sum(r['unpaid_redemptions']>tol for r in rows),
      clearance_day=clear[0] if clear else None,ending_equity=last['equity'],ending_financing_debt=last['financing_debt'],
      min_net_coverage=min((r['net_reserve_coverage'] for r in rows if r['net_reserve_coverage'] is not None),default=None),
      days_with_negative_equity=sum(r['equity']<-tol for r in rows),max_accounting_error=max(abs(r['accounting_error']) for r in rows))
    return summary,rows
