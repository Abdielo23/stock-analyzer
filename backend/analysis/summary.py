"""Master aggregator: pulls all 14 analyzer modules for one ticker into a plain-English
investment statement, an AI-analyst prompt, and a bull/bear score/verdict.

Takes 60-180 seconds since it calls all 14 modules one after another.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf

from analysis.fundamental import FundamentalAnalyzer
from analysis.valuation import ValuationAnalyzer
from analysis.technical import TechnicalAnalyzer
from analysis.volume import VolumeAnalyzer
from analysis.risk import RiskAnalyzer
from analysis.institutional import InstitutionalAnalyzer
from analysis.sentiment import SentimentAnalyzer
from analysis.earnings import EarningsAnalyzer
from analysis.quantitative import QuantitativeAnalyzer
from analysis.social import SocialSentimentAnalyzer
from analysis.geopolitical import GeopoliticalAnalyzer
from analysis.political import PoliticalAnalyzer
from analysis.macro import MacroAnalyzer
from analysis.calendar import EconomicCalendarAnalyzer

VERDICT_DESCRIPTIONS = {
    "STRONG BUY": "All major indicators align positively across fundamentals, valuation, technicals, risk, sentiment, and macro. High-conviction opportunity.",
    "BUY": "Strong weight of evidence is positive. More strengths than weaknesses across key metrics.",
    "WEAK BUY": "Moderately positive setup. Proceed with appropriate position sizing.",
    "LEAN BUY": "Moderately positive setup. Proceed with appropriate position sizing.",
    "HOLD": "Mixed signals. Current holders may maintain; new buyers should wait for clearer setup.",
    "LEAN SELL": "More red flags than green lights. Consider reducing exposure.",
    "WEAK SELL": "More red flags than green lights. Consider reducing exposure.",
    "SELL": "Multiple concerning signals. Risk/reward unfavorable.",
    "STRONG SELL": "Nearly all indicators negative. Avoid or exit.",
}

DISCLAIMER = (
    "DISCLAIMER: This analysis is generated automatically from public market "
    "data for educational purposes only. Not financial advice. Always do "
    "your own research."
)

# --- Score-breakdown verdict bands (score is the sum of 12 -2..+2 components) ---
VERDICT_STRONG_BUY_MIN = 7
VERDICT_BUY_MIN = 5
VERDICT_WEAK_BUY_MIN = 3
VERDICT_LEAN_BUY_MIN = 1
VERDICT_HOLD = 0
VERDICT_LEAN_SELL_MIN = -2
VERDICT_WEAK_SELL_MIN = -4
VERDICT_SELL_MIN = -6

# --- Individual score-component thresholds (each contributes -2..+2 to the total) ---
HEALTH_SCORE_STRONG_THRESHOLD = 70
HEALTH_SCORE_OK_MIN_THRESHOLD = 50
HEALTH_SCORE_WEAK_MAX_THRESHOLD = 40
DCF_UPSIDE_STRONG_THRESHOLD = 20
DCF_UPSIDE_WEAK_THRESHOLD = -20

# --- Narrative-text thresholds (separate from the scoring thresholds above — these just drive the wording) ---
NARRATIVE_HEALTH_EXCELLENT_THRESHOLD = 75
NARRATIVE_HEALTH_SOLID_MIN_THRESHOLD = 50
NARRATIVE_HEALTH_MIXED_MIN_THRESHOLD = 25
DEBT_EQUITY_CONSERVATIVE_MAX = 0.5
DEBT_EQUITY_MANAGEABLE_MAX = 1.5
EARNINGS_ALERT_DAYS = 30
TOP_N_SUPPLY_CHAIN_RISKS = 2
TOP_N_ALERTS = 3
TOP_N_FACTOR_SCORES = 2


def _get(d: Optional[dict], path: List[object], default=None):
    """Safely walk a nested dict/list `path`, returning `default` if anything along it is missing."""
    cur = d
    for key in path:
        if cur is None:
            return default
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


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


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    """Format a plain number, or "N/A" if missing."""
    cleaned = _clean(value)
    if cleaned is None:
        return "N/A"
    return f"{cleaned:.{decimals}f}"


def _pct(fraction: Optional[float], decimals: int = 2) -> str:
    """Format a 0-1 fraction as a percentage string (e.g. 0.469 -> "46.90"), or "N/A" if missing."""
    cleaned = _clean(fraction)
    if cleaned is None:
        return "N/A"
    return f"{cleaned * 100:.{decimals}f}"


def _dollars(value: Optional[float], decimals: int = 2) -> str:
    """Format a per-share dollar amount (e.g. "$123.45"), or "N/A" if missing."""
    cleaned = _clean(value)
    if cleaned is None:
        return "N/A"
    return f"${cleaned:,.{decimals}f}"


def _money(value: Optional[float]) -> str:
    """Format a large aggregate dollar amount with a K/M/B/T suffix, or "N/A" if missing."""
    cleaned = _clean(value)
    if cleaned is None:
        return "N/A"
    abs_v = abs(cleaned)
    if abs_v >= 1e12:
        return f"${cleaned / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"${cleaned / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"${cleaned / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"${cleaned / 1e3:.2f}K"
    return f"${cleaned:.2f}"


def _ratio(value: object) -> str:
    """Format a buy_sell_ratio-style field, which may be the literal string "all_buys" or a number."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    return _fmt(value)


