"""Generate synthetic data solely for execution testing, never for research claims."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from stablecoin_risk.data import REQUIRED


def make_demo(days=1200, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2021-01-01', periods=days, freq='D', tz='UTC')
    btc = 30000 * np.exp(np.cumsum(rng.normal(0, 0.02, days)))
    eth = 1500 * np.exp(np.cumsum(rng.normal(0, 0.025, days)))
    rows = []
    for coin, size in [('USDT', 65e9), ('USDC', 35e9)]:
        shock = np.zeros(days)
        stress = np.zeros(days)
        for event, start in enumerate(range(65, days-8, 55)):
            amplitude = [0.007, 0.012, 0.019, 0.025][event % 4]
            shock[start:start+5] = amplitude
            stress[start-2:start+5] = 1
        price = 1 + rng.normal(0, 0.0005, days) - shock - stress * 0.0008
        for i, date in enumerate(dates):
            report = date.normalize().replace(day=1) - pd.Timedelta(days=1)
            published = report + pd.Timedelta(days=7, hours=12)
            if published > date + pd.Timedelta(hours=23, minutes=59, seconds=59):
                report = report.replace(day=1) - pd.Timedelta(days=1)
                published = report + pd.Timedelta(days=7, hours=12)
            reserve = size * (1.03 + 0.01 * np.sin(report.month))
            cash = reserve * (0.13 + 0.03 * np.cos(report.month))
            rows.append(dict(date=date.strftime('%Y-%m-%d'), coin=coin, price=price[i],
                volume=size*(0.03+0.08*stress[i])*rng.uniform(0.8, 1.2), market_cap=size*price[i],
                btc_price=btc[i], eth_price=eth[i], fed_funds_rate=2.0+0.5*np.sin(i/180),
                treasury_3m_yield=2.1+0.5*np.sin(i/180), vix=18+5*stress[i]+rng.normal(0, 1),
                reserve_total=reserve, cash_bank=cash, treasury_assets=reserve*0.75,
                reserve_outstanding=size,
                market_available_at=(date + pd.Timedelta(hours=23, minutes=59, seconds=59)).isoformat(),
                macro_available_at=(date + pd.Timedelta(hours=21)).isoformat(),
                reserve_available_at=published.isoformat(), reserve_report_date=report.strftime('%Y-%m-%d')))
    return pd.DataFrame(rows, columns=REQUIRED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/demo_synthetic.csv')
    parser.add_argument('--days', type=int, default=1200)
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        parser.exit(2, f'Refusing to overwrite {out}\n')
    out.parent.mkdir(parents=True, exist_ok=True)
    make_demo(args.days).to_csv(out, index=False, float_format='%.17g')
    print(f'SYNTHETIC DATA ONLY: {out}')
