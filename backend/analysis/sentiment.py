"""Sentiment & Macro (Module 8): Fear & Greed, VIX, FRED macro data, analyst ratings, keyword-based news sentiment, and sector performance.

Uses a hand-rolled keyword count for news sentiment instead of VADER, unlike the other sentiment modules.
"""

import time
from typing import Dict, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from utils.fred_utils import fetch_fred_series

CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Accept": "application/json",
}

FRED_SERIES = [
    "FEDFUNDS", "CPIAUCSL", "UNRATE", "GDP", "DGS10",
    "DGS2", "T10Y2Y", "DCOILWTICO", "DTWEXBGS",
]
FRED_REQUEST_DELAY_SECONDS = 0.3
CPI_YOY_LOOKBACK_MONTHS = 12

SECTOR_ETFS = {
    "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financial",
    "XLY": "Consumer Discretionary", "XLE": "Energy", "XLI": "Industrial",
    "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLP": "Consumer Staples", "XLC": "Communication",
}

SECTOR_TO_ETF = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Consumer Defensive": "XLP",
    "Communication Services": "XLC",
}

POSITIVE_WORDS = [
    "beat", "surge", "growth", "record", "profit", "upgrade",
    "strong", "bullish", "outperform", "raised", "expansion",
]
NEGATIVE_WORDS = [
    "miss", "decline", "cut", "loss", "downgrade", "weak",
    "bearish", "underperform", "lowered", "layoff", "lawsuit",
]

# --- Fear & Greed Index bands ---
FEAR_GREED_EXTREME_FEAR_MAX = 25
FEAR_GREED_FEAR_MAX = 45
FEAR_GREED_NEUTRAL_MAX = 55
FEAR_GREED_GREED_MAX = 75
FEAR_GREED_HISTORY_TAIL = 100

# --- VIX regime bands ---
VIX_EXTREME_FEAR_THRESHOLD = 40
VIX_HIGH_FEAR_THRESHOLD = 30
VIX_ELEVATED_THRESHOLD = 20
VIX_NORMAL_MIN_THRESHOLD = 15
VIX_HISTORY_TAIL = 60

# --- Inflation (CPI YoY %) bands ---
INFLATION_HIGH_THRESHOLD = 4
INFLATION_ELEVATED_THRESHOLD = 2
INFLATION_TARGET_MIN_THRESHOLD = 1

# --- Fed funds rate stance bands ---
FED_FUNDS_RESTRICTIVE_THRESHOLD = 4
FED_FUNDS_NEUTRAL_MIN_THRESHOLD = 2

# --- Analyst consensus score bands (5=strong buy .. 1=sell weighted average) ---
CONSENSUS_STRONG_BUY_THRESHOLD = 4.2
CONSENSUS_BUY_THRESHOLD = 3.5
CONSENSUS_HOLD_THRESHOLD = 2.5
RATING_CHANGES_LIMIT = 10

# --- News keyword-sentiment thresholds (also reused for the combined score) ---
NEWS_POSITIVE_THRESHOLD = 0.1
NEWS_NEGATIVE_THRESHOLD = -0.1

# --- Combined overall-sentiment score buckets ---
OVERALL_SENTIMENT_VERY_BULLISH_MIN = 2
OVERALL_SENTIMENT_BULLISH = 1
OVERALL_SENTIMENT_NEUTRAL = 0
OVERALL_SENTIMENT_BEARISH = -1


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


