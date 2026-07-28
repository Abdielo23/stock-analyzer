"""Earnings analysis — beat-rate history, trends, guidance, and earnings-quality checks, all pulled from yfinance."""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

EARNINGS_HISTORY_QUARTERS = 8
ANNUAL_EPS_TAIL_YEARS = 4
YOY_QUARTERS_BACK = 4
REVENUE_TREND_QUARTERS = 8

# --- Earnings-quality bands ---
ACCRUALS_LOW_QUALITY_THRESHOLD = 0.1
ACCRUALS_HIGH_QUALITY_THRESHOLD = 0.05
SLOAN_HIGH_QUALITY_THRESHOLD = -0.1
SLOAN_LOW_QUALITY_THRESHOLD = 0.1

# --- Analyst consensus score bands (same weighting as sentiment.py) ---
CONSENSUS_STRONG_BUY_THRESHOLD = 4.2
CONSENSUS_BUY_THRESHOLD = 3.5
CONSENSUS_HOLD_THRESHOLD = 2.5

# --- Earnings-trend signal bands ---
STRONG_BEAT_RATE_THRESHOLD = 75
STRONG_BEAT_SURPRISE_THRESHOLD = 5
BEAT_RATE_THRESHOLD = 60
STRONG_MISS_RATE_THRESHOLD = 25
STRONG_MISS_SURPRISE_THRESHOLD = -5
MISS_RATE_THRESHOLD = 40

# --- Upcoming-earnings volatility risk bands (days until next report) ---
EARNINGS_RISK_HIGH_DAYS = 14
EARNINGS_RISK_MEDIUM_DAYS = 30


