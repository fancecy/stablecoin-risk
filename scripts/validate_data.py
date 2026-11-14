"""Validate the master CSV contract before training."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stablecoin_risk.data import read_master, prepare, FEATURE_SETS

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    args = p.parse_args()
    try:
        df = prepare(read_master(args.input))
    except (ValueError, FileNotFoundError) as exc:
        p.exit(2, f'Invalid input: {exc}\n')
    print(df.groupby('coin').agg(rows=('date', 'size'), first_date=('date', 'min'), last_date=('date', 'max'), usable_targets=('target_price', 'count')).to_string())
    print('\nMissing feature fractions (some warm-up values are expected):')
    print(df[FEATURE_SETS['market_reserve']].isna().mean().to_string())
