"""Technical analysis: trend, momentum, and support/resistance indicators, computed natively in pandas/numpy (no pandas-ta dependency) from yfinance daily OHLCV data."""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

# --- Moving averages / trend ---
SMA_SHORT_PERIOD = 20
SMA_MEDIUM_PERIOD = 50
SMA_LONG_PERIOD = 200
EMA_FAST_PERIOD = 12
EMA_SLOW_PERIOD = 26
GOLDEN_DEATH_CROSS_LOOKBACK_DAYS = 5

# --- ADX / ATR (Wilder's smoothing length) ---
DIRECTIONAL_MOVEMENT_LENGTH = 14
ADX_STRONG_THRESHOLD = 25
ADX_WEAK_THRESHOLD = 20

# --- Ichimoku Cloud ---
ICHIMOKU_TENKAN_PERIOD = 9
ICHIMOKU_KIJUN_PERIOD = 26
ICHIMOKU_SENKOU_B_PERIOD = 52
ICHIMOKU_CLOUD_SHIFT = 26

# --- Oscillators ---
RSI_LENGTH = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_SIGNAL_PERIOD = 9
STOCHASTIC_PERIOD = 14
STOCHASTIC_SMOOTHING = 3
STOCHASTIC_OVERBOUGHT = 80
STOCHASTIC_OVERSOLD = 20
CCI_PERIOD = 20
CCI_CONSTANT = 0.015

# --- Bollinger Bands ---
BOLLINGER_PERIOD = 20
BOLLINGER_STD_MULTIPLIER = 2

