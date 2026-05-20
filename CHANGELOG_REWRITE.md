# 重写说明与验收结论（第二轮升级版）

## 本轮新增升级

### 1. GUI 按工程化方式重构
- 旧版 `gui/widgets/MainWindow.py` 过于脚本式，已改成兼容包装层
- 新增 `gui/widgets/main_window_v2.py`
- 新增 `gui/models.py`、`gui/services.py`
- GUI 现在按“参数面板 / 结果面板 / 报告面板”拆分，支持：
  - 运行参数配置
  - 约束优化参数配置
  - 基金池生成
  - 评分/权重/交易表格展示
  - 研究报告预览

### 2. 优化器升级为真正的约束优化
- `src/optimizer.py` 从“等权 / 逆波动 / 混合权重”升级为：
  - 候选基金筛选
  - 协方差矩阵估计（优先 Ledoit-Wolf shrinkage）
  - 预期收益估计（历史收益 + score tilt）
  - SLSQP 约束优化
- 约束包括：
  - 全投资约束 `sum(w)=1`
  - 单基金上下限约束
  - 可选目标波动约束
  - 锚点/换手惩罚
  - L2 正则
- 新增输出列：
  - `weight_optimized`
  - `expected_return_ann`
  - `expected_vol_ann`
  - `marginal_risk`
  - `risk_contribution`
  - `risk_contribution_pct`
  - `optimizer_status`

### 3. 报告层升级为正式研究输出
- `src/reporting.py` 重写为研究型报告生成器
- 现在自动产出：
  - HTML 报告
  - Markdown 报告
  - JSON 摘要
  - 图表资产目录
- 新报告包含：
  - Executive summary
  - Score diagnostics
  - Portfolio construction
  - Backtest evaluation
  - Risk review
  - Methodology
- 自动生成图表：
  - equity vs benchmark
  - weights
  - risk contribution
  - top scores

### 4. 历史回填真正落地
- 旧版 `pipeline.py` 想调用 `backfill`，但原模块里并没有该函数
- 现已补齐 `src/backfill_portfolio.py::backfill()`
- 可按最近 N 个交易日重建历史组合，供回测与报告使用

### 5. DAO 与依赖同步升级
- `src/dao.py` 现在会对新字段自动补列 `ALTER TABLE`
- `requirements.txt` 新增：
  - `scipy`
  - `scikit-learn`

### 6. 新增整体验收脚本
- 新增 `validate_project.py`
- 可做一键验证：
  - 主流程
  - 回测
  - 数据库 schema
  - 输出文件
  - GUI（若无 PySide6，则退回语法级 smoke test）

## 验收结果

### 已完成并实际跑通
- `python run_daily_fund.py`
- `FUND_BACKFILL_DAYS=20 python run_daily_fund.py`
- `python run_backtest_fund.py`
- `python validate_project.py`
- `python -m compileall src gui run_daily_fund.py run_backtest_fund.py validate_project.py`

### 本轮验证通过的关键点
- 主流程可跑通
- 评分、组合、报告均能生成
- 历史回填可执行
- 回测输出含 `equity` 与 `benchmark`
- `portfolio_results` 已含优化器相关字段
- GUI 新源码通过语法级校验

## 当前已知限制

1. 当前容器环境未安装 `PySide6`，因此无法在本次验收中完成真实 GUI 窗口级实例化，只能完成源码与结构级 smoke test
2. 优化器仍属于研究型工程实现，不是带完整交易成本模型和行业/风格暴露约束的机构级优化器
3. 报告已达到“正式研究输出”层级，但还不是论文排版级 PDF 模板

## 项目经理视角结论

这轮之后，项目已经不再只是“能跑的基金池脚本”，而是具备了：
- **可维护 GUI**
- **可解释的约束优化器**
- **可交付的研究报告层**
- **可复验的整体验收脚本**

如果按完成度评估：
- **主流程**：通过
- **优化器**：通过，且明显提升
- **报告层**：通过，已达到研究输出形态
- **GUI 架构**：通过，但真实桌面端交互仍建议在装好 PySide6 的本机再做最终体验验收