class InvestmentSummaryAnalyzer:
    """Aggregates all 14 analyzer modules into one investment statement/verdict/AI prompt."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()

    # ------------------------------------------------------------------
    # 1. Data gathering
    # ------------------------------------------------------------------

    def _fetch_quote(self) -> Dict:
        """Direct yfinance quote fetch; returns an all-None shell on failure so it never breaks the rest of the summary."""
        try:
            info = yf.Ticker(self.ticker).info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            change = (price - prev_close) if price is not None and prev_close is not None else None
            change_pct = (change / prev_close * 100) if change is not None and prev_close else None
            return {
                "current_price": _clean(price),
                "change": _clean(change),
                "change_pct": _clean(change_pct),
                "market_cap": _clean(info.get("marketCap")),
                "company_name": info.get("longName") or info.get("shortName") or self.ticker,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
            }
        except Exception:
            return {
                "current_price": None, "change": None, "change_pct": None, "market_cap": None,
                "company_name": self.ticker, "sector": None, "industry": None,
            }

    def gather_all_data(self) -> Dict:
        """Call all 14 analyzer modules plus the quote fetch, in sequence.

        Each call is wrapped in try/except so one failing module doesn't take down the rest.
        """
        data = {}
        modules = [
            ("fundamental", lambda: FundamentalAnalyzer(self.ticker).get_full_analysis()),
            ("valuation", lambda: ValuationAnalyzer(self.ticker).get_full_valuation()),
            ("technical", lambda: TechnicalAnalyzer(self.ticker).get_full_technical()),
            ("volume", lambda: VolumeAnalyzer(self.ticker).get_full_volume_analysis()),
            ("risk", lambda: RiskAnalyzer(self.ticker).get_full_risk_analysis()),
            ("institutional", lambda: InstitutionalAnalyzer(self.ticker).get_full_institutional_analysis()),
            ("sentiment", lambda: SentimentAnalyzer(self.ticker).get_full_sentiment_analysis()),
            ("earnings", lambda: EarningsAnalyzer(self.ticker).get_full_earnings_analysis()),
            ("quantitative", lambda: QuantitativeAnalyzer(self.ticker).get_full_quantitative_analysis()),
            ("social", lambda: SocialSentimentAnalyzer(self.ticker).get_full_social_analysis()),
            ("geopolitical", lambda: GeopoliticalAnalyzer(self.ticker).get_full_geopolitical_analysis()),
            ("political", lambda: PoliticalAnalyzer(self.ticker).get_full_political_analysis()),
            ("macro", lambda: MacroAnalyzer(self.ticker).get_full_macro_analysis()),
            ("calendar", lambda: EconomicCalendarAnalyzer(self.ticker).get_full_calendar()),
        ]

        for name, fn in modules:
            try:
                data[name] = fn()
            except Exception:
                data[name] = None
            print(f"[Summary] Completed: {name}")

        data["quote"] = self._fetch_quote()
        print("[Summary] Completed: quote")
        return data

    # ------------------------------------------------------------------
    # Shared field extraction (used by both the statement and the AI prompt)
    # ------------------------------------------------------------------

    def _extract(self, data: Dict) -> Dict:
        """Flatten every field the statement/AI-prompt need out of the raw module dicts.

        One place mapping each field to its source, since units differ across modules (e.g. margins are fractions, risk returns are already percentages).
        """
        v = {}

        q = data.get("quote") or {}
        v["company_name"] = q.get("company_name") or self.ticker
        v["sector"] = q.get("sector") or "N/A"
        v["industry"] = q.get("industry") or "N/A"
        v["price"] = q.get("current_price")
        v["change"] = q.get("change")
        v["change_pct"] = q.get("change_pct")
        v["market_cap"] = q.get("market_cap")

        # Fundamental
        v["health_score"] = _get(data, ["fundamental", "health_score"])
        v["revenue"] = _get(data, ["fundamental", "income", "revenue"])
        v["revenue_growth"] = _get(data, ["fundamental", "income", "revenue_growth"])
        v["gross_margin"] = _get(data, ["fundamental", "income", "gross_margin"])
        v["operating_margin"] = _get(data, ["fundamental", "income", "operating_margin"])
        v["net_margin"] = _get(data, ["fundamental", "income", "net_margin"])
        v["ebitda"] = _get(data, ["fundamental", "income", "ebitda"])
        v["eps"] = _get(data, ["fundamental", "income", "eps"])
        v["eps_growth"] = _get(data, ["fundamental", "income", "eps_growth"])
        v["roe"] = _get(data, ["fundamental", "profitability", "roe"])
        v["roa"] = _get(data, ["fundamental", "profitability", "roa"])
        v["roic"] = _get(data, ["fundamental", "profitability", "roic"])
        v["fcf"] = _get(data, ["fundamental", "cashflow", "free_cashflow"])
        v["fcf_margin"] = _get(data, ["fundamental", "cashflow", "fcf_margin"])
        v["current_ratio"] = _get(data, ["fundamental", "balance", "current_ratio"])
        v["debt_equity"] = _get(data, ["fundamental", "balance", "debt_to_equity"])

        # Valuation
        v["intrinsic_value"] = _get(data, ["valuation", "dcf", "intrinsic_value"])
        v["dcf_current_price"] = _get(data, ["valuation", "dcf", "current_price"])
        v["upside_pct"] = _get(data, ["valuation", "dcf", "upside_pct"])
        v["wacc"] = _get(data, ["valuation", "dcf", "wacc"])
        v["fcf_growth_rate"] = _get(data, ["valuation", "dcf", "fcf_growth_rate"])
        v["pe"] = _get(data, ["valuation", "multiples", "pe", "value"])
        v["pe_sector_avg"] = _get(data, ["valuation", "multiples", "pe", "sector_avg"])
        v["forward_pe"] = _get(data, ["valuation", "multiples", "forward_pe", "value"])
        v["peg"] = _get(data, ["valuation", "multiples", "peg", "value"])
        v["ev_ebitda"] = _get(data, ["valuation", "multiples", "ev_ebitda", "value"])
        v["price_book"] = _get(data, ["valuation", "multiples", "price_book", "value"])
        v["valuation_verdict"] = _get(data, ["valuation", "verdict"])

        # Technical
        v["overall_technical"] = _get(data, ["technical", "overall_signal"])
        v["rsi_value"] = _get(data, ["technical", "momentum", "rsi", "value"])
        v["rsi_signal"] = _get(data, ["technical", "momentum", "rsi", "signal"])
        v["macd_signal"] = _get(data, ["technical", "momentum", "macd", "signal"])
        v["macd_histogram"] = _get(data, ["technical", "momentum", "macd", "histogram"])
        v["price_vs_sma20"] = _get(data, ["technical", "trend", "price_vs_sma20"])
        v["price_vs_sma50"] = _get(data, ["technical", "trend", "price_vs_sma50"])
        v["price_vs_sma200"] = _get(data, ["technical", "trend", "price_vs_sma200"])
        v["bb_signal"] = _get(data, ["technical", "momentum", "bollinger_bands", "signal"])
        v["bb_percent_b"] = _get(data, ["technical", "momentum", "bollinger_bands", "percent_b"])
        v["adx"] = _get(data, ["technical", "trend", "adx"])
        v["adx_trend"] = _get(data, ["technical", "trend", "adx_trend"])
        v["ichimoku_signal"] = _get(data, ["technical", "trend", "ichimoku_signal"])

        # Volume
        v["overall_flow_signal"] = _get(data, ["volume", "overall_flow_signal"])
        v["obv_signal"] = _get(data, ["volume", "obv", "obv_signal"])
        v["cmf_value"] = _get(data, ["volume", "chaikin_money_flow", "cmf_value"])
        v["cmf_signal"] = _get(data, ["volume", "chaikin_money_flow", "cmf_signal"])
        v["poc_price"] = _get(data, ["volume", "volume_profile", "poc_price"])
        v["vwap_signal"] = _get(data, ["volume", "vwap", "signal"])
        v["vwap_distance_pct"] = _get(data, ["volume", "vwap", "distance_pct"])
        v["rvol"] = _get(data, ["volume", "relative_volume", "rvol"])

        # Risk
        v["risk_label"] = _get(data, ["risk", "risk_label"])
        v["beta"] = _get(data, ["risk", "ratios", "beta"])
        v["annualized_volatility"] = _get(data, ["risk", "returns", "annualized_volatility"])
        v["sharpe_ratio"] = _get(data, ["risk", "ratios", "sharpe_ratio"])
        v["sortino_ratio"] = _get(data, ["risk", "ratios", "sortino_ratio"])
        v["max_drawdown"] = _get(data, ["risk", "drawdown", "max_drawdown"])
        v["current_drawdown"] = _get(data, ["risk", "drawdown", "current_drawdown"])
        v["var_95"] = _get(data, ["risk", "var", "historical_var_95"])
        v["cvar_95"] = _get(data, ["risk", "var", "cvar_95"])
        v["correlation_spy"] = _get(data, ["risk", "correlations", "ticker_vs_spy"])

        # Earnings
        v["eps_beat_rate"] = _get(data, ["earnings", "history", "eps_beat_rate"])
        v["avg_eps_surprise"] = _get(data, ["earnings", "history", "avg_eps_surprise_pct"])
        v["eps_trend"] = _get(data, ["earnings", "eps_trend", "eps_trend"])
        v["revenue_trend"] = _get(data, ["earnings", "revenue_trend", "revenue_trend"])
        v["earnings_quality"] = _get(data, ["earnings", "earnings_quality", "earnings_quality"])
        v["next_earnings_date"] = _get(data, ["earnings", "next_earnings", "next_earnings_date"])
        v["days_until_earnings"] = _get(data, ["earnings", "next_earnings", "days_until_earnings"])
        v["earnings_signal"] = _get(data, ["earnings", "earnings_signal"])

        # Institutional
        v["inst_own_pct"] = _get(data, ["institutional", "institutional_holders", "total_inst_ownership_pct"])
        major_present = _get(data, ["institutional", "institutional_holders", "major_holders_present"]) or {}
        v["major_holders"] = [k for k, present in major_present.items() if present]
        v["insider_signal"] = _get(data, ["institutional", "insider_trades", "signal"])
        v["buy_sell_ratio"] = _get(data, ["institutional", "insider_trades", "buy_sell_ratio"])
        v["short_float_pct"] = _get(data, ["institutional", "finviz_ownership", "short_float_pct"])
        v["smart_money_signal"] = _get(data, ["institutional", "smart_money_signal"])

        # Sentiment
        v["fear_greed_score"] = _get(data, ["sentiment", "fear_greed", "score"])
        v["fear_greed_rating"] = _get(data, ["sentiment", "fear_greed", "rating"])
        v["vix_value"] = _get(data, ["sentiment", "vix", "current_vix"])
        v["vix_regime"] = _get(data, ["sentiment", "vix", "vix_regime"])
        v["consensus_label"] = _get(data, ["sentiment", "analyst_ratings", "consensus_label"])
        v["mean_target"] = _get(data, ["sentiment", "analyst_ratings", "price_targets", "mean_target"])
        v["target_upside_pct"] = _get(data, ["sentiment", "analyst_ratings", "price_targets", "upside_from_current"])
        v["news_sentiment_label"] = _get(data, ["sentiment", "news_sentiment", "sentiment_label"])
        v["overall_sentiment_signal"] = _get(data, ["sentiment", "overall_sentiment_signal"])
        # Sentiment's own embedded macro signals, separate from the standalone macro module below
        v["sentiment_yield_curve_signal"] = _get(data, ["sentiment", "macro", "yield_curve_signal"])
        v["inflation_signal"] = _get(data, ["sentiment", "macro", "inflation_signal"])
        v["fed_signal"] = _get(data, ["sentiment", "macro", "fed_signal"])

        # Geopolitical
        v["geopolitical_signal"] = _get(data, ["geopolitical", "geopolitical_signal"])
        v["geo_overall_risk"] = _get(data, ["geopolitical", "geopolitical_risk", "overall_geopolitical_risk"])
        v["geo_key_risks"] = _get(data, ["geopolitical", "geopolitical_risk", "risk_factors"]) or []
        v["global_risk_mode"] = _get(data, ["geopolitical", "global_market_context", "global_risk_mode"])
        v["multi_source_sentiment_label"] = _get(data, ["geopolitical", "multi_source_news", "sentiment_consensus"])
        v["dominant_news_topic"] = _get(data, ["geopolitical", "ticker_news", "dominant_topic"])

        # Political
        v["political_signal"] = _get(data, ["political", "political_signal"])
        v["policy_risk_score"] = _get(data, ["political", "policy_risk", "overall_policy_risk"])
        v["policy_risk_label"] = _get(data, ["political", "policy_risk", "risk_label"])
        v["key_policy_risks"] = _get(data, ["political", "policy_risk", "key_policy_risks"]) or []
        v["legislative_risk"] = _get(data, ["political", "congress", "sector_legislative_risk"])
        v["fed_policy_sector_impact"] = _get(data, ["political", "fed_policy", "sector_fed_impact"])

        # Macro (standalone module)
        v["yield_curve_shape"] = _get(data, ["macro", "yield_curve", "curve_shape"])
        v["spread_2s10s"] = _get(data, ["macro", "yield_curve", "spreads", "2s10s"])
        v["recession_probability"] = _get(data, ["macro", "yield_curve", "recession_probability"])
        v["credit_signal"] = _get(data, ["macro", "credit_markets", "credit_signal"])
        v["copper_signal"] = _get(data, ["macro", "commodities", "signals", "copper_signal"])
        v["liquidity_signal"] = _get(data, ["macro", "liquidity", "liquidity_signal"])
        v["market_cycle_phase"] = _get(data, ["macro", "sector_rotation", "market_cycle_phase"])
        v["sector_rank"] = _get(data, ["macro", "sector_rotation", "ticker_sector_rank"])
        v["supply_chain_risk_label"] = _get(data, ["macro", "supply_chain", "risk_label"])
        v["supply_chain_key_risks"] = _get(data, ["macro", "supply_chain", "supply_chain_profile", "key_risks"]) or []
        v["macro_signal"] = _get(data, ["macro", "macro_signal"])

        # Quantitative
        v["composite_score"] = _get(data, ["quantitative", "factors", "composite_score"])
        v["factor_rating"] = _get(data, ["quantitative", "factors", "factor_rating"])
        v["momentum_score"] = _get(data, ["quantitative", "factors", "momentum", "score"])
        v["quality_score"] = _get(data, ["quantitative", "factors", "quality", "score"])
        v["value_score"] = _get(data, ["quantitative", "factors", "value", "score"])
        v["growth_score"] = _get(data, ["quantitative", "factors", "growth", "score"])
        v["low_vol_score"] = _get(data, ["quantitative", "factors", "low_volatility", "score"])
        v["prob_of_gain"] = _get(data, ["quantitative", "monte_carlo", "probability_of_gain"])
        v["base_case"] = _get(data, ["quantitative", "monte_carlo", "base_case"])
        v["bull_case"] = _get(data, ["quantitative", "monte_carlo", "bull_case"])
        v["bear_case"] = _get(data, ["quantitative", "monte_carlo", "bear_case"])
        v["best_strategy"] = _get(data, ["quantitative", "backtesting", "best_strategy"])
        best_strategy_stats = _get(data, ["quantitative", "backtesting", v["best_strategy"]]) if v["best_strategy"] else None
        v["best_strategy_return"] = _get(best_strategy_stats, ["total_return"]) if best_strategy_stats else None
        v["best_strategy_sharpe"] = _get(best_strategy_stats, ["sharpe"]) if best_strategy_stats else None
        v["quant_signal"] = _get(data, ["quantitative", "quant_signal"])

        # Calendar
        v["alerts"] = _get(data, ["calendar", "alerts"]) or []
        v["next_fomc"] = _get(data, ["calendar", "fomc", "next_fomc"])
        v["days_until_fomc"] = _get(data, ["calendar", "fomc", "days_until_next_fomc"])

        return v

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _verdict_from_score(self, score: int) -> str:
        """Map the -14..+14 combined score onto a 9-tier STRONG BUY..STRONG SELL verdict."""
        if score >= VERDICT_STRONG_BUY_MIN:
            return "STRONG BUY"
        if score >= VERDICT_BUY_MIN:
            return "BUY"
        if score >= VERDICT_WEAK_BUY_MIN:
            return "WEAK BUY"
        if score >= VERDICT_LEAN_BUY_MIN:
            return "LEAN BUY"
        if score == VERDICT_HOLD:
            return "HOLD"
        if score >= VERDICT_LEAN_SELL_MIN:
            return "LEAN SELL"
        if score >= VERDICT_WEAK_SELL_MIN:
            return "WEAK SELL"
        if score >= VERDICT_SELL_MIN:
            return "SELL"
        return "STRONG SELL"

    def _calculate_score(self, data: Dict) -> Tuple[int, str, Dict[str, int]]:
        """Combine 12 module signals into one -14..+14 score and verdict; breakdown holds each component's contribution."""
        breakdown = {}

        health_score = _get(data, ["fundamental", "health_score"])
        if health_score is None:
            breakdown["fundamental"] = 0
        elif health_score > HEALTH_SCORE_STRONG_THRESHOLD:
            breakdown["fundamental"] = 2
        elif health_score >= HEALTH_SCORE_OK_MIN_THRESHOLD:
            breakdown["fundamental"] = 1
        elif health_score < HEALTH_SCORE_WEAK_MAX_THRESHOLD:
            breakdown["fundamental"] = -1
        else:
            breakdown["fundamental"] = 0

        upside = _get(data, ["valuation", "dcf", "upside_pct"])
        if upside is None:
            breakdown["valuation"] = 0
        elif upside > DCF_UPSIDE_STRONG_THRESHOLD:
            breakdown["valuation"] = 2
        elif upside >= 0:
            breakdown["valuation"] = 1
        elif upside >= DCF_UPSIDE_WEAK_THRESHOLD:
            breakdown["valuation"] = -1
        else:
            breakdown["valuation"] = -2

        tech_sig = _get(data, ["technical", "overall_signal"])
        breakdown["technical"] = 1 if tech_sig == "Bullish" else -1 if tech_sig == "Bearish" else 0

        vol_sig = _get(data, ["volume", "overall_flow_signal"])
        breakdown["volume"] = 1 if vol_sig == "Bullish" else -1 if vol_sig == "Bearish" else 0

        risk_label = _get(data, ["risk", "risk_label"])
        breakdown["risk"] = 1 if risk_label in ("Conservative", "Moderate") else -1 if risk_label in ("Aggressive", "Speculative") else 0

        earnings_sig = _get(data, ["earnings", "earnings_signal"])
        breakdown["earnings"] = 1 if earnings_sig in ("beat_trend", "strong_beat_trend") else -1 if earnings_sig in ("miss_trend", "strong_miss_trend") else 0

        smart_money = _get(data, ["institutional", "smart_money_signal"])
        breakdown["institutional"] = 1 if smart_money == "bullish" else -1 if smart_money == "bearish" else 0

        sent_sig = _get(data, ["sentiment", "overall_sentiment_signal"])
        breakdown["sentiment"] = 1 if sent_sig in ("Bullish", "Very Bullish") else -1 if sent_sig in ("Bearish", "Very Bearish") else 0

        geo_sig = _get(data, ["geopolitical", "geopolitical_signal"])
        breakdown["geopolitical"] = -1 if geo_sig == "High Risk" else 1 if geo_sig == "Low Risk" else 0

        pol_sig = _get(data, ["political", "political_signal"])
        breakdown["political"] = -1 if pol_sig == "High Risk" else 1 if pol_sig == "Low Risk" else 0

        macro_sig = _get(data, ["macro", "macro_signal"])
        breakdown["macro"] = 1 if macro_sig in ("Bullish", "Very Bullish") else -1 if macro_sig in ("Bearish", "Very Bearish") else 0

        quant_sig = _get(data, ["quantitative", "quant_signal"])
        breakdown["quantitative"] = 1 if quant_sig in ("Strong Buy", "Buy") else -1 if quant_sig in ("Sell", "Strong Sell") else 0

        score = sum(breakdown.values())
        verdict = self._verdict_from_score(score)
        return score, verdict, breakdown

    # ------------------------------------------------------------------
    # 2. Statement generation (13 sections, one helper method each)
    # ------------------------------------------------------------------

    def _section_company_overview(self, v: Dict) -> str:
        """SECTION 1 — company name, sector, price, market cap, industry."""
        return (
            f"{v['company_name']} ({self.ticker}) is a {v['sector']} company trading at "
            f"${_fmt(v['price'])} ({_fmt(v['change_pct'])}% today) with a market cap of {_money(v['market_cap'])}. "
            f"The company operates in the {v['industry']} industry."
        )

    def _section_fundamental_health(self, v: Dict) -> str:
        """SECTION 2 — margins, ROE, FCF, debt/equity, and the health score."""
        hs = v["health_score"]
        if hs is None:
            opening = f"Fundamental health data is currently unavailable for {self.ticker}."
        elif hs > NARRATIVE_HEALTH_EXCELLENT_THRESHOLD:
            opening = f"Fundamentally, {self.ticker} is in excellent financial health"
        elif hs >= NARRATIVE_HEALTH_SOLID_MIN_THRESHOLD:
            opening = f"Fundamentally, {self.ticker} shows solid financial metrics"
        elif hs >= NARRATIVE_HEALTH_MIXED_MIN_THRESHOLD:
            opening = f"Fundamentally, {self.ticker} shows mixed financial health"
        else:
            opening = f"Fundamentally, {self.ticker} shows concerning financial metrics"

        de = v["debt_equity"]
        if de is None:
            debt_label = "unknown"
        elif de < DEBT_EQUITY_CONSERVATIVE_MAX:
            debt_label = "conservative"
        elif de < DEBT_EQUITY_MANAGEABLE_MAX:
            debt_label = "manageable"
        else:
            debt_label = "elevated"

        return (
            f"{opening} with a gross margin of {_pct(v['gross_margin'])}%, operating margin of "
            f"{_pct(v['operating_margin'])}%, ROE of {_pct(v['roe'])}%, and free cash flow of {_money(v['fcf'])}. "
            f"Debt/equity stands at {_fmt(de)} — {debt_label}. Health score: {_fmt(hs, 0)}/100."
        )

    def _section_valuation(self, v: Dict) -> str:
        """SECTION 3 — DCF intrinsic value vs. current price, and relative multiples."""
        upside = v["upside_pct"]
        if upside is None:
            val_opening = f"Valuation data is currently unavailable for {self.ticker}."
        elif upside > DCF_UPSIDE_STRONG_THRESHOLD:
            val_opening = f"{self.ticker} appears undervalued"
        elif upside >= 0:
            val_opening = f"{self.ticker} appears fairly valued with slight upside"
        elif upside >= DCF_UPSIDE_WEAK_THRESHOLD:
            val_opening = f"{self.ticker} appears fairly valued with slight downside"
        else:
            val_opening = f"{self.ticker} appears overvalued"
        up_down = "upside" if (upside is not None and upside >= 0) else "downside"

        return (
            f"{val_opening}. Our DCF model estimates intrinsic value at {_dollars(v['intrinsic_value'])} vs "
            f"current price of {_dollars(v['dcf_current_price'])} "
            f"({_fmt(abs(upside) if upside is not None else None)}% {up_down}). "
            f"The stock trades at a P/E of {_fmt(v['pe'])} vs sector average of {_fmt(v['pe_sector_avg'])}, "
            f"EV/EBITDA of {_fmt(v['ev_ebitda'])}, and Price/Book of {_fmt(v['price_book'])}. "
            f"Overall valuation verdict: {v['valuation_verdict'] or 'N/A'}."
        )

    def _section_technical_picture(self, v: Dict) -> str:
        """SECTION 4 — RSI, MACD, moving averages, Bollinger Bands, Ichimoku."""
        return (
            f"Technically, {self.ticker} is showing a {v['overall_technical'] or 'N/A'} setup. "
            f"RSI stands at {_fmt(v['rsi_value'])} ({v['rsi_signal'] or 'N/A'}), "
            f"MACD is {v['macd_signal'] or 'N/A'}, price is {v['price_vs_sma50'] or 'N/A'} the 50-day "
            f"moving average, and Bollinger Bands suggest the stock is {v['bb_signal'] or 'N/A'}. "
            f"Ichimoku Cloud signals {v['ichimoku_signal'] or 'N/A'}."
        )

    def _section_volume_flow(self, v: Dict) -> str:
        """SECTION 5 — OBV, Chaikin Money Flow, VWAP position."""
        cmf_sig = v["cmf_signal"] or ""
        pressure = "buying pressure" if "buy" in cmf_sig else "selling pressure" if "sell" in cmf_sig else "neutral pressure"
        vwap_dir = "above" if v["vwap_signal"] == "above_vwap" else "below" if v["vwap_signal"] == "below_vwap" else "N/A"

        return (
            f"Volume analysis shows {v['overall_flow_signal'] or 'N/A'} money flow. "
            f"On Balance Volume is {v['obv_signal'] or 'N/A'}, Chaikin Money Flow reads {_fmt(v['cmf_value'], 3)} "
            f"({pressure}), and the stock is trading {vwap_dir} its Volume Weighted Average Price (VWAP)."
        )

    def _section_risk_profile(self, v: Dict) -> str:
        """SECTION 6 — beta, volatility, Sharpe, max drawdown, VaR."""
        beta = v["beta"]
        more_less = "more" if (beta is not None and beta > 1) else "less" if beta is not None else "an unclear amount"
        var95 = v["var_95"]

        return (
            f"Risk profile is {v['risk_label'] or 'N/A'}. Beta of {_fmt(beta)} indicates the stock moves "
            f"{more_less} than the broader market. Annualized volatility of {_fmt(v['annualized_volatility'])}%, "
            f"Sharpe ratio of {_fmt(v['sharpe_ratio'])}, and maximum historical drawdown of {_fmt(v['max_drawdown'])}%. "
            f"VaR (95%) suggests a worst-case daily loss of {_fmt(abs(var95) if var95 is not None else None)}%."
        )

    def _section_earnings_quality(self, v: Dict) -> str:
        """SECTION 7 — beat rate, average surprise, earnings quality, and an upcoming-earnings alert."""
        section = (
            f"Earnings analysis shows a {v['earnings_signal'] or 'N/A'} pattern. The company has beaten EPS "
            f"estimates {_fmt(v['eps_beat_rate'], 0)}% of the time over the last 8 quarters with an average "
            f"surprise of {_fmt(v['avg_eps_surprise'])}%. Earnings quality is rated {v['earnings_quality'] or 'N/A'} "
            f"based on cash flow backing of reported earnings."
        )
        if v["days_until_earnings"] is not None and v["days_until_earnings"] < EARNINGS_ALERT_DAYS:
            section += f"\n⚠️ Next earnings report is in {v['days_until_earnings']} days — elevated volatility expected."
        return section

    def _section_institutional_insider(self, v: Dict) -> str:
        """SECTION 8 — smart money signal, institutional ownership, insider activity."""
        major_text = f"major holders present ({', '.join(v['major_holders'])})" if v["major_holders"] else "no major holders detected"
        return (
            f"Smart money signals are {v['smart_money_signal'] or 'N/A'}. Institutional ownership stands at "
            f"{_fmt(v['inst_own_pct'])}%, with {major_text}. Insider activity shows {v['insider_signal'] or 'N/A'} "
            f"with a buy/sell ratio of {_ratio(v['buy_sell_ratio'])}."
        )

    def _section_market_sentiment_macro(self, v: Dict) -> str:
        """SECTION 9 — Fear & Greed, VIX, analyst consensus, yield curve/inflation/Fed.

        Yield curve/recession fields come from the macro module, inflation/Fed from sentiment's embedded macro — neither module has all four alone.
        """
        return (
            f"Market sentiment is {v['overall_sentiment_signal'] or 'N/A'}. The Fear & Greed Index reads "
            f"{_fmt(v['fear_greed_score'], 0)} ({v['fear_greed_rating'] or 'N/A'}), VIX is at {_fmt(v['vix_value'])} "
            f"({v['vix_regime'] or 'N/A'}), and analyst consensus is {v['consensus_label'] or 'N/A'} with a mean "
            f"price target of {_dollars(v['mean_target'])}. Macro environment: yield curve is "
            f"{v['yield_curve_shape'] or 'N/A'} ({v['recession_probability'] or 'N/A'} recession probability), "
            f"inflation signal is {v['inflation_signal'] or 'N/A'}, Fed policy is {v['fed_signal'] or 'N/A'}."
        )

    def _section_geopolitical_political(self, v: Dict) -> str:
        """SECTION 10 — geopolitical risk, supply chain exposure, political/policy risk."""
        top_supply_risks = v["supply_chain_key_risks"][:TOP_N_SUPPLY_CHAIN_RISKS]
        top_policy_risk = v["key_policy_risks"][0] if v["key_policy_risks"] else "no significant risks identified"
        section = (
            f"Geopolitical risk is assessed as {v['geopolitical_signal'] or 'N/A'}. Supply chain exposure for the "
            f"{v['sector']} sector is {v['supply_chain_risk_label'] or 'N/A'} with key risks including "
            f"{'; '.join(top_supply_risks) if top_supply_risks else 'none identified'}. "
            f"Political risk is {v['political_signal'] or 'N/A'}, with {v['policy_risk_label'] or 'N/A'} "
            f"driven by {top_policy_risk}."
        )
        if v["global_risk_mode"] and v["global_risk_mode"] != "neutral":
            section += f"\nGlobal markets are currently in {v['global_risk_mode'].replace('_', ' ')} mode."
        return section

    def _section_upcoming_catalysts(self, v: Dict) -> str:
        """SECTION 11 — the top upcoming calendar alerts (FOMC/earnings/economic releases)."""
        top_alerts = v["alerts"][:TOP_N_ALERTS]
        if top_alerts:
            return (
                "Key upcoming events to watch:\n" + "\n".join(top_alerts) +
                f"\nThese events could cause elevated volatility in {self.ticker}."
            )
        return f"No major scheduled catalysts flagged as urgent for {self.ticker} in the near term."

    def _section_quantitative_signals(self, v: Dict) -> str:
        """SECTION 12 — composite factor score, strongest/weakest factors, Monte Carlo outlook."""
        factor_scores = {
            "Momentum": v["momentum_score"], "Quality": v["quality_score"], "Value": v["value_score"],
            "Growth": v["growth_score"], "Low Volatility": v["low_vol_score"],
        }
        valid_factors = sorted(((k, s) for k, s in factor_scores.items() if s is not None), key=lambda x: x[1], reverse=True)
        top_factors = valid_factors[:TOP_N_FACTOR_SCORES]
        weakest = valid_factors[-1] if valid_factors else None
        top_factors_text = ", ".join(f"{name} ({_fmt(s, 0)})" for name, s in top_factors) if top_factors else "N/A"
        weakest_text = f"{weakest[0]} ({_fmt(weakest[1], 0)})" if weakest else "N/A"

        return (
            f"Quantitative factor analysis gives {self.ticker} a composite score of {_fmt(v['composite_score'], 0)}/100 "
            f"({v['factor_rating'] or 'N/A'}). Strongest factors: {top_factors_text}. Weakest factors: {weakest_text}. "
            f"Monte Carlo simulation suggests a {_fmt(v['prob_of_gain'], 0)}% probability of positive returns over "
            f"the next year, with a base case price target of {_dollars(v['base_case'])}."
        )

    def _section_overall_verdict(self, score: int, verdict: str) -> str:
        """SECTION 13 — the final verdict, its description, and the disclaimer."""
        return (
            f"OVERALL VERDICT: {verdict} (Score: {score}/12)\n\n"
            f"{VERDICT_DESCRIPTIONS.get(verdict, '')}\n\n{DISCLAIMER}"
        )

    def generate_statement(self, data: Dict) -> str:
        """Build the 13-section plain-English investment statement."""
        v = self._extract(data)
        score, verdict, _ = self._calculate_score(data)

        sections = [
            self._section_company_overview(v),
            self._section_fundamental_health(v),
            self._section_valuation(v),
            self._section_technical_picture(v),
            self._section_volume_flow(v),
            self._section_risk_profile(v),
            self._section_earnings_quality(v),
            self._section_institutional_insider(v),
            self._section_market_sentiment_macro(v),
            self._section_geopolitical_political(v),
            self._section_upcoming_catalysts(v),
            self._section_quantitative_signals(v),
            self._section_overall_verdict(score, verdict),
        ]
        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # 3. AI prompt generation
    # ------------------------------------------------------------------

    def generate_ai_prompt(self, data: Dict, statement: str) -> str:
        """Build the full data-dump + analysis-tasks prompt for pasting into an AI chat.

        Kept as one method instead of split into helpers since it's really just one big string template, not a sequence of separate computations.
        """
        v = self._extract(data)
        score, verdict, _ = self._calculate_score(data)

        major_holders_text = ", ".join(v["major_holders"]) if v["major_holders"] else "None detected"
        geo_risks_text = "; ".join(v["geo_key_risks"][:3]) if v["geo_key_risks"] else "None identified"
        policy_risks_text = "; ".join(v["key_policy_risks"][:2]) if v["key_policy_risks"] else "None identified"
        alerts_text = "\n".join(v["alerts"]) if v["alerts"] else "No urgent alerts flagged"

        return f"""You are a senior equity analyst at a top-tier investment bank.
Analyze the following comprehensive data for {self.ticker} and provide
a detailed investment opinion.

=== COMPANY OVERVIEW ===
Company: {v['company_name']} | Sector: {v['sector']} | Industry: {v['industry']}
Current Price: ${_fmt(v['price'])} | Change: {_fmt(v['change_pct'])}%
Market Cap: {_money(v['market_cap'])}

=== FUNDAMENTAL ANALYSIS ===
Health Score: {_fmt(v['health_score'], 0)}/100
Revenue: {_money(v['revenue'])} | Revenue Growth: {_pct(v['revenue_growth'])}%
Gross Margin: {_pct(v['gross_margin'])}% | Operating Margin: {_pct(v['operating_margin'])}% | Net Margin: {_pct(v['net_margin'])}%
EBITDA: {_money(v['ebitda'])} | EPS: ${_fmt(v['eps'])} | EPS Growth: {_pct(v['eps_growth'])}%
ROE: {_pct(v['roe'])}% | ROA: {_pct(v['roa'])}% | ROIC: {_pct(v['roic'])}%
Free Cash Flow: {_money(v['fcf'])} | FCF Margin: {_pct(v['fcf_margin'])}%
Current Ratio: {_fmt(v['current_ratio'])} | Debt/Equity: {_fmt(v['debt_equity'])}

=== VALUATION ===
DCF Intrinsic Value: ${_fmt(v['intrinsic_value'])} | Upside/Downside: {_fmt(v['upside_pct'])}%
WACC: {_pct(v['wacc'])}% | FCF Growth Rate Used: {_pct(v['fcf_growth_rate'])}%
P/E: {_fmt(v['pe'])} | Forward P/E: {_fmt(v['forward_pe'])} | PEG: {_fmt(v['peg'])}
EV/EBITDA: {_fmt(v['ev_ebitda'])} | Price/Book: {_fmt(v['price_book'])}
Valuation Verdict: {v['valuation_verdict'] or 'N/A'}

=== TECHNICAL ANALYSIS ===
RSI(14): {_fmt(v['rsi_value'])} — {v['rsi_signal'] or 'N/A'}
MACD: {v['macd_signal'] or 'N/A'} | Histogram: {_fmt(v['macd_histogram'])}
Price vs SMA20: {v['price_vs_sma20'] or 'N/A'} | SMA50: {v['price_vs_sma50'] or 'N/A'} | SMA200: {v['price_vs_sma200'] or 'N/A'}
Bollinger Bands: {v['bb_signal'] or 'N/A'} | %B: {_fmt(v['bb_percent_b'])}
ADX: {_fmt(v['adx'])} ({v['adx_trend'] or 'N/A'})
Ichimoku: {v['ichimoku_signal'] or 'N/A'}
Overall Technical: {v['overall_technical'] or 'N/A'}

=== VOLUME & FLOW ===
OBV Signal: {v['obv_signal'] or 'N/A'}
Chaikin Money Flow: {_fmt(v['cmf_value'], 3)} ({v['cmf_signal'] or 'N/A'})
Volume Profile POC: ${_fmt(v['poc_price'])}
Price vs VWAP: {v['vwap_signal'] or 'N/A'} by {_fmt(v['vwap_distance_pct'])}%
Relative Volume: {_fmt(v['rvol'])}x average
Overall Flow: {v['overall_flow_signal'] or 'N/A'}

=== RISK METRICS ===
Beta: {_fmt(v['beta'])} | Annualized Volatility: {_fmt(v['annualized_volatility'])}%
Sharpe Ratio: {_fmt(v['sharpe_ratio'])} | Sortino Ratio: {_fmt(v['sortino_ratio'])}
Max Drawdown: {_fmt(v['max_drawdown'])}% | Current Drawdown: {_fmt(v['current_drawdown'])}%
VaR 95%: {_fmt(v['var_95'])}% | CVaR 95%: {_fmt(v['cvar_95'])}%
Correlation to SPY: {_fmt(v['correlation_spy'])}
Risk Label: {v['risk_label'] or 'N/A'}

=== EARNINGS ===
EPS Beat Rate: {_fmt(v['eps_beat_rate'], 0)}% (last 8 quarters)
Avg EPS Surprise: {_fmt(v['avg_eps_surprise'])}%
EPS Trend: {v['eps_trend'] or 'N/A'}
Revenue Growth Trend: {v['revenue_trend'] or 'N/A'}
Earnings Quality: {v['earnings_quality'] or 'N/A'}
Next Earnings: {v['next_earnings_date'] or 'N/A'} ({v['days_until_earnings'] if v['days_until_earnings'] is not None else 'N/A'} days away)
Earnings Signal: {v['earnings_signal'] or 'N/A'}

=== INSTITUTIONAL & INSIDER ===
Institutional Ownership: {_fmt(v['inst_own_pct'])}%
Major Holders: {major_holders_text}
Insider Signal: {v['insider_signal'] or 'N/A'}
Short Float: {_fmt(v['short_float_pct'])}%
Smart Money: {v['smart_money_signal'] or 'N/A'}

=== MARKET SENTIMENT ===
Fear & Greed: {_fmt(v['fear_greed_score'], 0)} ({v['fear_greed_rating'] or 'N/A'})
VIX: {_fmt(v['vix_value'])} ({v['vix_regime'] or 'N/A'})
Analyst Consensus: {v['consensus_label'] or 'N/A'}
Mean Price Target: ${_fmt(v['mean_target'])} ({_fmt(v['target_upside_pct'])}% upside)
News Sentiment: {v['news_sentiment_label'] or 'N/A'}
Overall Sentiment: {v['overall_sentiment_signal'] or 'N/A'}

=== MACRO ENVIRONMENT ===
Yield Curve: {v['yield_curve_shape'] or 'N/A'} | 2s10s Spread: {_fmt(v['spread_2s10s'])}%
Recession Probability: {v['recession_probability'] or 'N/A'}
Credit Markets: {v['credit_signal'] or 'N/A'}
Copper Signal: {v['copper_signal'] or 'N/A'}
M2 Liquidity: {v['liquidity_signal'] or 'N/A'}
Market Cycle Phase: {v['market_cycle_phase'] or 'N/A'}
Sector Rotation Rank: {v['sector_rank'] if v['sector_rank'] is not None else 'N/A'}/11
Supply Chain Risk: {v['supply_chain_risk_label'] or 'N/A'}
Macro Signal: {v['macro_signal'] or 'N/A'}

=== GEOPOLITICAL RISK ===
Geopolitical Signal: {v['geopolitical_signal'] or 'N/A'}
Overall Risk Score: {_fmt(v['geo_overall_risk'], 0)}/100
Key Risks: {geo_risks_text}
Global Market Mode: {v['global_risk_mode'] or 'N/A'}
News Sentiment (Multi-source): {v['multi_source_sentiment_label'] or 'N/A'}
Dominant News Topic: {v['dominant_news_topic'] or 'N/A'}

=== POLITICAL & POLICY RISK ===
Policy Risk Score: {_fmt(v['policy_risk_score'], 0)}/100
Political Signal: {v['political_signal'] or 'N/A'}
Legislative Risk: {v['legislative_risk'] or 'N/A'}
Fed Policy Impact on Sector: {v['fed_policy_sector_impact'] or 'N/A'}
Key Policy Risks: {policy_risks_text}

=== QUANTITATIVE FACTORS ===
Composite Score: {_fmt(v['composite_score'], 0)}/100 ({v['factor_rating'] or 'N/A'})
Momentum: {_fmt(v['momentum_score'], 0)} | Quality: {_fmt(v['quality_score'], 0)} | Value: {_fmt(v['value_score'], 0)}
Growth: {_fmt(v['growth_score'], 0)} | Low Volatility: {_fmt(v['low_vol_score'], 0)}
Monte Carlo Prob of Gain: {_fmt(v['prob_of_gain'], 0)}%
Base Case 1Y Price: ${_fmt(v['base_case'])} | Bull Case: ${_fmt(v['bull_case'])} | Bear Case: ${_fmt(v['bear_case'])}
Best Backtest Strategy: {(v['best_strategy'] or 'N/A').replace('_', ' ')} ({_fmt(v['best_strategy_return'])}% return, Sharpe {_fmt(v['best_strategy_sharpe'])})
Quant Signal: {v['quant_signal'] or 'N/A'}

=== UPCOMING CATALYSTS ===
{alerts_text}
Next FOMC: {v['next_fomc'] or 'N/A'} ({v['days_until_fomc'] if v['days_until_fomc'] is not None else 'N/A'} days)
Next Earnings: {v['next_earnings_date'] or 'N/A'} ({v['days_until_earnings'] if v['days_until_earnings'] is not None else 'N/A'} days)

=== AUTO-GENERATED VERDICT ===
Score: {score}/12 | Verdict: {verdict}

{statement}

=== YOUR ANALYSIS TASKS ===
1. Do you agree with the {verdict} verdict? What would change it?
2. What are the 3 biggest risks right now?
3. What are the 3 strongest bull case arguments?
4. Set a 12-month price target with full rationale
5. What specific metrics would you monitor most closely?
6. How does the geopolitical/political environment specifically
   affect this stock over the next 6-12 months?
7. Given the macro environment ({v['yield_curve_shape'] or 'N/A'} yield curve,
   {v['recession_probability'] or 'N/A'} recession probability, {v['macro_signal'] or 'N/A'} macro),
   how would you position this stock in a portfolio?
"""

    # ------------------------------------------------------------------
    # 4. Full summary
    # ------------------------------------------------------------------

    def get_full_summary(self) -> Dict:
        """Gather all module data and produce the statement, AI prompt, verdict, and score."""
        data = self.gather_all_data()
        statement = self.generate_statement(data)
        ai_prompt = self.generate_ai_prompt(data, statement)
        score, verdict, breakdown = self._calculate_score(data)
        v = self._extract(data)

        return {
            "ticker": self.ticker,
            "company_name": v["company_name"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "score": score,
            "score_breakdown": breakdown,
            "statement": statement,
            "ai_prompt": ai_prompt,
            "data_summary": {
                "price": v["price"],
                "market_cap": v["market_cap"],
                "health_score": v["health_score"],
                "dcf_upside_pct": v["upside_pct"],
                "technical_signal": v["overall_technical"],
                "volume_signal": v["overall_flow_signal"],
                "risk_label": v["risk_label"],
                "earnings_signal": v["earnings_signal"],
                "smart_money_signal": v["smart_money_signal"],
                "sentiment_signal": v["overall_sentiment_signal"],
                "geopolitical_signal": v["geopolitical_signal"],
                "political_signal": v["political_signal"],
                "macro_signal": v["macro_signal"],
                "quant_signal": v["quant_signal"],
                "composite_factor_score": v["composite_score"],
                "monte_carlo_prob_gain": v["prob_of_gain"],
                "next_earnings_date": v["next_earnings_date"],
                "days_until_earnings": v["days_until_earnings"],
                "next_fomc_date": v["next_fomc"],
                "days_until_fomc": v["days_until_fomc"],
                "alerts": v["alerts"],
            },
        }
