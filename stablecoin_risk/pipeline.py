import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import FEATURE_SETS, REQUIRED, boundaries, label, partition, prepare, read_master
from .evaluation import EPISODE_COLS, choose_threshold, episodes, evaluate

KEYS = ['coin', 'depeg_threshold', 'model', 'feature_set']
PRED_COLS = KEYS + ['split', 'date', 'target_date', 'target_price', 'y_true', 'probability',
                    'risk_threshold', 'high_risk', 'run_id', 'data_kind']


def model_pipeline(name, y, config):
    seed = config['seed']
    weight = int((y == 0).sum()) / int((y == 1).sum())
    if name == 'logistic':
        model = LogisticRegression(C=1.0, class_weight='balanced', max_iter=3000, random_state=seed)
    elif name == 'random_forest':
        model = RandomForestClassifier(n_estimators=config['n_estimators'], max_depth=6,
                                       min_samples_leaf=5, class_weight='balanced',
                                       random_state=seed, n_jobs=1)
    else:
        from xgboost import XGBClassifier
        model = XGBClassifier(n_estimators=config['n_estimators'], max_depth=3,
                              learning_rate=0.05, min_child_weight=3, subsample=1,
                              colsample_bytree=1, reg_lambda=1, objective='binary:logistic',
                              eval_metric='logloss', scale_pos_weight=weight,
                              tree_method='hist', random_state=seed, n_jobs=1)
    steps = [('imputer', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True))]
    if name == 'logistic':
        steps.append(('scaler', StandardScaler()))
    return Pipeline(steps + [('model', model)])


def save_csv(df, path):
    df.to_csv(path, index=False, float_format='%.17g')


def build_reports(predictions, output):
    """Recompute metrics and alerts from frozen predictions/validation thresholds."""
    output = Path(output)
    records, alerts, episode_frames = [], [], []
    for key, group in predictions.groupby(KEYS, sort=True):
        meta = dict(zip(KEYS, key))
        meta['data_kind'] = group.data_kind.iloc[0]
        finite = group.risk_threshold.dropna().unique()
        if len(finite) > 1:
            raise ValueError('Inconsistent frozen thresholds for one model run.')
        threshold = float(finite[0]) if len(finite) else None
        for split, p in group.groupby('split'):
            records.append({**meta, 'split': split, 'risk_threshold': threshold,
                            **evaluate(p.y_true, p.probability, threshold)})
        test = group.loc[group.split == 'test'].copy()
        if threshold is not None:
            high = test.loc[test.probability >= threshold].copy()
            alerts.append(high)
            ep = episodes(high)
            for col, val in meta.items():
                ep[col] = val
            ep['risk_threshold'] = threshold
            episode_frames.append(ep)
    metric_cols = KEYS + ['data_kind', 'split', 'risk_threshold', 'n', 'positives', 'prevalence',
                         'pr_auc', 'roc_auc', 'recall', 'precision', 'f1', 'alerts',
                         'true_positives', 'false_positives', 'false_negatives', 'true_negatives', 'metric_note']
    metrics = pd.DataFrame(records, columns=metric_cols)
    high = pd.concat(alerts, ignore_index=True) if alerts else pd.DataFrame(columns=PRED_COLS)
    eps = pd.concat(episode_frames, ignore_index=True) if episode_frames else pd.DataFrame(columns=EPISODE_COLS + KEYS + ['data_kind', 'risk_threshold'])
    save_csv(metrics, output / 'metrics.csv')
    save_csv(high, output / 'high_risk_dates.csv')
    save_csv(eps, output / 'high_risk_episodes.csv')
    test_metrics = metrics.loc[metrics.split == 'test']
    save_csv(test_metrics, output / 'results_table.csv')
    join = ['coin', 'depeg_threshold', 'model', 'data_kind', 'split']
    a = metrics.loc[metrics.feature_set == 'market_only'].drop(columns='feature_set')
    b = metrics.loc[metrics.feature_set == 'market_reserve'].drop(columns='feature_set')
    comparison = a.merge(b, on=join, suffixes=('_market', '_reserve'))
    for col in ['pr_auc', 'recall', 'precision', 'f1', 'roc_auc']:
        comparison['delta_' + col] = comparison[col + '_reserve'] - comparison[col + '_market']
    save_csv(comparison, output / 'feature_comparison.csv')
    # Select a deployment candidate per coin/label definition solely on validation.
    candidates = metrics.loc[(metrics.split == 'validation') & metrics.pr_auc.notna() & metrics.risk_threshold.notna()]
    chosen = candidates.sort_values(['pr_auc', 'recall', 'f1', 'model', 'feature_set'],
                                    ascending=[False, False, False, True, True]).drop_duplicates(['coin', 'depeg_threshold'])
    save_csv(chosen, output / 'selected_models.csv')
    selected_keys = chosen[KEYS]
    save_csv(high.merge(selected_keys, on=KEYS), output / 'selected_high_risk_dates.csv')
    save_csv(eps.merge(selected_keys, on=KEYS), output / 'selected_high_risk_episodes.csv')
    save_csv(test_metrics.merge(selected_keys, on=KEYS), output / 'selected_test_metrics.csv')
    return metrics


