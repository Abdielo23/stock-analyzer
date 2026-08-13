"""Module 5 — Volume & Flow.

OBV, Accumulation/Distribution, Chaikin Money Flow, Volume Profile, VWAP, and relative volume, all from yfinance daily OHLCV history.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# --- OBV / Accumulation-Distribution ---
FLOW_SMA_PERIOD = 20
DIVERGENCE_LOOKBACK_DAYS = 10

# --- Chaikin Money Flow ---
CMF_ROLLING_PERIOD = 20
CMF_STRONG_THRESHOLD = 0.25

# --- Volume Profile ---
VOLUME_PROFILE_BUCKETS = 20
VALUE_AREA_VOLUME_PCT = 0.70
POC_PROXIMITY_PCT = 0.005

# --- VWAP / Relative Volume ---
RVOL_AVG_WINDOW_DAYS = 20
RVOL_VERY_HIGH_THRESHOLD = 2.0
RVOL_HIGH_THRESHOLD = 1.5
RVOL_NORMAL_MIN_THRESHOLD = 0.75

HISTORY_TAIL = 100


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


def _last(series: Optional[pd.Series]) -> Optional[float]:
    """The most recent value of a Series, or None if it's empty/missing."""
    if series is None or len(series) == 0:
        return None
    return _clean(series.iloc[-1])


def _records(df: pd.DataFrame, columns: List[str]) -> List[dict]:
    """Convert selected columns of a DataFrame to a list of dicts with a string 'date' field."""
    subset = df[columns].reset_index()
    subset.columns = [str(c) for c in subset.columns]
    date_col = subset.columns[0]
    subset = subset.rename(columns={date_col: "date"})
    subset["date"] = subset["date"].astype(str)
    records = subset.to_dict(orient="records")
    return [{k: (_clean(v) if k != "date" else v) for k, v in row.items()} for row in records]


