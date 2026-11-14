import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from scripts.make_demo_data import make_demo
from stablecoin_risk.data import availability, boundaries, label, partition, prepare, read_master
from stablecoin_risk.evaluation import choose_threshold, episodes, evaluate
from stablecoin_risk.pipeline import build_reports, model_pipeline, PRED_COLS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'configs/default.json').read_text())


class IntegrityTests(unittest.TestCase):
    def read(self, df):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.csv'
            df.to_csv(path, index=False)
            return read_master(path)

    def test_inclusive_label_boundary(self):
        for threshold in [0.005, 0.01, 0.015]:
            p = pd.Series([1-threshold, 1+threshold, 1-threshold+1e-8, 1.0])
            self.assertEqual(label(p, threshold).tolist(), [1, 1, 0, 0])

    def test_calendar_gap_does_not_become_next_day(self):
        raw = self.read(make_demo(120))
        missing = raw.loc[raw.coin == 'USDC', 'date'].iloc[50]
        raw = raw.loc[~((raw.coin == 'USDC') & (raw.date == missing))]
        data = prepare(raw)
        prior = data.loc[(data.coin == 'USDC') & (data.date == missing-pd.Timedelta(days=1))]
        self.assertTrue(prior.target_price.isna().all())
        following = data.loc[(data.coin == 'USDC') & (data.date == missing+pd.Timedelta(days=1))]
        self.assertTrue(following.return_1d.isna().all())

    def test_purge_split_boundaries_and_shared_dates(self):
        data = prepare(self.read(make_demo(120)))
        bounds = boundaries(data, CONFIG)
        assigned = partition(data, bounds)
        for coin, g in assigned.groupby('coin'):
            self.assertTrue((g.loc[g.split == 'train', 'target_date'] <= bounds[0]).all())
            self.assertTrue((g.loc[g.split == 'validation', 'date'] > bounds[0]).all())
            self.assertTrue((g.loc[g.split == 'validation', 'target_date'] <= bounds[1]).all())
            self.assertTrue((g.loc[g.split == 'test', 'date'] > bounds[1]).all())
            self.assertTrue((g.loc[g.date.isin(bounds), 'split'] == 'excluded').all())

    def test_future_publication_rejected(self):
        for col in ['market_available_at', 'macro_available_at', 'reserve_available_at']:
            df = make_demo(120)
            df.loc[0, col] = '2030-01-01T00:00:00Z'
            with self.assertRaisesRegex(ValueError, 'future information'):
                self.read(df)

    def test_date_only_publication_waits_until_next_day(self):
        value = availability(pd.Series(['2024-01-01', '2024-01-01T12:00:00Z']))
        self.assertEqual(value.iloc[0], pd.Timestamp('2024-01-02', tz='UTC'))
        self.assertEqual(value.iloc[1], pd.Timestamp('2024-01-01T12:00:00Z'))

    def test_missing_columns_and_duplicates_rejected(self):
        raw = make_demo(120)
        with self.assertRaisesRegex(ValueError, 'Missing input columns: price'):
            self.read(raw.drop(columns='price'))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.read(pd.concat([raw, raw.iloc[:1]]))

    def test_future_market_values_cannot_change_past_features(self):
        raw = self.read(make_demo(120))
        original = prepare(raw)
        raw.loc[raw.date > pd.Timestamp('2021-03-01', tz='UTC'), ['price', 'btc_price', 'volume']] *= 2
        altered = prepare(raw)
        from stablecoin_risk.data import FEATURE_SETS
        past = original.date <= pd.Timestamp('2021-03-01', tz='UTC')
        pd.testing.assert_frame_equal(original.loc[past, FEATURE_SETS['market_reserve']],
                                      altered.loc[past, FEATURE_SETS['market_reserve']])

    def test_imputation_and_scaling_fit_only_training_values(self):
        x = pd.DataFrame({'feature': [1.0, np.nan, 3.0, 4.0]})
        model = model_pipeline('logistic', pd.Series([0, 1, 0, 1]), CONFIG)
        model.fit(x, [0, 1, 0, 1])
        median = model['imputer'].statistics_.copy()
        mean = model['scaler'].mean_.copy()
        model.predict_proba(pd.DataFrame({'feature': [1e9, np.nan]}))
        np.testing.assert_array_equal(median, model['imputer'].statistics_)
        np.testing.assert_array_equal(mean, model['scaler'].mean_)
        self.assertEqual(median[0], 3)

    def test_validation_threshold_and_single_class(self):
        y, p = np.array([0, 0, 1, 1]), np.array([.1, .2, .6, .9])
        threshold, curve = choose_threshold(y, p)
        self.assertEqual(threshold, .6)
        self.assertEqual(curve.f_beta.max(), 1)
        self.assertIsNone(choose_threshold(np.zeros(4), p)[0])
        self.assertTrue(np.isnan(evaluate(np.zeros(4), p, .6)['roc_auc']))
        self.assertTrue(np.isnan(evaluate(np.zeros(4), p, .6)['pr_auc']))

    def test_episodes_require_consecutive_calendar_dates(self):
        dates = pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-04'], utc=True)
        high = pd.DataFrame({'date': dates, 'target_date': dates+pd.Timedelta(days=1),
                             'probability': [.5, .7, .6], 'y_true': [0, 1, 0]})
        result = episodes(high)
        self.assertEqual(result.duration_days.tolist(), [2, 1])
        self.assertEqual(result.observed_depeg_days.tolist(), [1, 0])
        self.assertEqual(result.risk_start.iloc[0], pd.Timestamp('2024-01-02', tz='UTC'))
        self.assertTrue(episodes(high.iloc[:0]).empty)

    def test_selection_and_alerts_do_not_depend_on_test_labels(self):
        rows = []
        for model, val_score in [('logistic', [.1, .8]), ('random_forest', [.8, .1])]:
            for split in ['validation', 'test']:
                for i in range(2):
                    date = pd.Timestamp('2024-01-01', tz='UTC')+pd.Timedelta(days=i)
                    rows.append(dict(coin='USDC', depeg_threshold=.01, model=model,
                        feature_set='market_only', split=split, date=date,
                        target_date=date+pd.Timedelta(days=1), target_price=[1, .98][i],
                        y_true=i, probability=val_score[i], risk_threshold=.5,
                        high_risk=int(val_score[i] >= .5), run_id=model, data_kind='synthetic'))
        df = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_reports(df, out)
            chosen = (out/'selected_models.csv').read_bytes()
            dates = pd.read_csv(out/'selected_high_risk_dates.csv')[['date', 'probability']]
            df.loc[df.split == 'test', 'y_true'] = 1-df.loc[df.split == 'test', 'y_true']
            build_reports(df, out)
            self.assertEqual(chosen, (out/'selected_models.csv').read_bytes())
            pd.testing.assert_frame_equal(dates, pd.read_csv(out/'selected_high_risk_dates.csv')[['date', 'probability']])

    def test_empty_reports_have_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_reports(pd.DataFrame(columns=PRED_COLS), tmp)
            for filename in ['metrics.csv', 'high_risk_dates.csv', 'high_risk_episodes.csv', 'selected_models.csv']:
                self.assertTrue(pd.read_csv(Path(tmp)/filename).empty)


if __name__ == '__main__':
    unittest.main()
