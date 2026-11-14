"""Rebuild evaluation tables using saved predictions and frozen thresholds."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from stablecoin_risk.pipeline import build_reports

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True)
    args = p.parse_args()
    root = Path(args.run_dir)
    df = pd.read_csv(root / 'predictions.csv', float_precision='round_trip')
    for c in ['date', 'target_date']:
        df[c] = pd.to_datetime(df[c], utc=True)
    build_reports(df, root)
    print(f'Rebuilt evaluation tables in {root}; thresholds unchanged.')
