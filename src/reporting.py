from __future__ import annotations

import html
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .backtest_quick_fund import backtest_from_db
from .config import C

TRADING_DAYS = 252


def _safe_float(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except Exception:
        return default


def _portfolio_snapshot(df_port: pd.DataFrame) -> dict:
    if df_port is None or df_port.empty:
        return {}
    weight_col = "weight_optimized" if "weight_optimized" in df_port.columns else "weight_mixed"
    if weight_col not in df_port.columns:
        return {}
    w = pd.to_numeric(df_port[weight_col], errors="coerce").dropna()
    if w.empty:
        return {}
    hhi = float((w ** 2).sum())
    eff_n = float(1.0 / hhi) if hhi > 0 else float("nan")
    return {
        "weight_column": weight_col,
        "n_holdings": int(len(w)),
        "top_weight": float(w.max()),
        "min_weight": float(w.min()),
        "weight_sum": float(w.sum()),
        "hhi": hhi,
        "effective_n": eff_n,
    }


def _score_snapshot(df_scores: pd.DataFrame) -> dict:
    if df_scores is None or df_scores.empty or "score" not in df_scores.columns:
        return {}
    score = pd.to_numeric(df_scores["score"], errors="coerce").dropna()
    if score.empty:
        return {}
    return {
        "n_scored": int(len(score)),
        "score_mean": float(score.mean()),
        "score_std": float(score.std(ddof=0)),
        "score_p10": float(score.quantile(0.10)),
        "score_p50": float(score.quantile(0.50)),
        "score_p90": float(score.quantile(0.90)),
    }


def _performance_metrics(df_curve: pd.DataFrame) -> dict:
    if df_curve is None or df_curve.empty or "equity" not in df_curve.columns:
        return {}
    eq = pd.to_numeric(df_curve["equity"], errors="coerce").dropna()
    if len(eq) < 2:
        return {}
    ret = eq.pct_change().dropna()
    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (TRADING_DAYS / max(len(eq) - 1, 1)) - 1.0)
    vol = float(ret.std(ddof=0) * np.sqrt(TRADING_DAYS)) if len(ret) else 0.0
    sharpe = float((ret.mean() * TRADING_DAYS) / (vol + 1e-12)) if len(ret) else 0.0
    mdd = float((eq / eq.cummax() - 1.0).min())

    out = {
        "n_days": int(len(eq)),
        "total_return": total_return,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "max_drawdown": mdd,
    }

    if "benchmark" in df_curve.columns:
        bm = pd.to_numeric(df_curve["benchmark"], errors="coerce").dropna()
        if len(bm) == len(eq) and len(bm) > 1:
            bm_ret = bm.pct_change().dropna()
            excess = ret - bm_ret
            out["benchmark_total_return"] = float(bm.iloc[-1] / bm.iloc[0] - 1.0)
            out["tracking_error"] = float(excess.std(ddof=0) * np.sqrt(TRADING_DAYS)) if len(excess) else 0.0
            out["information_ratio"] = float((excess.mean() * TRADING_DAYS) / (out["tracking_error"] + 1e-12)) if len(excess) else 0.0
    return out


def _save_equity_chart(df_curve: pd.DataFrame, out_dir: Path, stem: str) -> Path | None:
    if df_curve is None or df_curve.empty:
        return None
    fig_path = out_dir / f"{stem}_equity.png"
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=160)
    x = pd.to_datetime(df_curve["date"], errors="coerce")
    ax.plot(x, pd.to_numeric(df_curve["equity"], errors="coerce"), label="Strategy")
    if "benchmark" in df_curve.columns:
        ax.plot(x, pd.to_numeric(df_curve["benchmark"], errors="coerce"), label="Benchmark")
        ax.legend()
    ax.set_title("Backtest Equity Curve")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)
    return fig_path


def _save_weights_chart(df_port: pd.DataFrame, out_dir: Path, stem: str) -> Path | None:
    if df_port is None or df_port.empty:
        return None
    weight_col = "weight_optimized" if "weight_optimized" in df_port.columns else "weight_mixed"
    if weight_col not in df_port.columns:
        return None
    chart = df_port[["fund_code", weight_col]].copy()
    chart[weight_col] = pd.to_numeric(chart[weight_col], errors="coerce")
    chart = chart.dropna().sort_values(weight_col, ascending=True)
    if chart.empty:
        return None
    fig_path = out_dir / f"{stem}_weights.png"
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    ax.barh(chart["fund_code"].astype(str), chart[weight_col])
    ax.set_title(f"Portfolio Weights ({weight_col})")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)
    return fig_path


def _save_risk_chart(df_port: pd.DataFrame, out_dir: Path, stem: str) -> Path | None:
    if df_port is None or df_port.empty or "risk_contribution_pct" not in df_port.columns:
        return None
    chart = df_port[["fund_code", "risk_contribution_pct"]].copy()
    chart["risk_contribution_pct"] = pd.to_numeric(chart["risk_contribution_pct"], errors="coerce")
    chart = chart.dropna().sort_values("risk_contribution_pct", ascending=True)
    if chart.empty:
        return None
    fig_path = out_dir / f"{stem}_risk_contrib.png"
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    ax.barh(chart["fund_code"].astype(str), chart["risk_contribution_pct"])
    ax.set_title("Risk Contribution Share")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)
    return fig_path