def train(csv_path, config, output, data_kind='real'):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory is not empty. Choose a new run directory to preserve prior results.')
    # Fail up front if any of the three required model implementations is unavailable.
    import xgboost  # noqa: F401
    if config['threshold_beta'] <= 0 or config['n_estimators'] < 1:
        raise ValueError('threshold_beta and n_estimators must be positive.')
    if set(config['depeg_thresholds']) != {0.005, 0.01, 0.015} or len(config['depeg_thresholds']) != 3:
        raise ValueError('This experiment requires exactly 0.005, 0.01 and 0.015 label thresholds.')
    raw = read_master(csv_path)
    data = prepare(raw)
    bounds = boundaries(data, config)
    data = partition(data, bounds)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'models').mkdir()
    audit_cols = ['coin', 'date', 'target_date', 'target_price', 'split']
    save_csv(data[audit_cols], output / 'split_assignments.csv')
    missingness = data.groupby(['coin', 'split'])[FEATURE_SETS['market_reserve']].agg(lambda s: s.isna().mean())
    save_csv(missingness.reset_index(), output / 'feature_missingness.csv')
    manifest = {'data_kind': data_kind, 'input_name': Path(csv_path).name,
                'input_sha256': hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
                'config': config, 'boundaries': dict(zip(['train_end', 'validation_end', 'test_end'], map(str, bounds))),
                'features': FEATURE_SETS, 'required_columns': REQUIRED,
                'python': platform.python_version(),
                'packages': {p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'scikit-learn', 'xgboost', 'joblib']},
                'pr_auc_definition': 'average_precision_score (non-interpolated AP)',
                'probability_note': 'Class-weighted model scores; not calibrated event frequencies.',
                'threshold_policy': 'Validation F-beta maximum; ties: recall, precision, then higher threshold.',
                'selection_policy': 'Validation AP, recall, F1; deterministic lexical ties. No test selection.'}
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    predictions, statuses, thresholds, curves, counts = [], [], [], [], []
    for coin, full in data.groupby('coin'):
        splits = {s: full.loc[full.split == s].copy() for s in ['train', 'validation', 'test']}
        for cut in config['depeg_thresholds']:
            ys = {s: label(part.target_price, cut) for s, part in splits.items()}
            for s, y in ys.items():
                counts.append({'coin': coin, 'depeg_threshold': cut, 'split': s,
                               'n': len(y), 'positives': int(y.sum()), 'negatives': int((y == 0).sum())})
            for name in ['logistic', 'random_forest', 'xgboost']:
                for feature_set, columns in FEATURE_SETS.items():
                    meta = dict(coin=coin, depeg_threshold=cut, model=name, feature_set=feature_set)
                    run_id = f'{coin}_{cut:g}_{name}_{feature_set}'
                    reasons = []
                    for s in splits:
                        if len(splits[s]) < config['min_' + s + '_rows']:
                            reasons.append(f'insufficient_{s}_rows')
                    if ys['train'].nunique() < 2:
                        reasons.append('single_class_train')
                    empty_columns = [c for c in columns if splits['train'][c].isna().all()]
                    if empty_columns:
                        reasons.append('all_missing_train_features:' + ','.join(empty_columns))
                    if reasons:
                        statuses.append({**meta, 'run_id': run_id, 'status': 'skipped', 'reason': ';'.join(reasons)})
                        continue
                    model = model_pipeline(name, ys['train'], config)
                    model.fit(splits['train'][columns], ys['train'])
                    val_prob = model.predict_proba(splits['validation'][columns])[:, 1]
                    threshold, curve = choose_threshold(ys['validation'], val_prob, config['threshold_beta'])
                    thresholds.append({**meta, 'run_id': run_id, 'risk_threshold': threshold,
                                       'threshold_beta': config['threshold_beta'], 'data_kind': data_kind})
                    for k, v in meta.items():
                        curve[k] = v
                    curves.append(curve)
                    status = 'ok' if threshold is not None else 'no_validation_threshold'
                    statuses.append({**meta, 'run_id': run_id, 'status': status,
                                     'reason': '' if threshold is not None else 'single_class_validation; alerts disabled'})
                    for s in ['validation', 'test']:
                        part = splits[s]
                        prob = val_prob if s == 'validation' else model.predict_proba(part[columns])[:, 1]
                        pred = part[['date', 'target_date', 'target_price']].copy()
                        for k, v in meta.items():
                            pred[k] = v
                        pred['split'], pred['y_true'], pred['probability'] = s, ys[s].to_numpy(), prob
                        pred['risk_threshold'] = threshold if threshold is not None else np.nan
                        pred['high_risk'] = (prob >= threshold).astype(int) if threshold is not None else np.nan
                        pred['run_id'], pred['data_kind'] = run_id, data_kind
                        predictions.append(pred[PRED_COLS])
                    joblib.dump({'pipeline': model, 'features': columns, 'risk_threshold': threshold,
                                 'meta': meta, 'data_kind': data_kind}, output / 'models' / f'{run_id}.joblib')
    preds = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame(columns=PRED_COLS)
    save_csv(preds, output / 'predictions.csv')
    save_csv(preds.loc[preds.split == 'test'], output / 'test_predictions.csv')
    save_csv(pd.DataFrame(statuses), output / 'run_status.csv')
    save_csv(pd.DataFrame(counts), output / 'class_counts.csv')
    save_csv(pd.DataFrame(thresholds, columns=KEYS + ['run_id', 'risk_threshold', 'threshold_beta', 'data_kind']), output / 'thresholds.csv')
    save_csv(pd.concat(curves, ignore_index=True) if curves else pd.DataFrame(columns=['threshold', 'precision', 'recall', 'f_beta'] + KEYS), output / 'validation_threshold_curves.csv')
    metrics = build_reports(preds, output)
    ok = sum(s['status'] == 'ok' for s in statuses)
    warning = '模拟数据演示：所有数值和日期均不可用作真实研究结论。' if data_kind == 'synthetic' else '真实输入实验；请结合类别数量和信息可用时间审计解释结果。'
    summary = f'''# 稳定币实验运行结果\n\n{warning}\n\n- 完成并获得 validation 报警阈值：{ok}/36 组。\n- 预测目标：t+1 日 UTC 价格观测值偏离 1 美元；不是日内最高/最低价格事件。\n- 模型选择：仅根据 validation AP、Recall、F1；test 只做最终评估。\n- PR-AUC 使用 Average Precision；报警阈值按 validation F{config['threshold_beta']:g} 选择。\n- 分类权重使分数不等于经校准的真实发生概率。\n- Market-only 和 Market+Reserve 均包含相同宏观控制变量。\n\n## 查看顺序\n\n1. class_counts.csv 和 run_status.csv：样本/事件是否足够，是否有跳过的实验。\n2. results_table.csv：test 模型对照；feature_comparison.csv：储备增量（reserve 减 market）。\n3. selected_models.csv：每个币、每个标签阈值的 validation 入选模型。\n4. selected_test_metrics.csv：这些入选模型的 test 表现。\n5. selected_high_risk_dates.csv / selected_high_risk_episodes.csv：入选模型的预警日期与连续区间。\n\n日期表的 date 是预警生成日 t，target_date 是预测风险日 t+1；episode 同时列出两种区间。空表表示未识别出预警或无法确定阈值，须结合 run_status.csv 区分。不得根据 test 指标反复修改模型或阈值后继续将其称为独立测试。\n'''
    (output / 'SUMMARY.md').write_text(summary, encoding='utf-8')
    return {'successful_runs': ok, 'total_runs': len(statuses), 'metric_rows': len(metrics), 'output': str(output)}
