from pathlib import Path
import numpy as np
import pandas as pd

MARKET_RAW = ['price', 'volume', 'market_cap', 'btc_price', 'eth_price']
MACRO = ['fed_funds_rate', 'treasury_3m_yield', 'vix']
RESERVE_RAW = ['reserve_total', 'cash_bank', 'treasury_assets', 'reserve_outstanding']
PROVENANCE = ['market_available_at', 'macro_available_at', 'reserve_available_at', 'reserve_report_date']
REQUIRED = ['date', 'coin'] + MARKET_RAW + MACRO + RESERVE_RAW + PROVENANCE
MARKET_FEATURES = ['price_deviation', 'return_1d', 'volume_change_1d',
                   'volatility_7d', 'volatility_30d', 'log_volume', 'log_market_cap',
                   'btc_return_1d', 'eth_return_1d', 'btc_volatility_7d', 'eth_volatility_7d']
RESERVE_FEATURES = ['cash_ratio', 'treasury_ratio', 'reserve_coverage', 'reserve_age_days']
FEATURE_SETS = {'market_only': MARKET_FEATURES + MACRO,
                'market_reserve': MARKET_FEATURES + MACRO + RESERVE_FEATURES}


def availability(series):
    """Unknown time within a publication date: wait until the next UTC day."""
    values = series.astype('string')
    out = pd.to_datetime(values, utc=True, format='mixed', errors='raise')
    date_only = values.str.fullmatch(r'\d{4}-\d{2}-\d{2}').fillna(False)
    return out + pd.to_timedelta(date_only.astype(int), unit='D')


def read_master(path):
    df = pd.read_csv(path)
    missing = sorted(set(REQUIRED) - set(df))
    if missing:
        raise ValueError('Missing input columns: ' + ', '.join(missing))
    if df.empty:
        raise ValueError('CSV contains a header but no observations.')
    df['date'] = pd.to_datetime(df['date'], utc=True, errors='raise')
    if df['date'].isna().any() or not df['date'].eq(df['date'].dt.normalize()).all():
        raise ValueError('date must be a nonmissing UTC calendar date (YYYY-MM-DD).')
    if set(df.coin) != {'USDT', 'USDC'}:
        raise ValueError('coin must contain both USDT and USDC, with no other symbols.')
    if df.duplicated(['coin', 'date']).any():
        raise ValueError('Duplicate (coin, date) rows.')
    for col in MARKET_RAW + MACRO + RESERVE_RAW:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if np.isinf(df[col]).any():
            raise ValueError(f'{col}: infinite values are invalid.')
    if df[MARKET_RAW].isna().any().any():
        raise ValueError('Market inputs cannot be missing; do not interpolate prices.')
    if (df[['price', 'btc_price', 'eth_price', 'market_cap']] <= 0).any().any() or (df.volume < 0).any():
        raise ValueError('Prices/market_cap must be positive; volume must be nonnegative.')
    for col in RESERVE_RAW:
        if (df[col].dropna() < 0).any():
            raise ValueError(f'{col} must be nonnegative.')
    for col in ['reserve_total', 'reserve_outstanding']:
        if (df[col].dropna() == 0).any():
            raise ValueError(f'{col} must be positive when known.')
    if ((df.cash_bank + df.treasury_assets) > df.reserve_total * (1 + 1e-6)).any():
        raise ValueError('cash_bank and treasury_assets must be nonoverlapping subsets of reserve_total.')
    df['decision_at'] = df.date + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    for col in ['market_available_at', 'macro_available_at', 'reserve_available_at']:
        df[col] = availability(df[col])
        group = MARKET_RAW if col.startswith('market') else MACRO if col.startswith('macro') else RESERVE_RAW
        known = df[group].notna().any(axis=1)
        if (known & df[col].isna()).any():
            raise ValueError(f'{col} is required wherever corresponding values are present.')
        if (df[col] > df.decision_at).any():
            raise ValueError(f'{col} contains future information relative to decision_at.')
    df['reserve_report_date'] = pd.to_datetime(df.reserve_report_date, utc=True, errors='raise')
    known = df[RESERVE_RAW].notna().any(axis=1)
    if (known & df.reserve_report_date.isna()).any():
        raise ValueError('reserve_report_date required for known reserves.')
    if (df.reserve_report_date > df.reserve_available_at).any():
        raise ValueError('Reserve report date cannot follow publication time.')
    return df.sort_values(['coin', 'date']).reset_index(drop=True)