def _save_score_chart(df_scores: pd.DataFrame, out_dir: Path, stem: str) -> Path | None:
    if df_scores is None or df_scores.empty or "score" not in df_scores.columns:
        return None
    chart = df_scores[["fund_code", "score"]].copy().head(10)
    chart["score"] = pd.to_numeric(chart["score"], errors="coerce")
    chart = chart.dropna().sort_values("score", ascending=True)
    if chart.empty:
        return None
    fig_path = out_dir / f"{stem}_scores.png"
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=160)
    ax.barh(chart["fund_code"].astype(str), chart["score"])
    ax.set_title("Top Cross-sectional Scores")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)
    return fig_path


def _fmt_pct(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):.2%}"


def _fmt_num(v: float | None, ndigits: int = 4) -> str:
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):.{ndigits}f}"


def _table_html(df: pd.DataFrame | None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "<p>No data.</p>"
    show = df.head(max_rows).copy()
    return show.to_html(index=False, border=0, classes="tbl")


def _table_md(df: pd.DataFrame | None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "No data."
    show = df.head(max_rows).copy()
    try:
        return show.to_markdown(index=False)
    except Exception:
        return show.to_csv(index=False)


def _img_tag(path: Path | None) -> str:
    if path is None:
        return ""
    return f'<div class="figure"><img src="{html.escape(path.name)}" alt="{html.escape(path.stem)}"></div>'


def generate_daily_report(
    date_str: str,
    df_scores: pd.DataFrame,
    df_port: pd.DataFrame,
    risk_warnings: list[str] | None,
    out_dir: Path,
    *,
    universe: list[str] | None = None,
    df_factors: pd.DataFrame | None = None,
    df_ret: pd.DataFrame | None = None,
    weight_col: str | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"report_{date_str}"
    asset_dir = out_dir / f"{stem}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    score_stats = _score_snapshot(df_scores)
    port_stats = _portfolio_snapshot(df_port)

    try:
        curve = backtest_from_db(weight_col=weight_col or C.WEIGHT_SCHEME, out_dir=C.OUTPUT_DIR, since_date=C.SINCE_DATE)
    except Exception:
        curve = pd.DataFrame(columns=["date", "equity", "benchmark"])
    perf_stats = _performance_metrics(curve)

    fig_equity = _save_equity_chart(curve, asset_dir, stem)
    fig_weights = _save_weights_chart(df_port, asset_dir, stem)
    fig_risk = _save_risk_chart(df_port, asset_dir, stem)
    fig_scores = _save_score_chart(df_scores, asset_dir, stem)

    top_port = None if df_port is None else df_port.sort_values("weight_optimized" if "weight_optimized" in df_port.columns else "weight_mixed", ascending=False)
    top_scores = None if df_scores is None else df_scores.sort_values("score", ascending=False)

    findings = []
    if top_port is not None and not top_port.empty:
        weight_col_eff = "weight_optimized" if "weight_optimized" in top_port.columns else "weight_mixed"
        lead = top_port.iloc[0]
        findings.append(f"Top holding: {lead['fund_code']} at {_fmt_pct(lead[weight_col_eff])}.")
    if perf_stats:
        findings.append(
            f"Backtest window: {perf_stats.get('n_days', 0)} days, CAGR {_fmt_pct(perf_stats.get('cagr'))}, "
            f"Sharpe {_fmt_num(perf_stats.get('sharpe'), 2)}, MaxDD {_fmt_pct(perf_stats.get('max_drawdown'))}."
        )
    if port_stats:
        findings.append(
            f"Portfolio concentration: effective N {_fmt_num(port_stats.get('effective_n'), 2)} with top weight {_fmt_pct(port_stats.get('top_weight'))}."
        )
    if risk_warnings:
        findings.extend(risk_warnings[:3])

    summary_payload = {
        "report_date": date_str,
        "title": C.report_title,
        "universe_size": len(universe or []),
        "score_stats": score_stats,
        "portfolio_stats": port_stats,
        "performance_stats": perf_stats,
        "risk_warnings": risk_warnings or [],
        "weight_scheme": weight_col or C.WEIGHT_SCHEME,
    }
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    methodology_md = (
        "1. Universe construction: use the configured fund universe and retained funds with sufficient NAV history.\n"
        "2. Factor model: annual return, annualized volatility, downside volatility, max drawdown, Sharpe, and IR are robustly standardized.\n"
        "3. Optimization: solve a constrained mean-variance problem under full-investment and box constraints, with shrinkage covariance and anchor penalty.\n"
        "4. Validation: export portfolio weights, risk contribution, score table, backtest equity curve, and benchmark comparison."
    )

    md_parts = [
        f"# {C.report_title}",
        f"**Report date:** {date_str}",
        "",
        "## Executive summary",
    ]
    md_parts.extend([f"- {item}" for item in findings] if findings else ["- No finding available."])
    md_parts.extend([
        "",
        "## Data and scope",
        f"- Universe size: {len(universe or [])}",
        f"- Since date: {C.since_date}",
        f"- Factor window: {C.window_days}",
        f"- Weight scheme: {weight_col or C.WEIGHT_SCHEME}",
        "",
        "## Score diagnostics",
        _table_md(pd.DataFrame([score_stats])) if score_stats else "No score statistics.",
        "",
        _table_md(top_scores[[c for c in ["fund_code", "score", "rank", "ann_return", "ann_vol", "sharpe", "ir"] if c in top_scores.columns]], 15) if top_scores is not None and not top_scores.empty else "No score table.",
        "",
        "## Portfolio construction",
        _table_md(pd.DataFrame([port_stats])) if port_stats else "No portfolio snapshot.",
        "",
        _table_md(top_port[[c for c in ["fund_code", "weight_optimized", "weight_mixed", "weight_risk_parity", "weight_equal", "score", "rank", "risk_contribution_pct"] if c in top_port.columns]], 15) if top_port is not None and not top_port.empty else "No holdings table.",
        "",
        "## Backtest evaluation",
        _table_md(pd.DataFrame([perf_stats])) if perf_stats else "No performance statistics.",
        "",
        "## Risk review",
    ])
    md_parts.extend([f"- {item}" for item in (risk_warnings or [])] if risk_warnings else ["- No explicit warnings."])
    md_parts.extend([
        "",
        "## Methodology",
        methodology_md,
    ])
    md_path = out_dir / f"{stem}.md"
    md_path.write_text("\n".join(md_parts), encoding="utf-8")

    html_parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(C.report_title)} - {html.escape(date_str)}</title>",
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:36px;line-height:1.6;color:#1f2937;}",
        "h1,h2,h3{color:#111827;} .muted{color:#6b7280;} .grid{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:18px;}",
        ".card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;background:#fff;} .tbl{border-collapse:collapse;width:100%;font-size:14px;}",
        ".tbl th,.tbl td{border:1px solid #e5e7eb;padding:6px 8px;text-align:right;} .tbl th:first-child,.tbl td:first-child{text-align:left;}",
        ".figure img{max-width:100%;border:1px solid #e5e7eb;border-radius:10px;} ul{padding-left:20px;}",
        "</style></head><body>",
        f"<h1>{html.escape(C.report_title)}</h1>",
        f"<p class='muted'>Report date: {html.escape(date_str)} | Weight scheme: {html.escape(weight_col or C.WEIGHT_SCHEME)}</p>",
        "<h2>Executive summary</h2>",
        "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in (findings or ["No finding available."])) + "</ul>",
        "<div class='grid'>",
        f"<div class='card'><h3>Score snapshot</h3>{_table_html(pd.DataFrame([score_stats])) if score_stats else '<p>No score statistics.</p>'}</div>",
        f"<div class='card'><h3>Portfolio snapshot</h3>{_table_html(pd.DataFrame([port_stats])) if port_stats else '<p>No portfolio statistics.</p>'}</div>",
        "</div>",
        "<h2>Research charts</h2>",
        _img_tag(fig_equity),
        _img_tag(fig_weights),
        _img_tag(fig_risk),
        _img_tag(fig_scores),
        "<h2>Score diagnostics</h2>",
        _table_html(top_scores[[c for c in ["fund_code", "score", "rank", "ann_return", "ann_vol", "sharpe", "ir"] if c in top_scores.columns]], 15) if top_scores is not None and not top_scores.empty else "<p>No score table.</p>",
        "<h2>Portfolio construction</h2>",
        _table_html(top_port[[c for c in ["fund_code", "weight_optimized", "weight_mixed", "weight_risk_parity", "weight_equal", "score", "rank", "risk_contribution_pct"] if c in top_port.columns]], 15) if top_port is not None and not top_port.empty else "<p>No holdings table.</p>",
        "<h2>Backtest evaluation</h2>",
        _table_html(pd.DataFrame([perf_stats])) if perf_stats else "<p>No performance statistics.</p>",
        "<h2>Risk review</h2>",
        "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in (risk_warnings or ["No explicit warnings."])) + "</ul>",
        "<h2>Methodology</h2>",
        "<ol>"
        "<li>Universe construction: use the configured fund universe and retain funds with sufficient NAV history.</li>"
        "<li>Factor model: annual return, annualized volatility, downside volatility, max drawdown, Sharpe, and IR are robustly standardized.</li>"
        "<li>Optimization: solve a constrained mean-variance problem under full-investment and box constraints, with shrinkage covariance and anchor penalty.</li>"
        "<li>Validation: export holdings, risk contribution, score table, backtest equity curve, and benchmark comparison.</li>"
        "</ol>",
        "</body></html>",
    ]
    html_path = out_dir / f"{stem}.html"
    html_path.write_text("\n".join(html_parts), encoding="utf-8")
    return html_path
