# 稳定币实验运行结果

模拟数据演示：所有数值和日期均不可用作真实研究结论。

- 完成并获得 validation 报警阈值：36/36 组。
- 预测目标：t+1 日 UTC 价格观测值偏离 1 美元；不是日内最高/最低价格事件。
- 模型选择：仅根据 validation AP、Recall、F1；test 只做最终评估。
- PR-AUC 使用 Average Precision；报警阈值按 validation F2 选择。
- 分类权重使分数不等于经校准的真实发生概率。
- Market-only 和 Market+Reserve 均包含相同宏观控制变量。

## 查看顺序

1. class_counts.csv 和 run_status.csv：样本/事件是否足够，是否有跳过的实验。
2. results_table.csv：test 模型对照；feature_comparison.csv：储备增量（reserve 减 market）。
3. selected_models.csv：每个币、每个标签阈值的 validation 入选模型。
4. selected_test_metrics.csv：这些入选模型的 test 表现。
5. selected_high_risk_dates.csv / selected_high_risk_episodes.csv：入选模型的预警日期与连续区间。

日期表的 date 是预警生成日 t，target_date 是预测风险日 t+1；episode 同时列出两种区间。空表表示未识别出预警或无法确定阈值，须结合 run_status.csv 区分。不得根据 test 指标反复修改模型或阈值后继续将其称为独立测试。
