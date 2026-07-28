"""Sector benchmarks computed live from each sector ETF's top-10 holdings, instead of hardcoded averages.

Two quirks: sector ETFs don't carry usable P/E-style fields themselves (their
Morningstar-derived values are miscalibrated), so we fetch each top holding's
own `.info` and take the median. And yfinance's raw `debtToEquity` is on a
0-100 scale, not a ratio, so it's divided by 100 to match ROE/ROA/margins.
"""

import time
from typing import Dict, List, Optional

import numpy as np
import yfinance as yf

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",  # yfinance's real sector string for this category
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Basic Materials": "XLB",  # yfinance's real sector string for this category
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",  # yfinance's real sector string for this category
    "Communication Services": "XLC",
    "Default": "SPY",
}

CACHE_TTL_SECONDS = 24 * 60 * 60
TOP_N_HOLDINGS = 10
AT_MEDIAN_TOLERANCE_PCT = 1.0
YFINANCE_DEBT_TO_EQUITY_SCALE = 100.0


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


class SectorBenchmarks:
    """Computes real, live sector-average valuation multiples and fundamentals.

    Caches are class-level so every analyzer instance shares the same fetch instead of refetching per-instance.
    """

    _cache: Dict[str, dict] = {}

    def _cache_get(self, key: str) -> Optional[dict]:
        entry = self._cache.get(key)
        if entry and time.time() - entry["timestamp"] < CACHE_TTL_SECONDS:
            return entry["data"]
        return None

    def _cache_set(self, key: str, data: dict) -> None:
        self._cache[key] = {"data": data, "timestamp": time.time()}

    def get_sector_etf(self, sector: Optional[str]) -> str:
        """Match a sector string to its ETF, falling back to SPY (yfinance's sector names aren't always exact)."""
        if not sector:
            return SECTOR_ETFS["Default"]
        if sector in SECTOR_ETFS:
            return SECTOR_ETFS[sector]

        normalized = sector.lower().strip()
        for name, etf in SECTOR_ETFS.items():
            if name == "Default":
                continue
            name_lower = name.lower()
            if name_lower in normalized or normalized in name_lower:
                return etf
        return SECTOR_ETFS["Default"]

    def _fetch_top_holdings(self, etf_symbol: str) -> List[str]:
        """Top `TOP_N_HOLDINGS` holding tickers for a sector ETF, or [] on failure."""
        try:
            top = yf.Ticker(etf_symbol).funds_data.top_holdings
            return [str(t) for t in top.index[:TOP_N_HOLDINGS]]
        except Exception:
            return []

    def get_sector_multiples(self, sector: str) -> Dict:
        """Median P/E, Forward P/E, Price/Book, and EV/EBITDA across the sector ETF's top 10 holdings."""
        etf_symbol = self.get_sector_etf(sector)
        cache_key = f"multiples:{etf_symbol}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        holdings = self._fetch_top_holdings(etf_symbol)
        pes, forward_pes, pbs, ev_ebitdas = [], [], [], []
        for holding in holdings:
            try:
                info = yf.Ticker(holding).info or {}
            except Exception:
                continue
            pe = _clean(info.get("trailingPE"))
            forward_pe = _clean(info.get("forwardPE"))
            pb = _clean(info.get("priceToBook"))
            ev_ebitda = _clean(info.get("enterpriseToEbitda"))
            if pe is not None:
                pes.append(pe)
            if forward_pe is not None:
                forward_pes.append(forward_pe)
            if pb is not None:
                pbs.append(pb)
            if ev_ebitda is not None:
                ev_ebitdas.append(ev_ebitda)

        result = {
            "pe": float(np.median(pes)) if pes else None,
            "forward_pe": float(np.median(forward_pes)) if forward_pes else None,
            "pb": float(np.median(pbs)) if pbs else None,
            "ev_ebitda": float(np.median(ev_ebitdas)) if ev_ebitdas else None,
            "source": "dynamic",
            "etf": etf_symbol,
            "as_of": time.time(),
        }
        self._cache_set(cache_key, result)
        return result

    def get_sector_fundamentals(self, sector: str) -> Dict:
        """Median ROE/ROA/margins/debt-equity across the sector ETF's top 10 holdings."""
        etf_symbol = self.get_sector_etf(sector)
        cache_key = f"fundamentals:{etf_symbol}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        holdings = self._fetch_top_holdings(etf_symbol)
        roes, roas, gross_margins, operating_margins, debt_equities = [], [], [], [], []
        holdings_used = []

        for holding in holdings:
            try:
                info = yf.Ticker(holding).info or {}
            except Exception:
                continue

            roe = _clean(info.get("returnOnEquity"))
            roa = _clean(info.get("returnOnAssets"))
            gross_margin = _clean(info.get("grossMargins"))
            operating_margin = _clean(info.get("operatingMargins"))
            debt_equity_raw = _clean(info.get("debtToEquity"))
            debt_equity = debt_equity_raw / YFINANCE_DEBT_TO_EQUITY_SCALE if debt_equity_raw is not None else None

            used_this_holding = False
            if roe is not None:
                roes.append(roe)
                used_this_holding = True
            if roa is not None:
                roas.append(roa)
                used_this_holding = True
            if gross_margin is not None:
                gross_margins.append(gross_margin)
                used_this_holding = True
            if operating_margin is not None:
                operating_margins.append(operating_margin)
                used_this_holding = True
            if debt_equity is not None:
                debt_equities.append(debt_equity)
                used_this_holding = True
            if used_this_holding:
                holdings_used.append(holding)

        result = {
            "median_roe": float(np.median(roes)) if roes else None,
            "median_roa": float(np.median(roas)) if roas else None,
            "median_gross_margin": float(np.median(gross_margins)) if gross_margins else None,
            "median_operating_margin": float(np.median(operating_margins)) if operating_margins else None,
            "median_debt_equity": float(np.median(debt_equities)) if debt_equities else None,
            "sample_size": len(holdings_used),
            "source": "dynamic",
            "holdings_used": holdings_used,
        }
        self._cache_set(cache_key, result)
        return result

    def _rank_label(self, pct_vs_sector: float) -> str:
        """Classify a ticker's % difference from the sector median."""
        if abs(pct_vs_sector) < AT_MEDIAN_TOLERANCE_PCT:
            return "at_median"
        return "above_median" if pct_vs_sector > 0 else "below_median"

    def compare_to_sector(self, ticker: str, sector: str) -> Dict:
        """Compare one ticker's ROE/ROA/margins/debt-equity to its real sector medians."""
        try:
            info = yf.Ticker(ticker.upper()).info or {}
        except Exception:
            info = {}

        medians = self.get_sector_fundamentals(sector)

        ticker_debt_equity_raw = _clean(info.get("debtToEquity"))
        ticker_debt_equity = (
            ticker_debt_equity_raw / YFINANCE_DEBT_TO_EQUITY_SCALE if ticker_debt_equity_raw is not None else None
        )

        metrics = {
            "roe": (_clean(info.get("returnOnEquity")), medians.get("median_roe")),
            "roa": (_clean(info.get("returnOnAssets")), medians.get("median_roa")),
            "gross_margin": (_clean(info.get("grossMargins")), medians.get("median_gross_margin")),
            "operating_margin": (_clean(info.get("operatingMargins")), medians.get("median_operating_margin")),
            "debt_equity": (ticker_debt_equity, medians.get("median_debt_equity")),
        }

        result = {}
        for key, (ticker_value, sector_median) in metrics.items():
            if ticker_value is None or sector_median is None or sector_median == 0:
                result[key] = {
                    "ticker_value": ticker_value, "sector_median": sector_median,
                    "vs_sector": None, "rank": None,
                }
                continue
            pct_vs_sector = (ticker_value - sector_median) / abs(sector_median) * 100
            result[key] = {
                "ticker_value": ticker_value,
                "sector_median": sector_median,
                "vs_sector": f"{'+' if pct_vs_sector >= 0 else ''}{pct_vs_sector:.0f}%",
                "rank": self._rank_label(pct_vs_sector),
            }

        return result
