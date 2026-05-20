# -*- coding: utf-8 -*-
"""GUI worker: bridge GUI config -> environment -> pipeline -> artifacts."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
import os
import sqlite3
import sys
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from PySide6.QtCore import QThread, Signal


class RunStrategyWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    stage = Signal(str, int)
    artifacts = Signal(dict)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.params = params or {}
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        digest = hashlib.md5(json.dumps(self.params, sort_keys=True).encode()).hexdigest()[:8]
        self.run_id = f"run_{ts}_{digest}"
        self.project_root = self._guess_project_root()
        self.art_dir = os.path.join(self.project_root, "gui", "artifacts", self.run_id)
        os.makedirs(self.art_dir, exist_ok=True)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._emit_stage("prepare", 5, "[STEP 0] 初始化任务")
            self._apply_env()
            self._preflight_universe_csv()

            self._emit_stage("pipeline", 25, "[STEP 1] 执行日度主流程")
            result = self._call_run_daily()
            if self._stop:
                return

            self._emit_stage("backtest", 70, "[STEP 2] 回测并生成收益曲线")
            eq_csv, eq_png = self._gen_equity_curve()

            self._emit_stage("harvest", 85, "[STEP 3] 导出权重、交易与研究报告")
            weights_csv, trades_csv = self._export_weights_and_trades()
            payload = {
                "run_id": self.run_id,
                "equity_curve_csv": eq_csv,
                "equity_curve_png": eq_png,
                "weights_csv": weights_csv,
                "trades_csv": trades_csv,
                "scores_csv": str(getattr(result, "score_path", "") or ""),
                "report_html": str(getattr(result, "report_path", "") or ""),
                "report_md": self._neighbor_report_path(getattr(result, "report_path", None), ".md"),
                "report_json": self._neighbor_report_path(getattr(result, "report_path", None), ".json"),
                "params_json": self._dump_params_json(),
            }
            self.artifacts.emit(payload)

            metrics = self._metrics_from_equity(eq_csv)
            self._emit_stage("done", 100, "[DONE] 任务完成")
            self.done.emit({"run_id": self.run_id, **metrics})
        except Exception as exc:
            self.failed.emit(str(exc))

    def _preflight_universe_csv(self):
        csv_path = os.getenv("FUND_UNIVERSE_CSV", "")
        try:
            dfu = pd.read_csv(csv_path, dtype={"fund_code": str})
            dfu["fund_code"] = dfu["fund_code"].astype(str).str.zfill(6)
            self.log.emit(f"[CHECK] 基金池CSV实际行数={len(dfu)}，样例={dfu['fund_code'].head(5).tolist()}")
        except Exception as exc:
            self.log.emit(f"[CHECK][WARN] 无法读取基金池CSV：{csv_path} -> {exc}")

    def _apply_env(self):
        def ap(p: str):
            return os.path.abspath(os.path.join(self.project_root, p)) if p and not os.path.isabs(p) else p

        p = self.params
        env = {
            "FUND_SINCE_DATE": p.get("since", "2022-01-01"),
            "FUND_UNIVERSE_CSV": ap(p.get("universe_csv", "data/universe_fund.csv")),
            "PARALLEL_WORKERS": str(p.get("workers", max(8, os.cpu_count() or 8))),
            "FUND_TOP_N_FUNDS": str(p.get("top_n", 5)),
            "FUND_WINDOW_DAYS": str(p.get("window_days", 252)),
            "FUND_UNIVERSE_LIMIT": str(p.get("universe_limit", 100)),
            "FUND_WEIGHT_SCHEME": p.get("weight_scheme", "weight_optimized"),
            "FUND_DB_PATH": ap(os.path.join("db", "fund_db.sqlite")),
            "FUND_OUTPUT_DIR": ap("output"),
            "FUND_BACKFILL_DAYS": str(p.get("backfill_days", 126)),
            "FUND_MAX_WEIGHT": str(p.get("max_weight", 0.45)),
            "FUND_MIN_WEIGHT": str(p.get("min_weight", 0.0)),
            "FUND_OPT_RISK_AVERSION": str(p.get("risk_aversion", 4.0)),
            "FUND_OPT_SCORE_TILT": str(p.get("score_tilt", 0.03)),
            "FUND_OPT_TURNOVER_PENALTY": str(p.get("turnover_penalty", 0.15)),
            "FUND_OPT_L2_PENALTY": str(p.get("l2_penalty", 0.01)),
            "FUND_OPT_TARGET_VOL": str(p.get("target_vol", 0.0)),
            "FUND_OPT_COV_LOOKBACK": str(p.get("cov_lookback", 126)),
        }
        for k, v in env.items():
            os.environ[k] = str(v)
            self.log.emit(f"[ENV] {k}={v}")

    def _call_run_daily(self):
        for name in list(sys.modules.keys()):
            if name.startswith("src.") or name in ("src", "run_daily_fund"):
                sys.modules.pop(name, None)
        sys.path.insert(0, self.project_root)
        mod = importlib.import_module("run_daily_fund")
        if not hasattr(mod, "main"):
            raise RuntimeError("run_daily_fund.main 未找到")
        self.log.emit(">>> 执行 run_daily_fund.main()")
        result = mod.main()
        self.log.emit("<<< 结束 run_daily_fund.main()")
        return result

    def _gen_equity_curve(self) -> Tuple[str, str]:
        for name in list(sys.modules.keys()):
            if name.startswith("src.") or name == "src":
                sys.modules.pop(name, None)
        sys.path.insert(0, self.project_root)

        weight_col = os.getenv("FUND_WEIGHT_SCHEME", "weight_optimized")
        self.log.emit(f"[BT] 使用权重列：{weight_col}")

        df_nav = None
        try:
            bqf = importlib.import_module("src.backtest_quick_fund")
            df_nav = bqf.backtest_from_db(weight_col=weight_col)
        except Exception as exc:
            self.log.emit(f"[BT][WARN] backtest_from_db 异常：{exc}")

        if df_nav is None or df_nav.empty:
            out_dir = os.getenv("FUND_OUTPUT_DIR", os.path.join(self.project_root, "output"))
            csv_path = os.path.join(out_dir, "backtest_fund_nav.csv")
            if os.path.exists(csv_path):
                try:
                    df_nav = pd.read_csv(csv_path)
                    self.log.emit(f"[BT] 回读导出的曲线：{csv_path} rows={len(df_nav)}")
                except Exception as exc:
                    self.log.emit(f"[BT][WARN] 读取导出曲线失败：{exc}")

        if df_nav is None or df_nav.empty or len(df_nav) < 2:
            self.log.emit("[BT][WARN] backtest_from_db 结果不足，启用静态持仓兜底。")
            df_nav = self._equity_from_static_weights(weight_col)
            if df_nav is None or df_nav.empty:
                raise RuntimeError("无法生成收益曲线：backtest 与兜底都为空。")

        df = df_nav.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        eq_csv = os.path.join(self.art_dir, "equity_curve.csv")
        df.to_csv(eq_csv, index=False, encoding="utf-8-sig")

        fig = Figure(figsize=(6.4, 3.0), dpi=160)
        ax = fig.add_subplot(111)
        ax.plot(df["date"], pd.to_numeric(df.get("equity"), errors="coerce"), label="Strategy")
        if "benchmark" in df.columns:
            ax.plot(df["date"], pd.to_numeric(df.get("benchmark"), errors="coerce"), label="Benchmark")
            ax.legend()
        ax.set_title("Equity Curve")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        eq_png = os.path.join(self.art_dir, "equity_curve.png")
        fig.savefig(eq_png, bbox_inches="tight")
        return eq_csv, eq_png

    def _equity_from_static_weights(self, weight_col: str) -> Optional[pd.DataFrame]:
        db_path = os.getenv("FUND_DB_PATH", os.path.join(self.project_root, "db", "fund_db.sqlite"))
        if not os.path.exists(db_path):
            self.log.emit(f"[BT][ERR] DB 不存在：{db_path}")
            return None
        con = sqlite3.connect(db_path)
        try:
            dts = pd.read_sql_query("SELECT DISTINCT date FROM portfolio_results ORDER BY date DESC LIMIT 1", con)
            if dts.empty:
                return None
            last_date = dts["date"].iloc[0]
            w = pd.read_sql_query(
                f"SELECT fund_code, {weight_col} AS weight FROM portfolio_results WHERE date=?",
                con,
                params=[last_date],
            )
            if w.empty:
                return None
            w["weight"] = pd.to_numeric(w["weight"], errors="coerce").fillna(0.0)
            w = w.loc[w["weight"] != 0.0].set_index("fund_code")["weight"]

            nav = pd.read_sql_query("SELECT fund_code AS code, date, nav FROM fund_nav_daily", con)
            if nav.empty:
                return None
            nav["date"] = pd.to_datetime(nav["date"], errors="coerce")
            nav["code"] = nav["code"].astype(str).str.zfill(6)
            nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
            nav = nav.dropna(subset=["date", "nav"])
            nav = nav.loc[nav["code"].isin(w.index)].sort_values(["code", "date"])
            if nav.empty:
                return None
            nav["norm"] = nav.groupby("code")["nav"].transform(lambda s: s / (s.iloc[0] if len(s) else 1.0))
            nav = nav.join(w.rename("weight"), on="code")
            nav["contrib"] = nav["norm"] * nav["weight"]
            df = nav.groupby("date")["contrib"].sum().reset_index().rename(columns={"contrib": "equity"})
            if not df.empty:
                base = df["equity"].iloc[0]
                if base != 0:
                    df["equity"] = df["equity"] / base
            return df
        finally:
            con.close()

    def _export_weights_and_trades(self) -> Tuple[Optional[str], Optional[str]]:
        db_path = os.getenv("FUND_DB_PATH", os.path.join(self.project_root, "db", "fund_db.sqlite"))
        if not os.path.exists(db_path):
            self.log.emit(f"[WARN] 数据库不存在：{db_path}")
            return None, None
        con = sqlite3.connect(db_path)
        try:
            dates = pd.read_sql_query("SELECT DISTINCT date FROM portfolio_results ORDER BY date DESC LIMIT 2", con)
            if dates.empty:
                return None, None
            last_date = dates["date"].iloc[0]
            prev_date = dates["date"].iloc[1] if len(dates) > 1 else None
            weight_col = os.getenv("FUND_WEIGHT_SCHEME", "weight_optimized")
            df_last = pd.read_sql_query(
                f"SELECT date, fund_code, {weight_col} AS weight, score, rank, risk_contribution_pct FROM portfolio_results WHERE date=? ORDER BY weight DESC",
                con,
                params=[last_date],
            )
            weights_csv = os.path.join(self.art_dir, "weights.csv")
            df_last.to_csv(weights_csv, index=False, encoding="utf-8-sig")

            trades_csv = None
            if prev_date is not None:
                df_prev = pd.read_sql_query(
                    f"SELECT fund_code, {weight_col} AS weight FROM portfolio_results WHERE date=?",
                    con,
                    params=[prev_date],
                )
                m = (
                    df_last.set_index("fund_code")["weight"].rename("w1").to_frame()
                    .join(df_prev.set_index("fund_code")["weight"].rename("w0"), how="outer")
                    .fillna(0.0)
                )
                m["delta"] = m["w1"] - m["w0"]
                m = m.loc[m["delta"].abs() > 1e-8].sort_values("delta", ascending=False)
                out = m.reset_index().rename(columns={"index": "fund_code"})
                out["date"] = last_date
                out["action"] = out["delta"].apply(lambda x: "BUY" if x > 0 else "SELL")
                trades_csv = os.path.join(self.art_dir, "trades.csv")
                out[["date", "fund_code", "action", "delta"]].to_csv(trades_csv, index=False, encoding="utf-8-sig")
            return weights_csv, trades_csv
        finally:
            con.close()

    def _metrics_from_equity(self, eq_csv: str) -> Dict[str, float]:
        try:
            df = pd.read_csv(eq_csv)
            equity = pd.to_numeric(df.get("equity", df.iloc[:, 1]), errors="coerce").dropna()
            if len(equity) < 3:
                return {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "vol": 0.0}
            rets = equity.pct_change().dropna()
            vol = float(rets.std(ddof=0) * np.sqrt(252))
            sharpe = float((rets.mean() * 252) / (vol + 1e-12))
            cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (252 / max(len(equity) - 1, 1)) - 1.0)
            mdd = float((equity / equity.cummax() - 1.0).min())
            return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": mdd, "vol": vol}
        except Exception:
            return {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "vol": 0.0}

    def _dump_params_json(self) -> str:
        path = os.path.join(self.art_dir, "params.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"run_id": self.run_id, **self.params}, f, ensure_ascii=False, indent=2)
        return path

    def _neighbor_report_path(self, report_html_path, suffix: str) -> str:
        if not report_html_path:
            return ""
        p = os.fspath(report_html_path)
        stem, _ = os.path.splitext(p)
        neighbor = stem + suffix
        return neighbor if os.path.exists(neighbor) else ""

    def _guess_project_root(self) -> str:
        here = os.path.abspath(os.path.dirname(__file__))
        return os.path.abspath(os.path.join(here, "..", ".."))

    def _emit_stage(self, name: str, pct: int, msg: str):
        self.stage.emit(name, int(pct))
        self.progress.emit(int(pct))
        self.log.emit(msg)