class SentimentAnalyzer:
    """Computes market-wide and ticker-specific sentiment indicators."""

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

    def get_fear_greed_index(self) -> Dict:
        """CNN's Fear & Greed Index: current score plus 100-day history.

        Needs a Referer header and a real browser User-Agent, or CNN returns HTTP 418.
        """
        empty = {
            "score": None, "rating": None, "signal": None,
            "previous_close": None, "one_week_ago": None,
            "one_month_ago": None, "one_year_ago": None,
            "historical_values": [],
        }

        try:
            response = requests.get(CNN_FEAR_GREED_URL, headers=CNN_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            current = data["fear_and_greed"]
            score = _clean(current.get("score"))

            signal = None
            if score is not None:
                if score < FEAR_GREED_EXTREME_FEAR_MAX:
                    signal = "extreme_fear"
                elif score < FEAR_GREED_FEAR_MAX:
                    signal = "fear"
                elif score <= FEAR_GREED_NEUTRAL_MAX:
                    signal = "neutral"
                elif score < FEAR_GREED_GREED_MAX:
                    signal = "greed"
                else:
                    signal = "extreme_greed"

            historical = []
            for point in data.get("fear_and_greed_historical", {}).get("data", [])[-FEAR_GREED_HISTORY_TAIL:]:
                historical.append({
                    "date": str(pd.to_datetime(point["x"], unit="ms").date()),
                    "score": _clean(point.get("y")),
                    "rating": point.get("rating"),
                })

            return {
                "score": score,
                "rating": current.get("rating"),
                "signal": signal,
                "previous_close": _clean(current.get("previous_close")),
                "one_week_ago": _clean(current.get("previous_1_week")),
                "one_month_ago": _clean(current.get("previous_1_month")),
                "one_year_ago": _clean(current.get("previous_1_year")),
                "historical_values": historical,
            }
        except Exception:
            return empty

    def get_vix_analysis(self) -> Dict:
        """VIX level, 20-day average/percentile, regime, and VIX/VIX3M term structure."""
        empty = {
            "current_vix": None, "vix_avg_20d": None, "vix_percentile": None,
            "vix_regime": None, "term_structure": None, "vix_history": [],
        }

        try:
            vix = yf.Ticker("^VIX").history(period="1y")["Close"].dropna()
            if vix.empty:
                return empty
            vix.index = vix.index.tz_localize(None).normalize()

            current_vix = _clean(vix.iloc[-1])
            vix_avg_20d = _clean(vix.tail(20).mean())
            vix_percentile = _clean((vix <= current_vix).mean() * 100)

            vix_regime = None
            if current_vix is not None:
                if current_vix > VIX_EXTREME_FEAR_THRESHOLD:
                    vix_regime = "extreme_fear"
                elif current_vix > VIX_HIGH_FEAR_THRESHOLD:
                    vix_regime = "high_fear"
                elif current_vix > VIX_ELEVATED_THRESHOLD:
                    vix_regime = "elevated"
                elif current_vix >= VIX_NORMAL_MIN_THRESHOLD:
                    vix_regime = "normal"
                else:
                    vix_regime = "complacent"

            # Contango (VIX3M > VIX) is normal; backwardation means near-term stress.
            term_structure = None
            try:
                vix3m = yf.Ticker("^VIX3M").history(period="1y")["Close"].dropna()
                vix3m.index = vix3m.index.tz_localize(None).normalize()
                aligned = pd.concat([vix.rename("vix"), vix3m.rename("vix3m")], axis=1, join="inner").dropna()
                if len(aligned):
                    last_vix, last_vix3m = aligned["vix"].iloc[-1], aligned["vix3m"].iloc[-1]
                    if last_vix3m > last_vix:
                        term_structure = "contango"
                    elif last_vix3m < last_vix:
                        term_structure = "backwardation"
                    else:
                        term_structure = "flat"
            except Exception:
                term_structure = None

            vix_history = [
                {"date": str(idx.date()), "vix": _clean(value)}
                for idx, value in vix.tail(VIX_HISTORY_TAIL).items()
            ]

            return {
                "current_vix": current_vix,
                "vix_avg_20d": vix_avg_20d,
                "vix_percentile": vix_percentile,
                "vix_regime": vix_regime,
                "term_structure": term_structure,
                "vix_history": vix_history,
            }
        except Exception:
            return empty

    def _fetch_fred_entry(self, series_id: str) -> Dict:
        """Fetch one FRED series; adds a yoy_pct field for CPIAUCSL only."""
        try:
            df = fetch_fred_series(series_id)
            current_value = _clean(df[series_id].iloc[-1])
            previous_value = _clean(df[series_id].iloc[-2]) if len(df) > 1 else None
            change = (
                current_value - previous_value
                if current_value is not None and previous_value is not None
                else None
            )

            entry = {
                "current_value": current_value,
                "previous_value": previous_value,
                "change": change,
                "date": str(df["observation_date"].iloc[-1]),
            }

            if series_id == "CPIAUCSL" and len(df) > CPI_YOY_LOOKBACK_MONTHS:
                year_ago = _clean(df[series_id].iloc[-(CPI_YOY_LOOKBACK_MONTHS + 1)])
                entry["yoy_pct"] = (
                    (current_value - year_ago) / year_ago * 100
                    if current_value is not None and year_ago else None
                )

            return entry
        except Exception:
            return {
                "current_value": None, "previous_value": None,
                "change": None, "date": None,
            }

    def _yield_curve_signal(self, yield_spread: Optional[float]) -> Optional[str]:
        """Classify the 10Y-2Y spread (T10Y2Y) as inverted/flat/normal."""
        if yield_spread is None:
            return None
        if yield_spread < 0:
            return "inverted"
        if yield_spread <= 0.5:
            return "flat"
        return "normal"

    def _inflation_signal(self, cpi_yoy: Optional[float]) -> Optional[str]:
        """Classify YoY CPI inflation as high/elevated/target/low."""
        if cpi_yoy is None:
            return None
        if cpi_yoy > INFLATION_HIGH_THRESHOLD:
            return "high"
        if cpi_yoy > INFLATION_ELEVATED_THRESHOLD:
            return "elevated"
        if cpi_yoy > INFLATION_TARGET_MIN_THRESHOLD:
            return "target"
        return "low"

    def _fed_stance_signal(self, fed_funds: Optional[float]) -> Optional[str]:
        """Classify the Fed funds rate as restrictive/neutral/accommodative."""
        if fed_funds is None:
            return None
        if fed_funds > FED_FUNDS_RESTRICTIVE_THRESHOLD:
            return "restrictive"
        if fed_funds >= FED_FUNDS_NEUTRAL_MIN_THRESHOLD:
            return "neutral"
        return "accommodative"

    def get_macro_indicators(self) -> Dict:
        """Fetches all FRED macro series and derives yield-curve/inflation/Fed signals from them."""
        series_results = {}
        for series_id in FRED_SERIES:
            series_results[series_id] = self._fetch_fred_entry(series_id)
            time.sleep(FRED_REQUEST_DELAY_SECONDS)

        yield_spread = series_results.get("T10Y2Y", {}).get("current_value")
        cpi_yoy = series_results.get("CPIAUCSL", {}).get("yoy_pct")
        fed_funds = series_results.get("FEDFUNDS", {}).get("current_value")

        return {
            "series": series_results,
            "yield_curve_signal": self._yield_curve_signal(yield_spread),
            "inflation_signal": self._inflation_signal(cpi_yoy),
            "fed_signal": self._fed_stance_signal(fed_funds),
        }

    def get_analyst_ratings(self) -> Dict:
        """Analyst ratings, weighted consensus, price targets, and recent rating changes.

        Remaps yfinance's sell/strongSell buckets onto underperform/sell.
        """
        result = {
            "ratings_breakdown": None, "consensus_score": None, "consensus_label": None,
            "price_targets": None, "last_10_rating_changes": [],
        }

        try:
            rec = self._stock.recommendations
            if rec is not None and not rec.empty:
                current = rec[rec["period"] == "0m"]
                row = current.iloc[0] if len(current) else rec.iloc[0]

                breakdown = {
                    "strong_buy": int(row.get("strongBuy", 0)),
                    "buy": int(row.get("buy", 0)),
                    "hold": int(row.get("hold", 0)),
                    "underperform": int(row.get("sell", 0)),
                    "sell": int(row.get("strongSell", 0)),
                }
                result["ratings_breakdown"] = breakdown

                weights = {"strong_buy": 5, "buy": 4, "hold": 3, "underperform": 2, "sell": 1}
                total = sum(breakdown.values())
                if total > 0:
                    consensus = sum(breakdown[k] * weights[k] for k in weights) / total
                    result["consensus_score"] = _clean(consensus)

                    if consensus > CONSENSUS_STRONG_BUY_THRESHOLD:
                        result["consensus_label"] = "Strong Buy"
                    elif consensus > CONSENSUS_BUY_THRESHOLD:
                        result["consensus_label"] = "Buy"
                    elif consensus > CONSENSUS_HOLD_THRESHOLD:
                        result["consensus_label"] = "Hold"
                    else:
                        result["consensus_label"] = "Sell"
        except Exception:
            pass

        try:
            targets = self._stock.analyst_price_targets
            if targets:
                current_price = _clean(targets.get("current"))
                mean_target = _clean(targets.get("mean"))
                upside = None
                if current_price and mean_target is not None:
                    upside = (mean_target - current_price) / current_price * 100

                result["price_targets"] = {
                    "mean_target": mean_target,
                    "high_target": _clean(targets.get("high")),
                    "low_target": _clean(targets.get("low")),
                    "current_price": current_price,
                    "upside_from_current": _clean(upside),
                }
        except Exception:
            pass

        try:
            ud = self._stock.upgrades_downgrades
            if ud is not None and not ud.empty:
                ud = ud.sort_index(ascending=False).head(RATING_CHANGES_LIMIT)
                for grade_date, row in ud.iterrows():
                    result["last_10_rating_changes"].append({
                        "firm": row.get("Firm"),
                        "from_grade": row.get("FromGrade"),
                        "to_grade": row.get("ToGrade"),
                        "action": row.get("Action"),
                        "date": str(grade_date.date()) if hasattr(grade_date, "date") else str(grade_date),
                    })
        except Exception:
            pass

        return result

    def _extract_news_fields(self, article: dict):
        """Pull title/publisher/link/publish_time out of yfinance's nested news schema."""
        content = article.get("content", article)
        title = content.get("title")
        publisher = (content.get("provider") or {}).get("displayName") or article.get("publisher")
        link = (
            (content.get("canonicalUrl") or {}).get("url")
            or (content.get("clickThroughUrl") or {}).get("url")
            or article.get("link")
        )
        publish_time = content.get("pubDate") or article.get("providerPublishTime")
        return title, publisher, link, publish_time

    def get_news_sentiment(self) -> Dict:
        """Keyword-based sentiment score across recent news headlines (not VADER, see module docstring)."""
        result = {
            "articles": [], "aggregate_sentiment": None,
            "positive_count": 0, "negative_count": 0, "neutral_count": 0,
            "sentiment_label": None,
        }

        try:
            news = self._stock.news or []
        except Exception:
            news = []

        scores = []
        for article in news:
            try:
                title, publisher, link, publish_time = self._extract_news_fields(article)
                if not title:
                    continue

                words = title.lower().split()
                pos = sum(1 for w in words if any(kw in w for kw in POSITIVE_WORDS))
                neg = sum(1 for w in words if any(kw in w for kw in NEGATIVE_WORDS))
                raw_score = pos - neg
                denom = pos + neg
                sentiment_score = raw_score / denom if denom else 0.0

                scores.append(sentiment_score)
                if sentiment_score > NEWS_POSITIVE_THRESHOLD:
                    result["positive_count"] += 1
                elif sentiment_score < NEWS_NEGATIVE_THRESHOLD:
                    result["negative_count"] += 1
                else:
                    result["neutral_count"] += 1

                result["articles"].append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "publish_time": publish_time,
                    "sentiment_score": _clean(sentiment_score),
                })
            except Exception:
                continue

        if scores:
            avg = sum(scores) / len(scores)
            result["aggregate_sentiment"] = _clean(avg)
            if avg > NEWS_POSITIVE_THRESHOLD:
                result["sentiment_label"] = "Positive"
            elif avg < NEWS_NEGATIVE_THRESHOLD:
                result["sentiment_label"] = "Negative"
            else:
                result["sentiment_label"] = "Neutral"

        return result

    def get_sector_performance(self) -> Dict:
        """1-week/1-month return for all sector ETFs, ranked, plus this ticker's sector rank."""
        result = {
            "sector_returns": [], "ticker_sector": None,
            "ticker_sector_etf_performance": None, "sector_rank": None,
        }

        performances = []
        for etf, name in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period="1mo")["Close"].dropna()
                if len(hist) < 2:
                    continue
                one_month_return = (hist.iloc[-1] / hist.iloc[0] - 1) * 100
                one_week_slice = hist.tail(6)
                one_week_return = (
                    (one_week_slice.iloc[-1] / one_week_slice.iloc[0] - 1) * 100
                    if len(one_week_slice) > 1 else None
                )
                performances.append({
                    "etf": etf,
                    "sector": name,
                    "one_week_return": _clean(one_week_return),
                    "one_month_return": _clean(one_month_return),
                })
            except Exception:
                continue

        performances.sort(key=lambda p: (p["one_month_return"] if p["one_month_return"] is not None else -999), reverse=True)
        for rank, p in enumerate(performances, start=1):
            p["rank"] = rank
        result["sector_returns"] = performances

        try:
            sector_name = self.info.get("sector")
            result["ticker_sector"] = sector_name
            etf = SECTOR_TO_ETF.get(sector_name)
            if etf:
                match = next((p for p in performances if p["etf"] == etf), None)
                if match:
                    result["ticker_sector_etf_performance"] = match
                    result["sector_rank"] = match["rank"]
        except Exception:
            pass

        return result

    def _compute_overall_sentiment_signal(
        self, fear_greed: Optional[Dict], vix: Optional[Dict],
        analyst_ratings: Optional[Dict], news_sentiment: Optional[Dict], macro: Optional[Dict],
    ) -> str:
        """Tally +1/-1 votes across Fear & Greed, VIX, analyst consensus, news, and yield curve."""
        score = 0

        fg_score = fear_greed.get("score") if fear_greed else None
        if fg_score is not None:
            if fg_score > FEAR_GREED_NEUTRAL_MAX:
                score += 1
            elif fg_score < FEAR_GREED_FEAR_MAX:
                score -= 1

        current_vix = vix.get("current_vix") if vix else None
        if current_vix is not None:
            if current_vix < VIX_ELEVATED_THRESHOLD:
                score += 1
            elif current_vix > VIX_HIGH_FEAR_THRESHOLD:
                score -= 1

        consensus_label = analyst_ratings.get("consensus_label") if analyst_ratings else None
        if consensus_label in ("Strong Buy", "Buy"):
            score += 1
        elif consensus_label in ("Hold", "Sell"):
            score -= 1

        news_score = news_sentiment.get("aggregate_sentiment") if news_sentiment else None
        if news_score is not None:
            if news_score > NEWS_POSITIVE_THRESHOLD:
                score += 1
            elif news_score < NEWS_NEGATIVE_THRESHOLD:
                score -= 1

        yield_curve_signal = macro.get("yield_curve_signal") if macro else None
        if yield_curve_signal is not None:
            if yield_curve_signal != "inverted":
                score += 1
            else:
                score -= 1

        if score >= OVERALL_SENTIMENT_VERY_BULLISH_MIN:
            return "Very Bullish"
        if score == OVERALL_SENTIMENT_BULLISH:
            return "Bullish"
        if score == OVERALL_SENTIMENT_NEUTRAL:
            return "Neutral"
        if score == OVERALL_SENTIMENT_BEARISH:
            return "Bearish"
        return "Very Bearish"

    def get_full_sentiment_analysis(self) -> Dict:
        """Aggregates Fear & Greed, VIX, macro, analyst ratings, news, and sector performance.

        Each piece is fetched independently so one failing source doesn't break the rest.
        """
        try:
            fear_greed = self.get_fear_greed_index()
        except Exception:
            fear_greed = None

        try:
            vix = self.get_vix_analysis()
        except Exception:
            vix = None

        try:
            macro = self.get_macro_indicators()
        except Exception:
            macro = None

        try:
            analyst_ratings = self.get_analyst_ratings()
        except Exception:
            analyst_ratings = None

        try:
            news_sentiment = self.get_news_sentiment()
        except Exception:
            news_sentiment = None

        try:
            sector_performance = self.get_sector_performance()
        except Exception:
            sector_performance = None

        return {
            "ticker": self.ticker,
            "fear_greed": fear_greed,
            "vix": vix,
            "macro": macro,
            "analyst_ratings": analyst_ratings,
            "news_sentiment": news_sentiment,
            "sector_performance": sector_performance,
            "overall_sentiment_signal": self._compute_overall_sentiment_signal(
                fear_greed, vix, analyst_ratings, news_sentiment, macro
            ),
        }