class VolumeAnalyzer:
    """Computes volume/money-flow indicators for one ticker."""

    def __init__(self, ticker: str, period: str = "1y"):
        self.ticker = ticker.upper()
        self.period = period
        self._stock = yf.Ticker(self.ticker)
        history = self._stock.history(period=period)
        # yfinance can add a placeholder row for today's still-open session with NaN prices, so drop it.
        self.df = history[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
        self._money_flow_volume = None

    @property
    def money_flow_volume(self) -> pd.Series:
        """Lazily-computed, cached Money Flow Volume series (feeds A/D and CMF)."""
        if self._money_flow_volume is None:
            high, low, close, volume = self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"]
            price_range = high - low
            mfm = ((close - low) - (high - close)) / price_range
            mfm = mfm.where(price_range != 0, 0.0)
            self._money_flow_volume = mfm * volume
        return self._money_flow_volume

    def get_obv(self) -> Dict:
        """On-Balance Volume plus a 10-day signal comparing OBV direction to price direction."""
        close, volume = self.df["Close"], self.df["Volume"]

        direction = np.where(close.diff() > 0, 1, np.where(close.diff() < 0, -1, 0))
        obv = pd.Series(direction, index=self.df.index) * volume
        obv = obv.cumsum()
        obv_sma20 = obv.rolling(FLOW_SMA_PERIOD).mean()

        current_obv = _last(obv)
        obv_10d_ago = _clean(obv.shift(DIVERGENCE_LOOKBACK_DAYS).iloc[-1]) if len(obv) > DIVERGENCE_LOOKBACK_DAYS else None
        current_price = _last(close)
        price_10d_ago = _clean(close.shift(DIVERGENCE_LOOKBACK_DAYS).iloc[-1]) if len(close) > DIVERGENCE_LOOKBACK_DAYS else None

        obv_signal = None
        if None not in (current_obv, obv_10d_ago, current_price, price_10d_ago):
            obv_up = current_obv > obv_10d_ago
            obv_down = current_obv < obv_10d_ago
            price_up = current_price > price_10d_ago
            price_down = current_price < price_10d_ago

            if obv_up and price_up:
                obv_signal = "bullish"
            elif obv_down and price_down:
                obv_signal = "bearish"
            elif obv_up and price_down:
                obv_signal = "divergence_bullish"
            elif obv_down and price_up:
                obv_signal = "divergence_bearish"
            else:
                obv_signal = "neutral"

        history_df = self.df.copy()
        history_df["OBV"] = obv
        history_df["OBV_SMA20"] = obv_sma20

        try:
            obv_history = _records(history_df, ["OBV", "OBV_SMA20"])[-HISTORY_TAIL:]
        except Exception:
            obv_history = []

        return {
            "current_obv": current_obv,
            "obv_10d_ago": obv_10d_ago,
            "obv_signal": obv_signal,
            "obv_history": obv_history,
        }

    def get_accumulation_distribution(self) -> Dict:
        """Accumulation/Distribution line and its 10-day trend signal."""
        mfv = self.money_flow_volume
        ad = mfv.cumsum()
        ad_sma20 = ad.rolling(FLOW_SMA_PERIOD).mean()

        current_ad = _last(ad)
        ad_10d_ago = _clean(ad.shift(DIVERGENCE_LOOKBACK_DAYS).iloc[-1]) if len(ad) > DIVERGENCE_LOOKBACK_DAYS else None

        ad_signal = None
        if current_ad is not None and ad_10d_ago is not None:
            if current_ad > ad_10d_ago:
                ad_signal = "accumulation"
            elif current_ad < ad_10d_ago:
                ad_signal = "distribution"
            else:
                ad_signal = "neutral"

        history_df = self.df.copy()
        history_df["AD"] = ad
        history_df["AD_SMA20"] = ad_sma20

        try:
            ad_history = _records(history_df, ["AD", "AD_SMA20"])[-HISTORY_TAIL:]
        except Exception:
            ad_history = []

        return {
            "current_ad": current_ad,
            "ad_signal": ad_signal,
            "ad_history": ad_history,
        }

    def get_chaikin_money_flow(self) -> Dict:
        """20-day Chaikin Money Flow; signal is strong/normal buying or selling based on CMF_STRONG_THRESHOLD."""
        volume = self.df["Volume"]
        mfv = self.money_flow_volume

        cmf_series = mfv.rolling(CMF_ROLLING_PERIOD).sum() / volume.rolling(CMF_ROLLING_PERIOD).sum()
        cmf_value = _last(cmf_series)

        cmf_signal = None
        if cmf_value is not None:
            if cmf_value > CMF_STRONG_THRESHOLD:
                cmf_signal = "strong_buying"
            elif cmf_value > 0:
                cmf_signal = "buying"
            elif cmf_value < -CMF_STRONG_THRESHOLD:
                cmf_signal = "strong_selling"
            elif cmf_value < 0:
                cmf_signal = "selling"
            else:
                cmf_signal = "neutral"

        return {"cmf_value": cmf_value, "cmf_signal": cmf_signal}

    def _bucket_volume_by_price(
        self, typical_price: pd.Series, volume: pd.Series, price_min: float, price_max: float
    ) -> Tuple[List[float], np.ndarray]:
        """Bins traded volume into `VOLUME_PROFILE_BUCKETS` equal price ranges."""
        edges = np.linspace(price_min, price_max, VOLUME_PROFILE_BUCKETS + 1)
        bucket_idx = np.clip(np.digitize(typical_price, edges) - 1, 0, VOLUME_PROFILE_BUCKETS - 1)

        bucket_volume = np.zeros(VOLUME_PROFILE_BUCKETS)
        for idx, vol in zip(bucket_idx, volume.values):
            bucket_volume[idx] += vol

        price_levels = [(edges[i] + edges[i + 1]) / 2 for i in range(VOLUME_PROFILE_BUCKETS)]
        return price_levels, bucket_volume

    def _expand_value_area(self, bucket_volume: np.ndarray, poc_idx: int) -> Tuple[int, int]:
        """Expands outward from the POC bucket until `VALUE_AREA_VOLUME_PCT` of volume is captured."""
        num_buckets = len(bucket_volume)
        total_volume = bucket_volume.sum()
        target_volume = VALUE_AREA_VOLUME_PCT * total_volume

        low_idx, high_idx = poc_idx, poc_idx
        cum_volume = bucket_volume[poc_idx]
        while cum_volume < target_volume and (low_idx > 0 or high_idx < num_buckets - 1):
            vol_below = bucket_volume[low_idx - 1] if low_idx > 0 else -1
            vol_above = bucket_volume[high_idx + 1] if high_idx < num_buckets - 1 else -1
            if vol_above >= vol_below:
                high_idx += 1
                cum_volume += bucket_volume[high_idx]
            else:
                low_idx -= 1
                cum_volume += bucket_volume[low_idx]

        return low_idx, high_idx

    def get_volume_profile(self) -> Dict:
        """Volume-by-price profile: Point of Control (POC) and 70% Value Area (VAH/VAL)."""
        high, low, close, volume = self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"]
        typical_price = (high + low + close) / 3

        price_min, price_max = float(low.min()), float(high.max())
        if price_min == price_max or np.isnan(price_min) or np.isnan(price_max):
            return {
                "poc_price": None, "vah": None, "val": None,
                "price_vs_poc": None, "volume_buckets": [],
            }

        price_levels, bucket_volume = self._bucket_volume_by_price(typical_price, volume, price_min, price_max)

        poc_idx = int(np.argmax(bucket_volume))
        poc_price = price_levels[poc_idx]

        low_idx, high_idx = self._expand_value_area(bucket_volume, poc_idx)
        vah = price_levels[high_idx]
        val = price_levels[low_idx]

        current_price = _last(close)
        price_vs_poc = None
        if current_price is not None:
            distance = (current_price - poc_price) / poc_price
            if abs(distance) <= POC_PROXIMITY_PCT:
                price_vs_poc = "at"
            elif distance > 0:
                price_vs_poc = "above"
            else:
                price_vs_poc = "below"

        volume_buckets = [
            {
                "price_level": _clean(price_levels[i]),
                "volume": _clean(bucket_volume[i]),
                "is_poc": i == poc_idx,
            }
            for i in range(VOLUME_PROFILE_BUCKETS)
        ]

        return {
            "poc_price": _clean(poc_price),
            "vah": _clean(vah),
            "val": _clean(val),
            "price_vs_poc": price_vs_poc,
            "volume_buckets": volume_buckets,
        }

    def get_vwap_analysis(self) -> Dict:
        """Session-cumulative VWAP, its +/-1 std bands, and price distance from it."""
        high, low, close, volume = self.df["High"], self.df["Low"], self.df["Close"], self.df["Volume"]
        typical_price = (high + low + close) / 3

        total_volume = volume.sum()
        if total_volume == 0:
            return {
                "vwap": None, "vwap_upper": None, "vwap_lower": None,
                "signal": None, "distance_pct": None,
            }

        vwap = float((typical_price * volume).sum() / total_volume)
        std = float(typical_price.std())
        vwap_upper = vwap + std
        vwap_lower = vwap - std

        current_price = _last(close)
        signal = None
        distance_pct = None
        if current_price is not None:
            signal = "above_vwap" if current_price > vwap else "below_vwap"
            distance_pct = (current_price - vwap) / vwap * 100

        return {
            "vwap": _clean(vwap),
            "vwap_upper": _clean(vwap_upper),
            "vwap_lower": _clean(vwap_lower),
            "signal": signal,
            "distance_pct": _clean(distance_pct),
        }

    def get_relative_volume(self) -> Dict:
        """Today's volume vs. its `RVOL_AVG_WINDOW_DAYS`-day average."""
        volume = self.df["Volume"]

        today_volume = _last(volume)
        avg_volume_20d = (
            _clean(volume.rolling(RVOL_AVG_WINDOW_DAYS).mean().iloc[-1])
            if len(volume) >= RVOL_AVG_WINDOW_DAYS else None
        )

        rvol = None
        signal = None
        if today_volume is not None and avg_volume_20d:
            rvol = today_volume / avg_volume_20d
            if rvol > RVOL_VERY_HIGH_THRESHOLD:
                signal = "very_high"
            elif rvol > RVOL_HIGH_THRESHOLD:
                signal = "high"
            elif rvol >= RVOL_NORMAL_MIN_THRESHOLD:
                signal = "normal"
            else:
                signal = "low"

        return {
            "today_volume": today_volume,
            "avg_volume_20d": avg_volume_20d,
            "rvol": _clean(rvol),
            "signal": signal,
        }

    def _score_overall_flow_signal(
        self, obv: Optional[Dict], ad: Optional[Dict], cmf: Optional[Dict],
        volume_profile: Optional[Dict], vwap: Optional[Dict],
    ) -> str:
        """Tally simple bullish/bearish checks across OBV, A/D, CMF, POC, and VWAP."""
        bullish_checks = []
        bearish_checks = []

        if obv:
            bullish_checks.append(obv.get("obv_signal") in ("bullish", "divergence_bullish"))
            bearish_checks.append(obv.get("obv_signal") in ("bearish", "divergence_bearish"))

        if ad:
            bullish_checks.append(ad.get("ad_signal") == "accumulation")
            bearish_checks.append(ad.get("ad_signal") == "distribution")

        if cmf:
            bullish_checks.append(cmf.get("cmf_signal") in ("buying", "strong_buying"))
            bearish_checks.append(cmf.get("cmf_signal") in ("selling", "strong_selling"))

        if volume_profile:
            bullish_checks.append(volume_profile.get("price_vs_poc") == "above")
            bearish_checks.append(volume_profile.get("price_vs_poc") == "below")

        if vwap:
            bullish_checks.append(vwap.get("signal") == "above_vwap")
            bearish_checks.append(vwap.get("signal") == "below_vwap")

        bullish_count = sum(1 for c in bullish_checks if c)
        bearish_count = sum(1 for c in bearish_checks if c)

        if bullish_count > bearish_count:
            return "Bullish"
        if bearish_count > bullish_count:
            return "Bearish"
        return "Neutral"

    def get_full_volume_analysis(self) -> Dict:
        """Aggregates OBV, A/D, CMF, Volume Profile, VWAP, and RVOL into one overall signal; each piece is wrapped separately so one failing indicator doesn't break the rest."""
        try:
            obv = self.get_obv()
        except Exception:
            obv = None

        try:
            ad = self.get_accumulation_distribution()
        except Exception:
            ad = None

        try:
            cmf = self.get_chaikin_money_flow()
        except Exception:
            cmf = None

        try:
            volume_profile = self.get_volume_profile()
        except Exception:
            volume_profile = None

        try:
            vwap = self.get_vwap_analysis()
        except Exception:
            vwap = None

        try:
            relative_volume = self.get_relative_volume()
        except Exception:
            relative_volume = None

        return {
            "ticker": self.ticker,
            "obv": obv,
            "accumulation_distribution": ad,
            "chaikin_money_flow": cmf,
            "volume_profile": volume_profile,
            "vwap": vwap,
            "relative_volume": relative_volume,
            "overall_flow_signal": self._score_overall_flow_signal(obv, ad, cmf, volume_profile, vwap),
        }
