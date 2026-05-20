# Fund Pool Model（重写增强版）

这是一个用于**公募基金池构建、日度选基、组合权重生成、结果落库与简易回测**的本地化 Python 项目。

这版重写重点不在“代码换个写法”，而在把原工程整理成一个更适合长期迭代的小型研究系统：

- 配置集中管理，支持环境变量与 GUI 覆盖
- SQLite 写入显式做类型清洗，避免 `numpy.int64` 被写成 BLOB
- 主流程拆成明确阶段：基金池 → 抓取 → 读库 → 因子 → 打分 → 组合 → 风险提示 → 导出 → 回测
- 保留原主要接口，尽量不破坏 GUI 与既有调用方式
- 补齐 `requirements.txt`、`.env.example`、`run_backtest_fund.py`

## 项目结构

```text
Fund_pool_model_rewritten/
├── data/
├── db/
├── output/
├── gui/
├── src/
│   ├── config.py
│   ├── dao.py
│   ├── universe_fund.py
│   ├── data_loader_fund.py
│   ├── feature_engineering_fund.py
│   ├── scoring_model.py
│   ├── optimizer.py
│   ├── risk_checks.py
│   ├── reporting.py
│   ├── pipeline.py
│   ├── backtest_quick_fund.py
│   ├── data_fetcher_ak_fund.py
│   └── parallel_fetch.py
├── requirements.txt
├── .env.example
├── init_db.py
├── reset_db.py
├── run_daily_fund.py
└── run_backtest_fund.py
```

## 主要能力

1. 读取或补齐基金池 `data/universe_fund.csv`
2. 抓取并增量写入基金净值到 SQLite
3. 从数据库读取净值并构造日收益率
4. 计算收益、波动、Sharpe、IR、最大回撤等因子
5. 进行横截面标准化与综合打分
6. 选取 Top-N 基金，生成等权 / 逆波动 / 混合权重
7. 落库到 `portfolio_results`
8. 导出 `scores_YYYY-MM-DD.csv`、`portfolio_fund_YYYY-MM-DD.csv`
9. 可从数据库直接回测，输出 `equity_curve.csv`

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
```

## 命令行运行

日跑主流程：

```bash
python run_daily_fund.py
```

回测：

```bash
python run_backtest_fund.py
```

GUI：

```bash
python gui/app.py
```

## 常用环境变量

| 变量 | 含义 | 默认值 |
|---|---|---|
| `FUND_DB_PATH` | SQLite 路径 | `db/fund_db.sqlite` |
| `FUND_OUTPUT_DIR` | 输出目录 | `output` |
| `FUND_UNIVERSE_CSV` | 基金池 CSV | `data/universe_fund.csv` |
| `FUND_UNIVERSE_LIMIT` | 基金池上限 | `100` |
| `FUND_TOP_N_FUNDS` | 选基数量 | `3` |
| `FUND_WINDOW_DAYS` | 因子窗口 | `252` |
| `FUND_SINCE_DATE` | 起始日期 | `2022-01-01` |
| `FUND_MIN_HISTORY_DAYS` | 最小历史天数 | `60` |
| `FUND_WEIGHT_SCHEME` | 回测权重列 | `weight_mixed` |
| `PARALLEL_WORKERS` | 抓取并发数 | `8` |

## 输出文件

- `output/scores_YYYY-MM-DD.csv`：当日横截面评分结果
- `output/portfolio_fund_YYYY-MM-DD.csv`：当日组合权重
- `output/equity_curve.csv`：回测净值曲线
- `output/reports/report_YYYY-MM-DD.html`：简易日报

## 这次重写重点修复的问题

- 入口脚本存在重复 import、职责不清、基金池逻辑分散
- SQLite 写入缺乏 numpy → Python 标量转换，`rank` 曾被写成二进制
- 组合构建与打分虽能跑通，但缺少系统化风险提示与日报输出
- 文档与依赖说明不完整，回测入口在 README 中出现但工程里缺失