def prepare(df):
    frames = []
    for coin, original in df.groupby('coin', sort=True):
        # Reindex only internally: gaps break daily returns, windows and t+1 labels.
        g = original.set_index('date').reindex(pd.date_range(original.date.min(), original.date.max(), freq='D'))
        g['date'] = g.index
        g['price_deviation'] = (g.price - 1).abs()
        g['return_1d'] = g.price.pct_change(fill_method=None)
        g['volume_change_1d'] = g.volume.pct_change(fill_method=None)
        for window in [7, 30]:
            g[f'volatility_{window}d'] = g.return_1d.rolling(window, min_periods=window).std()
        for asset in ['btc', 'eth']:
            g[f'{asset}_return_1d'] = g[f'{asset}_price'].pct_change(fill_method=None)
            g[f'{asset}_volatility_7d'] = g[f'{asset}_return_1d'].rolling(7, min_periods=7).std()
        g['log_volume'] = np.log1p(g.volume)
        g['log_market_cap'] = np.log1p(g.market_cap)
        g['cash_ratio'] = g.cash_bank / g.reserve_total
        g['treasury_ratio'] = g.treasury_assets / g.reserve_total
        g['reserve_coverage'] = g.reserve_total / g.reserve_outstanding
        g['reserve_age_days'] = (g.decision_at - g.reserve_report_date).dt.total_seconds() / 86400
        g['target_date'] = g.date + pd.Timedelta(days=1)
        g['target_price'] = g.price.shift(-1)
        g = g.loc[g.coin.notna()].copy()
        g[FEATURE_SETS['market_reserve']] = g[FEATURE_SETS['market_reserve']].replace([np.inf, -np.inf], np.nan)
        frames.append(g.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True)


def label(price, threshold):
    # Decimal CSV prices at the inclusive boundary should not fail due to binary rounding.
    return ((price - 1).abs() >= threshold - 1e-12).astype(int)


def boundaries(df, config):
    dates = pd.DatetimeIndex(sorted(df.date.unique()))
    if bool(config.get('train_end')) != bool(config.get('validation_end')):
        raise ValueError('Specify both train_end and validation_end, or neither.')
    if config.get('train_end'):
        train = pd.Timestamp(config['train_end'], tz='UTC')
        val = pd.Timestamp(config['validation_end'], tz='UTC')
    else:
        a, b = config['train_fraction'], config['validation_fraction']
        if not (0 < a < 1 and 0 < b < 1 and a + b < 1):
            raise ValueError('Invalid chronological split fractions.')
        n, m = int(len(dates) * a), int(len(dates) * (a + b))
        if not (0 < n < m < len(dates)):
            raise ValueError('Insufficient calendar dates for three partitions.')
        train, val = dates[n-1], dates[m-1]
    end = pd.Timestamp(config['test_end'], tz='UTC') if config.get('test_end') else dates[-1]
    if not dates[0] <= train < val < end <= dates[-1]:
        raise ValueError('Require first_date <= train_end < validation_end < test_end <= last_date.')
    return train, val, end


def partition(df, bounds):
    train, val, end = bounds
    d = df.copy()
    d['split'] = 'excluded'
    known = d.target_price.notna()
    d.loc[known & (d.date <= train) & (d.target_date <= train), 'split'] = 'train'
    d.loc[known & (d.date > train) & (d.date <= val) & (d.target_date <= val), 'split'] = 'validation'
    d.loc[known & (d.date > val) & (d.date <= end) & (d.target_date <= end), 'split'] = 'test'
    return d