def _clean(value: object) -> Optional[float]:
    """Cast to float, collapsing None/NaN/Inf/unparseable values to None."""
    try:
        if value is None:
            return None
        value = float(value)
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    except (TypeError, ValueError):
        return None


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Period-over-period % change (already pre-multiplied, e.g. 10.0 = +10%)."""
    current, previous = _clean(current), _clean(previous)
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _first_valid(df, label: str) -> Optional[float]:
    """Scan a statement row left to right (most recent first) for the first non-null value."""
    try:
        row = df.loc[label]
    except (KeyError, AttributeError):
        return None
    for value in row:
        cleaned = _clean(value)
        if cleaned is not None:
            return cleaned
    return None


def _series_chronological(df, label: str) -> List[Optional[float]]:
    """Return a statement row as an oldest-to-newest list of clean floats."""
    try:
        row = df.loc[label]
    except (KeyError, AttributeError):
        return []
    values = [_clean(v) for v in row][::-1]
    return values


class EarningsAnalyzer:
    """Computes earnings history, trend, guidance, and quality for one ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        self._info = None

    @property
    def info(self) -> dict:
        """Lazily-fetched, cached ``yfinance`` info dict (``{}`` on failure)."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    def get_earnings_history(self) -> Dict:
        """EPS estimate vs. actual for recent quarters; revenue fields are always None since yfinance has no historical revenue-estimate feed."""
        empty = {
            "quarters": [], "eps_beat_rate": None, "revenue_beat_rate": None,
            "avg_eps_surprise_pct": None, "avg_revenue_surprise_pct": None,
        }

        try:
            dates = self._stock.earnings_dates
        except Exception:
            dates = None

        if dates is None or dates.empty:
            return empty

        reported = dates.dropna(subset=["Reported EPS"]).head(EARNINGS_HISTORY_QUARTERS)

        quarters = []
        beat_flags = []
        surprises = []
        for report_date, row in reported.iterrows():
            estimated_eps = _clean(row.get("EPS Estimate"))
            reported_eps = _clean(row.get("Reported EPS"))
            surprise_pct = _clean(row.get("Surprise(%)"))
            beat_eps = None
            if reported_eps is not None and estimated_eps is not None:
                beat_eps = reported_eps > estimated_eps
                beat_flags.append(beat_eps)
            if surprise_pct is not None:
                surprises.append(surprise_pct)

            quarters.append({
                "date": str(report_date.date()),
                "estimated_eps": estimated_eps,
                "reported_eps": reported_eps,
                "eps_surprise_pct": surprise_pct,
                "beat_eps": beat_eps,
                "estimated_revenue": None,
                "reported_revenue": None,
                "revenue_surprise_pct": None,
                "beat_revenue": None,
            })

        eps_beat_rate = _clean(sum(beat_flags) / len(beat_flags) * 100) if beat_flags else None
        avg_eps_surprise_pct = _clean(sum(surprises) / len(surprises)) if surprises else None

        return {
            "quarters": quarters,
            "eps_beat_rate": eps_beat_rate,
            "revenue_beat_rate": None,
            "avg_eps_surprise_pct": avg_eps_surprise_pct,
            "avg_revenue_surprise_pct": None,
        }

    def get_next_earnings(self) -> Dict:
        """Next earnings date plus EPS/revenue estimates; each yfinance call is wrapped separately since any one of them might be missing."""
        result = {
            "next_earnings_date": None, "days_until_earnings": None,
            "eps_estimate_current_quarter": None, "eps_estimate_next_quarter": None,
            "revenue_estimate_current_quarter": None, "revenue_estimate_next_quarter": None,
            "earnings_growth_estimate": None, "revenue_growth_estimate": None,
        }

        try:
            dates = self._stock.earnings_dates
            if dates is not None and not dates.empty:
                now = pd.Timestamp.now(tz=dates.index.tz)
                future = dates[dates.index > now].sort_index()
                if len(future):
                    next_date = future.index[0]
                    result["next_earnings_date"] = str(next_date.date())
                    result["days_until_earnings"] = (next_date.normalize() - now.normalize()).days
        except Exception:
            pass

        try:
            earnings_est = self._stock.earnings_estimate
            if earnings_est is not None and not earnings_est.empty:
                result["eps_estimate_current_quarter"] = _clean(earnings_est.loc["0q", "avg"]) if "0q" in earnings_est.index else None
                result["eps_estimate_next_quarter"] = _clean(earnings_est.loc["+1q", "avg"]) if "+1q" in earnings_est.index else None
                if "0y" in earnings_est.index:
                    growth = _clean(earnings_est.loc["0y", "growth"])
                    result["earnings_growth_estimate"] = growth * 100 if growth is not None else None
        except Exception:
            pass

        try:
            revenue_est = self._stock.revenue_estimate
            if revenue_est is not None and not revenue_est.empty:
                result["revenue_estimate_current_quarter"] = _clean(revenue_est.loc["0q", "avg"]) if "0q" in revenue_est.index else None
                result["revenue_estimate_next_quarter"] = _clean(revenue_est.loc["+1q", "avg"]) if "+1q" in revenue_est.index else None
                if "0y" in revenue_est.index:
                    growth = _clean(revenue_est.loc["0y", "growth"])
                    result["revenue_growth_estimate"] = growth * 100 if growth is not None else None
        except Exception:
            pass

        return result

    def get_earnings_trend(self) -> Dict:
        """Annual/quarterly EPS history plus QoQ/YoY growth and an acceleration signal."""
        result = {
            "annual_eps": [], "annual_eps_growth": [],
            "quarterly_eps": [], "quarterly_eps_growth": [],
            "eps_acceleration": None, "eps_trend": None,
        }

        try:
            annual = self._stock.income_stmt
            eps_values = [v for v in _series_chronological(annual, "Diluted EPS") if v is not None][-ANNUAL_EPS_TAIL_YEARS:]
            result["annual_eps"] = eps_values
            result["annual_eps_growth"] = [
                _pct_change(eps_values[i], eps_values[i - 1]) for i in range(1, len(eps_values))
            ]
        except Exception:
            pass

        try:
            quarterly = self._stock.quarterly_income_stmt
            q_eps = _series_chronological(quarterly, "Diluted EPS")
            result["quarterly_eps"] = q_eps

            qoq = [_pct_change(q_eps[i], q_eps[i - 1]) for i in range(1, len(q_eps))]
            yoy = [
                _pct_change(q_eps[i], q_eps[i - YOY_QUARTERS_BACK]) if i >= YOY_QUARTERS_BACK else None
                for i in range(len(q_eps))
            ]
            result["quarterly_eps_growth"] = [
                {"qoq_pct": qoq[i - 1] if i > 0 else None, "yoy_pct": yoy[i]}
                for i in range(len(q_eps))
            ]

            valid_qoq = [g for g in qoq if g is not None]
            if len(valid_qoq) >= 2:
                result["eps_acceleration"] = valid_qoq[-1] > valid_qoq[-2]
                if valid_qoq[-1] > valid_qoq[-2]:
                    result["eps_trend"] = "accelerating"
                elif valid_qoq[-1] < valid_qoq[-2]:
                    result["eps_trend"] = "decelerating"
                else:
                    result["eps_trend"] = "stable"
        except Exception:
            pass

        return result

    def get_revenue_trend(self) -> Dict:
        """Last `REVENUE_TREND_QUARTERS` quarters of revenue with QoQ/YoY growth."""
        result = {
            "quarters": [], "revenue_acceleration": None,
            "revenue_trend": None, "revenue_consistency": None,
        }

        try:
            quarterly = self._stock.quarterly_financials
            revenue = _series_chronological(quarterly, "Total Revenue")
            if not revenue:
                return result

            qoq = [_pct_change(revenue[i], revenue[i - 1]) for i in range(1, len(revenue))]
            yoy = [
                _pct_change(revenue[i], revenue[i - YOY_QUARTERS_BACK]) if i >= YOY_QUARTERS_BACK else None
                for i in range(len(revenue))
            ]

            quarters = []
            for i in range(len(revenue)):
                quarters.append({
                    "revenue": revenue[i],
                    "qoq_pct": qoq[i - 1] if i > 0 else None,
                    "yoy_pct": yoy[i],
                })
            result["quarters"] = quarters[-REVENUE_TREND_QUARTERS:]

            valid_qoq = [g for g in qoq if g is not None]
            if len(valid_qoq) >= 2:
                result["revenue_acceleration"] = valid_qoq[-1] > valid_qoq[-2]
                if valid_qoq[-1] > valid_qoq[-2]:
                    result["revenue_trend"] = "accelerating"
                elif valid_qoq[-1] < valid_qoq[-2]:
                    result["revenue_trend"] = "decelerating"
                else:
                    result["revenue_trend"] = "stable"

            valid_yoy = [g for g in yoy if g is not None]
            if valid_yoy:
                result["revenue_consistency"] = _clean(
                    sum(1 for g in valid_yoy if g > 0) / len(valid_yoy) * 100
                )
        except Exception:
            pass

        return result

    def get_guidance_analysis(self) -> Dict:
        """Forward EPS/P/E/PEG estimates, implied growth, and analyst consensus."""
        result = {
            "forward_estimates": {
                "forward_eps": None, "forward_pe": None, "peg_ratio": None,
                "earnings_growth_5y": None, "next_year_eps_estimate": None,
                "current_year_eps_estimate": None,
            },
            "implied_growth": None,
            "analyst_consensus": None,
        }

        info = self.info
        forward_eps = info.get("forwardEps")
        trailing_eps = info.get("trailingEps")

        result["forward_estimates"]["forward_eps"] = _clean(forward_eps)
        result["forward_estimates"]["forward_pe"] = _clean(info.get("forwardPE"))
        result["forward_estimates"]["peg_ratio"] = _clean(info.get("pegRatio") or info.get("trailingPegRatio"))

        try:
            growth_est = self._stock.growth_estimates
            if growth_est is not None and "LTG" in growth_est.index:
                ltg = _clean(growth_est.loc["LTG", "stockTrend"])
                result["forward_estimates"]["earnings_growth_5y"] = ltg * 100 if ltg is not None else None
        except Exception:
            pass

        try:
            earnings_est = self._stock.earnings_estimate
            if earnings_est is not None:
                if "+1y" in earnings_est.index:
                    result["forward_estimates"]["next_year_eps_estimate"] = _clean(earnings_est.loc["+1y", "avg"])
                if "0y" in earnings_est.index:
                    result["forward_estimates"]["current_year_eps_estimate"] = _clean(earnings_est.loc["0y", "avg"])
        except Exception:
            pass

        if forward_eps is not None and trailing_eps:
            result["implied_growth"] = _clean((forward_eps / trailing_eps - 1) * 100)

        try:
            rec = self._stock.recommendations
            if rec is not None and not rec.empty:
                current = rec[rec["period"] == "0m"]
                row = current.iloc[0] if len(current) else rec.iloc[0]
                breakdown = {
                    "strong_buy": int(row.get("strongBuy", 0)),
                    "buy": int(row.get("buy", 0)),
                    "hold": int(row.get("hold", 0)),
                    "sell": int(row.get("sell", 0)),
                    "strong_sell": int(row.get("strongSell", 0)),
                }
                weights = {"strong_buy": 5, "buy": 4, "hold": 3, "sell": 2, "strong_sell": 1}
                total = sum(breakdown.values())
                consensus_score = None
                consensus_label = None
                if total > 0:
                    consensus_score = _clean(sum(breakdown[k] * weights[k] for k in weights) / total)
                    if consensus_score > CONSENSUS_STRONG_BUY_THRESHOLD:
                        consensus_label = "Strong Buy"
                    elif consensus_score > CONSENSUS_BUY_THRESHOLD:
                        consensus_label = "Buy"
                    elif consensus_score > CONSENSUS_HOLD_THRESHOLD:
                        consensus_label = "Hold"
                    else:
                        consensus_label = "Sell"

                result["analyst_consensus"] = {
                    "breakdown": breakdown,
                    "consensus_score": consensus_score,
                    "consensus_label": consensus_label,
                }
        except Exception:
            pass

        return result

    def get_earnings_quality(self) -> Dict:
        """Accruals ratio (Sloan-style earnings quality) and a dilution warning — a large positive ratio means earnings lean more on accounting than cash."""
        result = {
            "accruals_ratio": None, "earnings_quality": None,
            "sloan_ratio": None, "sloan_signal": None,
            "dilution_warning": None,
        }

        try:
            financials = self._stock.income_stmt
            balance_sheet = self._stock.balance_sheet
            cashflow = self._stock.cashflow

            net_income = _first_valid(financials, "Net Income")
            operating_cf = _first_valid(cashflow, "Operating Cash Flow")
            investing_cf = _first_valid(cashflow, "Investing Cash Flow")

            assets_row = balance_sheet.loc["Total Assets"]
            total_assets_current = _clean(assets_row.iloc[0]) if len(assets_row) > 0 else None
            total_assets_previous = _clean(assets_row.iloc[1]) if len(assets_row) > 1 else None
            avg_total_assets = (
                (total_assets_current + total_assets_previous) / 2
                if total_assets_current is not None and total_assets_previous is not None
                else total_assets_current
            )

            if net_income is not None and operating_cf is not None and total_assets_current:
                accruals_ratio = (net_income - operating_cf) / total_assets_current
                result["accruals_ratio"] = _clean(accruals_ratio)
                if accruals_ratio > ACCRUALS_LOW_QUALITY_THRESHOLD:
                    result["earnings_quality"] = "low"
                elif accruals_ratio < ACCRUALS_HIGH_QUALITY_THRESHOLD:
                    result["earnings_quality"] = "high"
                else:
                    result["earnings_quality"] = "medium"

            if (
                net_income is not None and operating_cf is not None
                and investing_cf is not None and avg_total_assets
            ):
                sloan_ratio = (net_income - operating_cf - investing_cf) / avg_total_assets
                result["sloan_ratio"] = _clean(sloan_ratio)
                if sloan_ratio < SLOAN_HIGH_QUALITY_THRESHOLD:
                    result["sloan_signal"] = "high_quality"
                elif sloan_ratio > SLOAN_LOW_QUALITY_THRESHOLD:
                    result["sloan_signal"] = "low_quality"
                else:
                    result["sloan_signal"] = "medium_quality"

            shares = [v for v in _series_chronological(financials, "Diluted Average Shares") if v is not None]
            revenue = [v for v in _series_chronological(financials, "Total Revenue") if v is not None]
            if len(shares) >= 2 and len(revenue) >= 2:
                shares_growth = _pct_change(shares[-1], shares[-2])
                revenue_growth = _pct_change(revenue[-1], revenue[-2])
                if shares_growth is not None and revenue_growth is not None:
                    result["dilution_warning"] = shares_growth > 0 and shares_growth > revenue_growth
        except Exception:
            pass

        return result

    def _earnings_signal(self, eps_beat_rate: Optional[float], avg_eps_surprise: Optional[float]) -> str:
        """Classify the EPS beat-rate/surprise history into a beat/miss trend label."""
        if eps_beat_rate is None:
            return "mixed"
        if eps_beat_rate > STRONG_BEAT_RATE_THRESHOLD and avg_eps_surprise is not None and avg_eps_surprise > STRONG_BEAT_SURPRISE_THRESHOLD:
            return "strong_beat_trend"
        if eps_beat_rate > BEAT_RATE_THRESHOLD:
            return "beat_trend"
        if eps_beat_rate < STRONG_MISS_RATE_THRESHOLD and avg_eps_surprise is not None and avg_eps_surprise < STRONG_MISS_SURPRISE_THRESHOLD:
            return "strong_miss_trend"
        if eps_beat_rate < MISS_RATE_THRESHOLD:
            return "miss_trend"
        return "mixed"

    def _upcoming_earnings_risk(self, days_until: Optional[int]) -> str:
        """Classify volatility risk from an upcoming earnings report by days remaining."""
        if days_until is None:
            return "low"
        if days_until < EARNINGS_RISK_HIGH_DAYS:
            return "high"
        if days_until < EARNINGS_RISK_MEDIUM_DAYS:
            return "medium"
        return "low"

    def get_full_earnings_analysis(self) -> Dict:
        """Aggregates all earnings sub-analyses; each one is wrapped separately so one failing data source doesn't break the rest."""
        try:
            history = self.get_earnings_history()
        except Exception:
            history = None

        try:
            next_earnings = self.get_next_earnings()
        except Exception:
            next_earnings = None

        try:
            eps_trend = self.get_earnings_trend()
        except Exception:
            eps_trend = None

        try:
            revenue_trend = self.get_revenue_trend()
        except Exception:
            revenue_trend = None

        try:
            guidance = self.get_guidance_analysis()
        except Exception:
            guidance = None

        try:
            earnings_quality = self.get_earnings_quality()
        except Exception:
            earnings_quality = None

        eps_beat_rate = history.get("eps_beat_rate") if history else None
        avg_eps_surprise = history.get("avg_eps_surprise_pct") if history else None
        days_until = next_earnings.get("days_until_earnings") if next_earnings else None

        return {
            "ticker": self.ticker,
            "history": history,
            "next_earnings": next_earnings,
            "eps_trend": eps_trend,
            "revenue_trend": revenue_trend,
            "guidance": guidance,
            "earnings_quality": earnings_quality,
            "earnings_signal": self._earnings_signal(eps_beat_rate, avg_eps_surprise),
            "upcoming_earnings_risk": self._upcoming_earnings_risk(days_until),
        }
