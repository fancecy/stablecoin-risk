"""Midterm experiment definitions; all financial calculations use stress.simulate."""
from dataclasses import asdict
from .stress import Balance, Scenario, simulate, DEFAULT_POLICY

STRATEGIES = ['no_intervention', 'cash_buffer', 'credit_line', 'combined']
LABELS = dict(zip(STRATEGIES, ['无干预', '事前现金缓冲', '有抵押融资', '组合措施']))
REDEMPTIONS = [10, 20, 30, 40, 50]
FREEZE_DAYS = [3, 10, 20, 30, 45]
SALE_CAPS = [0.1, 1, 3]
ACTIVATIONS = [1, 3, 5, 10]
EVENTS = [
    ('tether2018', 'Tether 折价', '2018-10-15', 'USDT'),
    ('investigation2019', 'Bitfinex / Tether 调查公开', '2019-04-25', 'USDT'),
    ('terra2022', 'Terra / UST 冲击', '2022-05-12', 'USDT'),
    ('ftx2022', 'FTX 流动性危机', '2022-11-10', 'USDT'),
    ('svb2023', 'SVB 冲击下 USDC 脱锚', '2023-03-11', 'USDC'),
    ('curve2023', 'Curve 3pool 失衡', '2023-06-15', 'USDT'),
]
PATH_FIELDS = ['day', 'unpaid_redemptions', 'free_cash', 'net_reserve_coverage', 'financing_debt', 'equity']

def scenario(redemption=20, freeze=10, sale=1):
    return Scenario(redemption / 100, .6, freeze, 0, .01, sale / 100, 30)

def configuration_key(redemption, freeze, sale, activation):
    return f'{redemption}|{freeze}|{sale:g}|{activation}'

def recovery_status(summary):
    if summary['days_with_unpaid'] == 0:
        return 'never_backlogged'
    if summary['clearance_day'] is None:
        return 'uncleared_at_horizon'
    return 'cleared'

def experiment(balance, redemption=20, freeze=10, sale=1, activation=1, keep_paths=True):
    s = scenario(redemption, freeze, sale)
    policy = {**DEFAULT_POLICY, 'credit_activation_day': activation}
    results = []
    for strategy in STRATEGIES:
        summary, paths = simulate(balance, s, strategy, policy)
        validate_run(balance, summary, paths)
        summary['recovery_status'] = recovery_status(summary)
        summary['liquidity_failure'] = summary['unpaid_at_horizon'] > max(.01, balance.stablecoin_liabilities * 1e-12)
        summary['solvency_warning'] = summary['days_with_negative_equity'] > 0
        results.append({'summary': summary, 'path': [[r[k] for k in PATH_FIELDS] for r in paths] if keep_paths else []})
    return results

def validate_run(balance, summary, paths):
    """Independently check all saved scientific runs, including queue and loss accounting."""
    tol = max(.01, balance.stablecoin_liabilities * 1e-12)
    for r in paths:
        assert abs(r['assets'] - r['stablecoin_liabilities'] - r['financing_debt'] - r['equity']) < tol
        assert abs(r['stablecoin_liabilities'] - (balance.stablecoin_liabilities - r['cumulative_paid'])) < tol
        assert abs(r['unpaid_redemptions'] - (r['cumulative_requests'] - r['cumulative_paid'])) < tol
        assert r['pledged_treasury'] <= r['treasury'] + tol
        assert min(r['free_cash'], r['blocked_cash'], r['treasury'], r['unpaid_redemptions']) >= -tol
    assert abs(summary['ending_equity'] - (summary['initial_equity'] - summary['total_balance_sheet_loss'])) < tol
    assert abs(summary['unpaid_dollar_days'] - sum(r['unpaid_redemptions'] for r in paths)) < tol
    last_request = max((r['day'] for r in paths if r['new_redemption_requests'] > 0), default=0)
    eligible = [r['day'] for r in paths if r['day'] >= last_request and r['unpaid_redemptions'] <= tol]
    assert summary['clearance_day'] == (eligible[0] if eligible else None)
