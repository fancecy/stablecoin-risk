# USDT / USDC 次日脱锚风险识别

这是从 CSV 接入到「识别测试期高风险日期与连续 episode」的完整实现。当前未提供真实 master dataset，随附的 `data/demo_synthetic.csv` 和 `results/demo/` **全部属于模拟演示，不是 USDT / USDC 的历史实证结论**。项目不包含资产负债表仿真和压力测试。

## 先看哪些文件

- `DATA_CONTRACT.md`：交给负责数据的组员，包含全部必需列、单位和信息可用时间规则。
- `data/master_template.csv`：仅包含表头的正式输入模板。
- `scripts/train.py`：一次运行完整的 36 组实验。
- `scripts/evaluate.py`：基于已保存的预测分数和阈值，重建评估与 episode 表；不重新训练或调阈值。
- `results/demo/SUMMARY.md`：模拟运行的输出说明。
- `tests/test_integrity.py`：前视偏差、标签边界、数据集边界、缺失日期与 episode 的针对性测试。

```text
stablecoin-risk/
├── configs/default.json
├── data/
│   ├── master_template.csv
│   └── demo_synthetic.csv
├── scripts/
│   ├── validate_data.py
│   ├── make_demo_data.py
│   ├── train.py
│   └── evaluate.py
├── stablecoin_risk/
│   ├── data.py
│   ├── pipeline.py
│   └── evaluation.py
├── tests/test_integrity.py
├── results/demo/
├── DATA_CONTRACT.md
└── requirements.txt
```

## 安装与运行

在此项目目录运行，建议 Python 3.11–3.13：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows 的激活命令为 `.venv\Scripts\activate`。若 macOS 导入 XGBoost 报缺少 `libomp`，需要安装系统 OpenMP 运行库（例如 `brew install libomp`）；本次验证环境未遇到该问题。

直接使用附带模拟 CSV 重跑完整演示：

```bash
python scripts/train.py --input data/demo_synthetic.csv --output results/demo_new --data-kind synthetic
python scripts/evaluate.py --run-dir results/demo_new
python -m unittest discover -s tests -v
```

需要重新生成模拟数据时，使用一个新文件名：

```bash
python scripts/make_demo_data.py --output data/demo_new.csv
```

真实数据准备好后，放到 `data/master.csv`：

```bash
python scripts/validate_data.py --input data/master.csv
python scripts/train.py --input data/master.csv --config configs/default.json --output results/real_001
```

训练命令拒绝覆盖非空输出目录；新实验使用新目录。`evaluate.py` 会更新指定目录内的结果表，但不会改动模型、原始预测或报警阈值。模拟数据运行必须显式使用 `--data-kind synthetic`。

## 固定研究设定

每个币分别训练：2 个币 × 3 个标签阈值 × 3 个模型 × 2 组特征，共 **36 组**。

标签为 `abs(price[t+1] - 1) >= depeg_threshold`，三个阈值是 1%（主实验）、0.5% 和 1.5%（敏感性分析）。每一行是一个币的一个 UTC 日，以该日结束前实际可获得的输入预测下一自然日价格观测值是否脱锚。标签要求 t+1 当天有真实价格观测；不会把下一条记录误认为下一天，也不对缺失价格插值。

模型固定为 Logistic Regression、Random Forest、XGBoost。默认参数在 `pipeline.py`，不使用 test 进行调参。三个模型都仅根据 train 类别分布使用类别权重；缺失特征以 train 中位数填补，并添加缺失指示变量；Logistic 额外在 train 上拟合标准化器。全部训练预处理封装在模型 Pipeline 内。

### 特征对照

| 输出中的组名 | 实际输入 |
|---|---|
| `market_only` | 市场特征 + 宏观控制变量 |
| `market_reserve` | 完全相同的市场特征与宏观控制变量 + 储备特征 |

这里的 Market-only 指「不含储备的基准」，两组保持宏观控制变量相同，以隔离储备信息的增量。不要把它解释为排除了宏观的纯市场模型。

市场特征：当日绝对价格偏离、1 日收益率、交易量变化率、7/30 日收益率波动率、`log1p(volume)`、`log1p(market_cap)`、BTC/ETH 的 1 日收益率与 7 日波动率。窗口只使用 t 及以前数据，标准差使用样本标准差、不年化；内部补齐日历仅用于识别断档，不生成训练样本或填补价格。

储备特征：现金与银行存款/总储备、国债资产/总储备、总储备/披露时稳定币流通规模、报告期末距决策时点的天数。宏观变量：Fed Funds Rate、3-Month Treasury Yield、VIX。完整特征清单随每次运行写入 `run_manifest.json`。

### 时间切分与防泄漏

默认按两个币共同的、排序后的唯一日历日期确定前 60% / 中间 20% / 后 20% 的边界，不 shuffle。两币共用边界，分别训练。最终有效行数不一定恰好 60/20/20：每一段末尾凡 t+1 标签跨出该段的行都会排除；没有次日价格的行也会排除。

