"""Run all predeclared experiments; never select thresholds from test labels."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stablecoin_risk.pipeline import train

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', default=str(Path(__file__).resolve().parents[1] / 'configs/default.json'))
    parser.add_argument('--data-kind', choices=['real', 'synthetic'], default='real')
    args = parser.parse_args()
    try:
        result = train(args.input, json.loads(Path(args.config).read_text()), args.output, args.data_kind)
    except (ValueError, ImportError, FileNotFoundError) as exc:
        parser.exit(2, f'Cannot run: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['successful_runs'] == 0:
        sys.exit(2)
