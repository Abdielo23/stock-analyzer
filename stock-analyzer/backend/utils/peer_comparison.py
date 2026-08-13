"""Ranks a ticker against real peers pulled from its sector ETF's top holdings."""

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf

from utils.sector_benchmarks import SectorBenchmarks

CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_PEERS = 10
YFINANCE_DEBT_TO_EQUITY_SCALE = 100.0

TOP_QUARTILE_THRESHOLD = 75
ABOVE_AVERAGE_THRESHOLD = 50
BELOW_AVERAGE_THRESHOLD = 25
STRONGEST_WEAKEST_COUNT = 3

# yfinance info field name for each metric.
METRIC_FIELDS = {
    "pe": "trailingPE",
    "forward_pe": "forwardPE",
    "ev_ebitda": "enterpriseToEbitda",
    "price_book": "priceToBook",
    "roe": "returnOnEquity",
    "roa": "returnOnAssets",
    "net_margin": "profitMargins",
    "debt_equity": "debtToEquity",
    "beta": "beta",
}

# Lower is better for these (cheap valuation, less debt) — percentile is inverted so a higher label still means better.
LOWER_IS_BETTER = {"pe", "forward_pe", "ev_ebitda", "price_book", "debt_equity"}


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


class PeerComparison:
    """Identifies a ticker's real sector peers and ranks it against them."""

    _cache: Dict[str, dict] = {}

    def __init__(self):
        self._benchmarks = SectorBenchmarks()

    def _cache_get(self, key: str) -> Optional[list]:
        entry = self._cache.get(key)
        if entry and time.time() - entry["timestamp"] < CACHE_TTL_SECONDS:
            return entry["data"]
        return None

    def _cache_set(self, key: str, data: list) -> None:
        self._cache[key] = {"data": data, "timestamp": time.time()}

    def get_sector_peers(self, ticker: str, max_peers: int = DEFAULT_MAX_PEERS) -> List[str]:
        """Top holdings of this ticker's sector ETF, excluding the ticker itself."""
        ticker = ticker.upper()
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}
        sector = info.get("sector")
        etf_symbol = self._benchmarks.get_sector_etf(sector)

        cache_key = f"peer_pool:{etf_symbol}"
        pool = self._cache_get(cache_key)
        if pool is None:
            try:
                top = yf.Ticker(etf_symbol).funds_data.top_holdings
                pool = [str(t) for t in top.index]
            except Exception:
                pool = []
            self._cache_set(cache_key, pool)

        return [t for t in pool if t != ticker][:max_peers]

    def get_peer_metrics(self, peers: List[str]) -> Dict:
        """Median/mean/min/max for each metric across the peer group."""
        raw: Dict[str, List[Tuple[str, float]]] = {key: [] for key in METRIC_FIELDS}

        for peer in peers:
            try:
                info = yf.Ticker(peer).info or {}
            except Exception:
                continue
            for key, field in METRIC_FIELDS.items():
                value = _clean(info.get(field))
                if value is None:
                    continue
                if key == "debt_equity":
                    value = value / YFINANCE_DEBT_TO_EQUITY_SCALE
                raw[key].append((peer, value))

        result = {}
        for key, pairs in raw.items():
            if not pairs:
                result[key] = {"peer_median": None, "peer_mean": None, "peer_min": None, "peer_max": None, "peer_list": []}
                continue
            values = [v for _, v in pairs]
            result[key] = {
                "peer_median": float(np.median(values)),
                "peer_mean": float(np.mean(values)),
                "peer_min": float(np.min(values)),
                "peer_max": float(np.max(values)),
                "peer_list": sorted(pairs, key=lambda p: p[1]),
            }
        return result

    def _percentile_label(self, percentile_rank: float) -> str:
        """Classify a percentile rank into Top Quartile/Above Average/Below Average/Bottom Quartile."""
        if percentile_rank > TOP_QUARTILE_THRESHOLD:
            return "Top Quartile"
        if percentile_rank > ABOVE_AVERAGE_THRESHOLD:
            return "Above Average"
        if percentile_rank > BELOW_AVERAGE_THRESHOLD:
            return "Below Average"
        return "Bottom Quartile"

    def rank_vs_peers(self, ticker: str, peers: List[str]) -> Dict:
        """Rank one ticker's metrics against its peer group; percentile_rank is % of peers it beats."""
        ticker = ticker.upper()
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}

        peer_metrics = self.get_peer_metrics(peers)

        rankings = {}
        for key, field in METRIC_FIELDS.items():
            ticker_value = _clean(info.get(field))
            if key == "debt_equity" and ticker_value is not None:
                ticker_value = ticker_value / YFINANCE_DEBT_TO_EQUITY_SCALE

            peer_data = peer_metrics.get(key, {})
            peer_list = peer_data.get("peer_list", [])

            if ticker_value is None or not peer_list:
                rankings[key] = {
                    "ticker_value": ticker_value, "peer_median": peer_data.get("peer_median"),
                    "percentile_rank": None, "label": None, "better_than": None,
                }
                continue

            peer_values = [v for _, v in peer_list]
            n = len(peer_values)
            if key in LOWER_IS_BETTER:
                better_count = sum(1 for v in peer_values if v > ticker_value)
            else:
                better_count = sum(1 for v in peer_values if v < ticker_value)
            percentile_rank = round(better_count / n * 100, 1)

            rankings[key] = {
                "ticker_value": ticker_value,
                "peer_median": peer_data.get("peer_median"),
                "percentile_rank": percentile_rank,
                "label": self._percentile_label(percentile_rank),
                "better_than": f"{better_count} out of {n} peers",
            }

        valid_ranks = [r["percentile_rank"] for r in rankings.values() if r["percentile_rank"] is not None]
        overall_peer_rank = round(sum(valid_ranks) / len(valid_ranks), 1) if valid_ranks else None

        ranked_metrics = sorted(
            ((k, r["percentile_rank"]) for k, r in rankings.items() if r["percentile_rank"] is not None),
            key=lambda x: x[1], reverse=True,
        )
        strongest_vs_peers = [k for k, _ in ranked_metrics[:STRONGEST_WEAKEST_COUNT]]
        weakest_vs_peers = [k for k, _ in ranked_metrics[-STRONGEST_WEAKEST_COUNT:]] if ranked_metrics else []

        return {
            "ticker": ticker,
            "peers_used": peers,
            "rankings": rankings,
            "overall_peer_rank": overall_peer_rank,
            "strongest_vs_peers": strongest_vs_peers,
            "weakest_vs_peers": weakest_vs_peers,
        }