正式研究建议在看测试结果之前修改配置，填入共同的 `train_end`、`validation_end`、`test_end`（`YYYY-MM-DD`）。前两个必须一起填写；`test_end` 不填则使用数据末日。无需更改代码。分割日期是 t 的边界，标签也必须落在相同分割内。最后一日无法获得 t+1 标签，因此不纳入测试结果；这是回测实现，不是实时无标签预测服务。

储备和宏观变量须由数据组按「当时已公开的信息」预先对齐，代码检查可用时间不晚于 t 日结束。代码不向前回填储备、不跨币填充、不从验证或测试期拟合中位数。时间戳检查不能识别伪填的披露日期或事后修订值，因此仍须保留原始来源和历史版本。

### 阈值、模型选择与评估

1. 仅在 train 拟合模型。
2. 在 validation 预测值的不同取值上遍历报警阈值，以 **F2 最大**选择阈值；并列依次优先 Recall、Precision、更高阈值。F2 比 F1 更重视召回率，可在配置中修改 `threshold_beta`。
3. 固定模型与该阈值后，在 test 报告 PR-AUC、Recall、Precision、F1、ROC-AUC，并附类别数量、基准阳性率和混淆矩阵计数。
4. 每个币、每个脱锚标签阈值另选一个候选模型：仅按 validation PR-AUC、Recall、F1 排序，并列按模型名和特征组名排序。选中的模型不会用 train+validation 重训，避免改变已选阈值对应的分数分布。

PR-AUC 在本项目中明确采用 **Average Precision（AP，非插值）**，而不是梯形积分面积。定义见 [scikit-learn 官方说明](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html)。阈值候选来自 [precision_recall_curve](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_curve.html)。XGBoost 的实现接口参见 [官方 Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html)。

如果 train 只有一个类别、任意输入特征在 train 完全缺失，或任一分割不足配置的最小行数，该实验标记 skipped。若 validation 只有一个类别，模型可以保留预测结果，但无法确定可靠报警阈值，故禁用该实验的预警输出与候选模型选择。若 test 只有一个类别，本项目将 PR-AUC 和 ROC-AUC 留空并注明；没有正例时 Recall 留空。没有预测正例时 Precision 按 0 记录，F1 按零分母为 0 处理，便于复现。

同一 validation 同时用于阈值及候选模型选择，其指标存在选择乐观偏差，不能代替 test 指标。这个版本是固定时间留出实验，不包含滚动交叉验证、事件级置信区间或统计显著性检验；不能仅凭 AP 增量断言储备具有显著或因果影响。

### 高风险日期与 episode

`probability >= validation_selected_threshold` 即为预警。概率列是分类器输出的分数，类别加权后**未做概率校准**，不能直接把 0.8 解读为实际发生率 80%。

每个币、每个模型、每个特征组、每个标签阈值分别合并连续自然日的预警，日期断档或中间一天没有预警都会断开 episode。不跨币、不跨模型合并，不根据真实脱锚标签生成预警。

- `date`：预警生成日 t；`target_date`：预测风险日 t+1。
- `alert_start/end`：连续预警的 t 区间；`risk_start/end`：对应的 t+1 风险区间。
- `duration_days`：预警连续天数；`max_probability/mean_probability`：区间内分数汇总。
- `observed_depeg_days`：对应风险日中实际脱锚天数，仅用于事后核查，不参与报警生成。

这里的 episode 是**连续预警区间**，不是自动认定的金融危机事件。定义允许预测持续脱锚，并未限定为「首次脱锚开始」。

## 输出表说明

| 文件 | 用途 |
|---|---|
| `results_table.csv` | 36 组模型在 test 的指标（成功训练的实验才有行） |
| `metrics.csv` | validation + test 指标；检查阈值与评估依据 |
| `feature_comparison.csv` | 同币、同模型、同标签阈值下的两组指标与增量；delta = Reserve − Market |
| `thresholds.csv` | 从 validation 选出的报警概率阈值 |
| `validation_threshold_curves.csv` | 阈值候选及 Precision / Recall / F2 |
| `predictions.csv` / `test_predictions.csv` | 全部 validation/test 预测，及仅 test 预测 |
| `high_risk_dates.csv` / `high_risk_episodes.csv` | 所有模型的测试期预警日期 / 连续区间 |
| `selected_models.csv` | validation 选定的模型及其 validation 指标 |
| `selected_test_metrics.csv` | 入选模型在 test 上的指标 |
| `selected_high_risk_dates.csv` / `selected_high_risk_episodes.csv` | 入选模型的测试期预警；研究主线先筛选 depeg_threshold=0.01 |
| `class_counts.csv` / `run_status.csv` | 类别数量、实验成功/跳过状态及原因 |
| `split_assignments.csv` / `feature_missingness.csv` | 每行分割归属和各分割缺失率审计 |
| `run_manifest.json` | 输入文件哈希、日期边界、特征、配置、依赖版本 |
| `models/*.joblib` | 训练后的预处理器、模型、特征顺序和阈值 |

没有高风险日期时仍输出带表头的空文件。应先查看 `run_status.csv`，区分「模型没有报警」和「缺少有效阈值」。正式研究的结果表目前尚不存在；收到合格的真实 CSV 后按上述命令生成。
