import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, roc_auc_score,
                             precision_recall_curve, precision_score, recall_score, f1_score)


def choose_threshold(y, scores, beta=2):
    if len(np.unique(y)) != 2:
        return None, pd.DataFrame(columns=['threshold', 'precision', 'recall', 'f_beta'])
    precision, recall, thresholds = precision_recall_curve(y, scores)
    precision, recall = precision[:-1], recall[:-1]
    b2 = beta ** 2
    fb = np.divide((1+b2)*precision*recall, b2*precision+recall,
                   out=np.zeros_like(precision), where=(b2*precision+recall) != 0)
    curve = pd.DataFrame({'threshold': thresholds, 'precision': precision, 'recall': recall, 'f_beta': fb})
    # Fully specified tie-breaking, using validation data only.
    best = curve.sort_values(['f_beta', 'recall', 'precision', 'threshold'], ascending=[False, False, False, False]).iloc[0]
    return float(best.threshold), curve


def evaluate(y, scores, threshold):
    y = np.asarray(y)
    both = len(np.unique(y)) == 2
    result = {'n': len(y), 'positives': int(y.sum()), 'prevalence': float(y.mean()),
              'pr_auc': float(average_precision_score(y, scores)) if both else np.nan,
              'roc_auc': float(roc_auc_score(y, scores)) if both else np.nan,
              'recall': np.nan, 'precision': np.nan, 'f1': np.nan,
              'alerts': np.nan, 'true_positives': np.nan, 'false_positives': np.nan,
              'false_negatives': np.nan, 'true_negatives': np.nan,
              'metric_note': '' if both else 'single_class: PR-AUC/ROC-AUC undefined by project policy'}
    if threshold is not None:
        pred = np.asarray(scores) >= threshold
        result.update(precision=float(precision_score(y, pred, zero_division=0)),
                      recall=float(recall_score(y, pred, zero_division=0)) if y.sum() else np.nan,
                      f1=float(f1_score(y, pred, zero_division=0)), alerts=int(pred.sum()),
                      true_positives=int(((y == 1) & pred).sum()),
                      false_positives=int(((y == 0) & pred).sum()),
                      false_negatives=int(((y == 1) & ~pred).sum()),
                      true_negatives=int(((y == 0) & ~pred).sum()))
    return result


EPISODE_COLS = ['episode_id', 'alert_start', 'alert_end', 'risk_start', 'risk_end',
                'duration_days', 'max_probability', 'mean_probability', 'observed_depeg_days']


def episodes(high):
    if high.empty:
        return pd.DataFrame(columns=EPISODE_COLS)
    high = high.sort_values('date').copy()
    group = high.date.diff().ne(pd.Timedelta(days=1)).cumsum()
    rows = []
    for i, g in high.groupby(group):
        rows.append(dict(episode_id=int(i), alert_start=g.date.min(), alert_end=g.date.max(),
                         risk_start=g.target_date.min(), risk_end=g.target_date.max(),
                         duration_days=len(g), max_probability=g.probability.max(),
                         mean_probability=g.probability.mean(), observed_depeg_days=int(g.y_true.sum())))
    return pd.DataFrame(rows, columns=EPISODE_COLS)