# --- Support/resistance & output shaping ---
LOCAL_EXTREMA_WINDOW_DAYS = 60
LOCAL_EXTREMA_KEEP = 3
PRICE_HISTORY_TAIL = 100


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


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (used by RSI, ADX, ATR)."""
    return series.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def _records(df: pd.DataFrame) -> List[dict]:
    """Convert a DataFrame to a list of dicts with the index as a string 'date' field."""
    df = df.reset_index()
    df.columns = [str(c) for c in df.columns]
    date_col = df.columns[0]
    df = df.rename(columns={date_col: "date"})
    df["date"] = df["date"].astype(str)
    records = df.to_dict(orient="records")
    return [{k: _clean(v) if k != "date" else v for k, v in row.items()} for row in records]


class TechnicalAnalyzer:
    """Computes trend/momentum/support-resistance indicators for one ticker."""

    def __init__(self, ticker: str, period: str = "1y"):
        self.ticker = ticker.upper()
        self.period = period
        self._stock = yf.Ticker(self.ticker)
        history = self._stock.history(period=period)
        # yfinance can add a placeholder row for today's still-open session (NaN OHLC) — drop it or "current value" indicators break.
        self.df = history[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
        self._indicators = None

    @property
    def indicators(self) -> pd.DataFrame:
        """Lazily-built, cached DataFrame of `self.df` plus every indicator column."""
        if self._indicators is None:
            self._indicators = self._build_indicators()
        return self._indicators

    def _add_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """SMA20/50/200, EMA12/26, and cumulative VWAP."""
        high, low, close, volume = df["High"], df["Low"], df["Close"], df["Volume"]

        df["SMA20"] = close.rolling(SMA_SHORT_PERIOD).mean()
        df["SMA50"] = close.rolling(SMA_MEDIUM_PERIOD).mean()
        df["SMA200"] = close.rolling(SMA_LONG_PERIOD).mean()
        df["EMA12"] = _ema(close, EMA_FAST_PERIOD)
        df["EMA26"] = _ema(close, EMA_SLOW_PERIOD)

        typical_price = (high + low + close) / 3
        df["VWAP"] = (typical_price * volume).cumsum() / volume.cumsum()
        return df

    def _add_directional_movement(self, df: pd.DataFrame) -> pd.DataFrame:
        """ATR, +DI/-DI, and ADX (Wilder's smoothed trend-strength indicator)."""
        high, low, close = df["High"], df["Low"], df["Close"]

        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        tr = _true_range(high, low, close)
        atr = _rma(tr, DIRECTIONAL_MOVEMENT_LENGTH)
        df["ATR"] = atr
        df["PLUS_DI"] = 100 * _rma(plus_dm, DIRECTIONAL_MOVEMENT_LENGTH) / atr
        df["MINUS_DI"] = 100 * _rma(minus_dm, DIRECTIONAL_MOVEMENT_LENGTH) / atr
        dx = 100 * (df["PLUS_DI"] - df["MINUS_DI"]).abs() / (df["PLUS_DI"] + df["MINUS_DI"])
        df["ADX"] = _rma(dx, DIRECTIONAL_MOVEMENT_LENGTH)
        return df

    def _add_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ichimoku Cloud: Tenkan-sen, Kijun-sen, Senkou spans A/B, Chikou span."""
        high, low, close = df["High"], df["Low"], df["Close"]

        tenkan = (high.rolling(ICHIMOKU_TENKAN_PERIOD).max() + low.rolling(ICHIMOKU_TENKAN_PERIOD).min()) / 2
        kijun = (high.rolling(ICHIMOKU_KIJUN_PERIOD).max() + low.rolling(ICHIMOKU_KIJUN_PERIOD).min()) / 2
        df["TENKAN"] = tenkan
        df["KIJUN"] = kijun
        df["SENKOU_A"] = ((tenkan + kijun) / 2).shift(ICHIMOKU_CLOUD_SHIFT)
        df["SENKOU_B"] = (
            (high.rolling(ICHIMOKU_SENKOU_B_PERIOD).max() + low.rolling(ICHIMOKU_SENKOU_B_PERIOD).min()) / 2
        ).shift(ICHIMOKU_CLOUD_SHIFT)
        # Chikou span is null for the last few rows since it needs future data that doesn't exist yet.
        df["CHIKOU"] = close.shift(-ICHIMOKU_CLOUD_SHIFT)
        return df

    def _add_oscillators(self, df: pd.DataFrame) -> pd.DataFrame:
        """RSI, MACD, Stochastic %K/%D, Williams %R, and CCI."""
        high, low, close = df["High"], df["Low"], df["Close"]
        typical_price = (high + low + close) / 3

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = _rma(gain, RSI_LENGTH)
        avg_loss = _rma(loss, RSI_LENGTH)
        rs = avg_gain / avg_loss
        df["RSI"] = 100 - 100 / (1 + rs)

        macd_line = df["EMA12"] - df["EMA26"]
        df["MACD"] = macd_line
        df["MACD_signal"] = _ema(macd_line, MACD_SIGNAL_PERIOD)
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

        low_n = low.rolling(STOCHASTIC_PERIOD).min()
        high_n = high.rolling(STOCHASTIC_PERIOD).max()
        df["STOCH_K"] = 100 * (close - low_n) / (high_n - low_n)
        df["STOCH_D"] = df["STOCH_K"].rolling(STOCHASTIC_SMOOTHING).mean()

        df["WILLIAMS_R"] = -100 * (high_n - close) / (high_n - low_n)

        tp_sma = typical_price.rolling(CCI_PERIOD).mean()
        mean_dev = typical_price.rolling(CCI_PERIOD).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
        df["CCI"] = (typical_price - tp_sma) / (CCI_CONSTANT * mean_dev)
        return df

    def _add_bollinger_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bollinger Bands: middle/upper/lower, bandwidth, and %B."""
        close = df["Close"]
        bb_middle = close.rolling(BOLLINGER_PERIOD).mean()
        bb_std = close.rolling(BOLLINGER_PERIOD).std()
        df["BB_middle"] = bb_middle
        df["BB_upper"] = bb_middle + BOLLINGER_STD_MULTIPLIER * bb_std
        df["BB_lower"] = bb_middle - BOLLINGER_STD_MULTIPLIER * bb_std
        df["BB_bandwidth"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_middle"]
        df["BB_percent_b"] = (close - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"])
        return df

    def _build_indicators(self) -> pd.DataFrame:
        """Build every indicator column, in dependency order — MACD needs the EMA12/EMA26 columns added earlier."""
        df = self.df.copy()
        df = self._add_moving_averages(df)
        df = self._add_directional_movement(df)
        df = self._add_ichimoku(df)
        df = self._add_oscillators(df)
        df = self._add_bollinger_bands(df)
        return df

    def get_trend_indicators(self) -> Dict:
        """SMAs/EMAs/VWAP/ADX/Ichimoku plus price-vs-average and cross signals."""
        ind = self.indicators
        close = ind["Close"]
        current_price = _last(close)

        result = {
            "sma_20": _last(ind["SMA20"]),
            "sma_50": _last(ind["SMA50"]),
            "sma_200": _last(ind["SMA200"]),
            "ema_12": _last(ind["EMA12"]),
            "ema_26": _last(ind["EMA26"]),
            "vwap": _last(ind["VWAP"]),
            "adx": _last(ind["ADX"]),
            "plus_di": _last(ind["PLUS_DI"]),
            "minus_di": _last(ind["MINUS_DI"]),
            "ichimoku": {
                "tenkan_sen": _last(ind["TENKAN"]),
                "kijun_sen": _last(ind["KIJUN"]),
                "senkou_span_a": _last(ind["SENKOU_A"]),
                "senkou_span_b": _last(ind["SENKOU_B"]),
                "chikou_span": _last(ind["CHIKOU"]),
            },
        }

        try:
            result["price_vs_sma20"] = "above" if current_price > _last(ind["SMA20"]) else "below"
        except TypeError:
            result["price_vs_sma20"] = None
        try:
            result["price_vs_sma50"] = "above" if current_price > _last(ind["SMA50"]) else "below"
        except TypeError:
            result["price_vs_sma50"] = None
        try:
            result["price_vs_sma200"] = "above" if current_price > _last(ind["SMA200"]) else "below"
        except TypeError:
            result["price_vs_sma200"] = None

        try:
            diff = ind["SMA50"] - ind["SMA200"]
            cross_up = (diff.shift(1) < 0) & (diff > 0)
            cross_down = (diff.shift(1) > 0) & (diff < 0)
            result["golden_cross"] = bool(cross_up.tail(GOLDEN_DEATH_CROSS_LOOKBACK_DAYS).any())
            result["death_cross"] = bool(cross_down.tail(GOLDEN_DEATH_CROSS_LOOKBACK_DAYS).any())
        except Exception:
            result["golden_cross"] = None
            result["death_cross"] = None

        adx = result["adx"]
        if adx is None:
            result["adx_trend"] = None
        elif adx > ADX_STRONG_THRESHOLD:
            result["adx_trend"] = "strong"
        elif adx < ADX_WEAK_THRESHOLD:
            result["adx_trend"] = "weak"
        else:
            result["adx_trend"] = "moderate"

        senkou_a, senkou_b = result["ichimoku"]["senkou_span_a"], result["ichimoku"]["senkou_span_b"]
        if current_price is None or senkou_a is None or senkou_b is None:
            result["ichimoku_signal"] = None
        else:
            cloud_top, cloud_bottom = max(senkou_a, senkou_b), min(senkou_a, senkou_b)
            if current_price > cloud_top:
                result["ichimoku_signal"] = "bullish"
            elif current_price < cloud_bottom:
                result["ichimoku_signal"] = "bearish"
            else:
                result["ichimoku_signal"] = "neutral"

        return result

    def get_momentum_indicators(self) -> Dict:
        """RSI, MACD, Stochastic, Williams %R, CCI, ATR, and Bollinger Bands."""
        ind = self.indicators
        result = {}

        rsi = _last(ind["RSI"])
        result["rsi"] = {
            "value": rsi,
            "signal": None if rsi is None else (
                "overbought" if rsi > RSI_OVERBOUGHT else "oversold" if rsi < RSI_OVERSOLD else "neutral"
            ),
        }

        macd_line, macd_signal, macd_hist = _last(ind["MACD"]), _last(ind["MACD_signal"]), _last(ind["MACD_hist"])
        result["macd"] = {
            "macd_line": macd_line,
            "signal_line": macd_signal,
            "histogram": macd_hist,
            "signal": None if macd_hist is None else (
                "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "neutral"
            ),
        }

        stoch_k, stoch_d = _last(ind["STOCH_K"]), _last(ind["STOCH_D"])
        result["stochastic"] = {
            "percent_k": stoch_k,
            "percent_d": stoch_d,
            "signal": None if stoch_k is None else (
                "overbought" if stoch_k > STOCHASTIC_OVERBOUGHT else "oversold" if stoch_k < STOCHASTIC_OVERSOLD else "neutral"
            ),
        }

        result["williams_r"] = _last(ind["WILLIAMS_R"])
        result["cci"] = _last(ind["CCI"])
        result["atr"] = _last(ind["ATR"])

        bb_upper, bb_lower, bb_middle = _last(ind["BB_upper"]), _last(ind["BB_lower"]), _last(ind["BB_middle"])
        current_price = _last(ind["Close"])
        bb_signal = None
        if current_price is not None and bb_upper is not None and bb_lower is not None:
            if current_price > bb_upper:
                bb_signal = "above_upper"
            elif current_price < bb_lower:
                bb_signal = "below_lower"
            else:
                bb_signal = "inside"

        result["bollinger_bands"] = {
            "upper": bb_upper,
            "middle": bb_middle,
            "lower": bb_lower,
            "bandwidth": _last(ind["BB_bandwidth"]),
            "percent_b": _last(ind["BB_percent_b"]),
            "signal": bb_signal,
        }

        return result

    def get_support_resistance(self) -> Dict:
        """Classic floor-trader pivot points plus recent 3-bar swing highs/lows."""
        result = {
            "pivot_point": None, "r1": None, "r2": None, "r3": None,
            "s1": None, "s2": None, "s3": None,
            "local_highs": [], "local_lows": [],
        }

        try:
            last = self.df.iloc[-1]
            high, low, close = float(last["High"]), float(last["Low"]), float(last["Close"])
            pp = (high + low + close) / 3
            result.update({
                "pivot_point": _clean(pp),
                "r1": _clean(2 * pp - low),
                "r2": _clean(pp + (high - low)),
                "r3": _clean(high + 2 * (pp - low)),
                "s1": _clean(2 * pp - high),
                "s2": _clean(pp - (high - low)),
                "s3": _clean(low - 2 * (high - pp)),
            })
        except Exception:
            pass

        try:
            window = self.df.tail(LOCAL_EXTREMA_WINDOW_DAYS)
            closes = window["Close"]
            highs, lows = [], []
            for i in range(1, len(closes) - 1):
                price = closes.iloc[i]
                if price > closes.iloc[i - 1] and price > closes.iloc[i + 1]:
                    highs.append({"date": str(closes.index[i].date()), "price": _clean(price)})
                elif price < closes.iloc[i - 1] and price < closes.iloc[i + 1]:
                    lows.append({"date": str(closes.index[i].date()), "price": _clean(price)})
            result["local_highs"] = highs[-LOCAL_EXTREMA_KEEP:]
            result["local_lows"] = lows[-LOCAL_EXTREMA_KEEP:]
        except Exception:
            pass

        return result

    def get_price_history_with_indicators(self) -> List[dict]:
        """Last `PRICE_HISTORY_TAIL` days of OHLCV plus key indicator columns, for charting."""
        try:
            cols = ["Open", "High", "Low", "Close", "Volume", "SMA20", "SMA50",
                    "EMA12", "RSI", "MACD", "MACD_signal", "BB_upper", "BB_lower", "BB_middle"]
            subset = self.indicators[cols].tail(PRICE_HISTORY_TAIL)
            return _records(subset)
        except Exception:
            return []

    def _score_overall_signal(self, trend: Optional[Dict], momentum: Optional[Dict]) -> str:
        """Tally simple bullish/bearish checks across RSI, MACD, SMA50, Ichimoku, and ADX."""
        bullish_checks = []
        bearish_checks = []

        if momentum:
            rsi_signal = momentum["rsi"]["signal"]
            bullish_checks.append(rsi_signal is not None and rsi_signal != "overbought")
            bearish_checks.append(rsi_signal == "overbought")

            macd_signal = momentum["macd"]["signal"]
            bullish_checks.append(macd_signal == "bullish")
            bearish_checks.append(macd_signal == "bearish")

        if trend:
            bullish_checks.append(trend.get("price_vs_sma50") == "above")
            bearish_checks.append(trend.get("price_vs_sma50") == "below")

            bullish_checks.append(trend.get("ichimoku_signal") == "bullish")
            bearish_checks.append(trend.get("ichimoku_signal") == "bearish")

            # ADX measures trend strength, not direction, so credit "strong" to whichever side +DI/-DI favors.
            adx_strong = trend.get("adx_trend") == "strong"
            plus_di, minus_di = trend.get("plus_di"), trend.get("minus_di")
            if adx_strong and plus_di is not None and minus_di is not None:
                bullish_checks.append(plus_di > minus_di)
                bearish_checks.append(minus_di > plus_di)

        bullish_count = sum(1 for c in bullish_checks if c)
        bearish_count = sum(1 for c in bearish_checks if c)

        if bullish_count > bearish_count:
            return "Bullish"
        if bearish_count > bullish_count:
            return "Bearish"
        return "Neutral"

    def get_full_technical(self) -> Dict:
        """Aggregate trend, momentum, support/resistance, and price history into one signal; each piece runs in its own try/except so one failure doesn't break the rest."""
        try:
            trend = self.get_trend_indicators()
        except Exception:
            trend = None

        try:
            momentum = self.get_momentum_indicators()
        except Exception:
            momentum = None

        try:
            support_resistance = self.get_support_resistance()
        except Exception:
            support_resistance = None

        try:
            price_history = self.get_price_history_with_indicators()
        except Exception:
            price_history = []

        return {
            "ticker": self.ticker,
            "trend": trend,
            "momentum": momentum,
            "support_resistance": support_resistance,
            "price_history": price_history,
            "overall_signal": self._score_overall_signal(trend, momentum),
        }
