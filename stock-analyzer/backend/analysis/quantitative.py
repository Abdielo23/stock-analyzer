"""Quantitative analysis: factor scores, Monte Carlo simulation, strategy backtests, and stats vs. SPY.

Data comes from yfinance (price history, financial statements, growth estimates, info).
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from utils.peer_comparison import PeerComparison
from utils.sector_benchmarks import SectorBenchmarks

RISK_FREE_RATE = 0.045
TRADING_DAYS = 252

# --- Factor weights (must sum to 1.0) and composite-score rating bands ---
FACTOR_WEIGHT_MOMENTUM = 0.25
FACTOR_WEIGHT_QUALITY = 0.25
FACTOR_WEIGHT_VALUE = 0.20
FACTOR_WEIGHT_GROWTH = 0.20
FACTOR_WEIGHT_LOW_VOL = 0.10
FACTOR_RATING_EXCELLENT_THRESHOLD = 75
FACTOR_RATING_GOOD_THRESHOLD = 60
FACTOR_RATING_AVERAGE_THRESHOLD = 45
FACTOR_RATING_BELOW_AVERAGE_THRESHOLD = 30

# --- Momentum factor: 12-month-skip-1-month, 6-month, and 3-month windows ---
MOMENTUM_12_1_LOOKBACK_DAYS = 252
MOMENTUM_12_1_SKIP_DAYS = 21
MOMENTUM_6M_LOOKBACK_DAYS = 126
MOMENTUM_3M_LOOKBACK_DAYS = 63
MOMENTUM_WEIGHT_12_1 = 0.5
MOMENTUM_WEIGHT_6M = 0.3
MOMENTUM_WEIGHT_3M = 0.2
MOMENTUM_POINTS = [(-0.15, 0), (-0.05, 20), (0.0, 40), (0.05, 60), (0.15, 80), (0.25, 100)]

# Fallback tiers, only used if live sector data isn't available — normally tiers are built from the real sector median instead.
ROE_TIERS = [(0.20, 100), (0.15, 80), (0.10, 60), (0.05, 40), (-999, 20)]
ROA_TIERS = [(0.10, 100), (0.07, 80), (0.04, 60), (0.01, 40), (-999, 20)]
GROSS_MARGIN_TIERS = [(0.60, 100), (0.40, 80), (0.25, 60), (0.10, 40), (-999, 20)]
OPERATING_MARGIN_TIERS = [(0.25, 100), (0.15, 80), (0.08, 60), (0.0, 40), (-999, 20)]
DEBT_EQUITY_TIERS = [(0.3, 100), (0.8, 80), (1.5, 60), (2.5, 40), (999, 20)]

PE_TIERS = [(12, 100), (18, 80), (25, 60), (35, 40), (999, 20)]
PB_TIERS = [(1, 100), (2, 80), (4, 60), (7, 40), (999, 20)]
EV_EBITDA_TIERS = [(8, 100), (12, 80), (18, 60), (25, 40), (999, 20)]
FCF_YIELD_TIERS = [(0.08, 100), (0.05, 80), (0.03, 60), (0.01, 40), (-999, 20)]

# Multipliers on the real sector median to build score tiers at runtime — high-good metrics score better above the median, low-good ones below it.
HIGH_GOOD_TIER_MULTIPLIERS = [(1.5, 100), (1.15, 80), (0.85, 60), (0.5, 40), (-999, 20)]
LOW_GOOD_TIER_MULTIPLIERS = [(0.6, 100), (0.85, 80), (1.15, 60), (1.5, 40), (999, 20)]

GROWTH_TIERS = [(0.25, 100), (0.15, 80), (0.08, 60), (0.0, 40), (-999, 20)]

VOL_TIERS = [(0.15, 100), (0.20, 80), (0.30, 60), (0.45, 40), (999, 20)]
BETA_TIERS = [(0.6, 100), (0.8, 80), (1.1, 60), (1.5, 40), (999, 20)]

# --- Monte Carlo simulation ---
MONTE_CARLO_SIMULATIONS = 1000
MONTE_CARLO_LOOKBACK_DAYS = 504
MONTE_CARLO_MIN_RETURNS = 30
MONTE_CARLO_PATH_SAMPLE_STRIDE = 50
BULL_CASE_PERCENTILE = 90
BASE_CASE_PERCENTILE = 50
BEAR_CASE_PERCENTILE = 10
WORST_CASE_PERCENTILE = 5
PROB_ABOVE_10PCT_MULTIPLIER = 1.10
PROB_LOSS_20PCT_MULTIPLIER = 0.80

# --- Backtesting strategies ---
SMA_CROSSOVER_FAST_PERIOD = 20
SMA_CROSSOVER_SLOW_PERIOD = 50
RSI_MEAN_REVERSION_PERIOD = 14
RSI_OVERSOLD_THRESHOLD = 30
RSI_OVERBOUGHT_THRESHOLD = 70

# --- Statistical analysis ---
HURST_MAX_LAG = 100
HURST_MIN_LAG = 10
HURST_TRENDING_THRESHOLD = 0.55
HURST_MEAN_REVERTING_THRESHOLD = 0.45
JARQUE_BERA_NORMALITY_THRESHOLD = 5.99
AUTOCORR_LAGS = (1, 5, 10)

# --- Portfolio diversification (equal-weight stock/SPY blend) ---
PORTFOLIO_EQUAL_WEIGHT = 0.5

# --- Quant signal bands ---
QUANT_SIGNAL_COMPOSITE_STRONG_BUY = 70
QUANT_SIGNAL_PROB_GAIN_STRONG_BUY = 60
QUANT_SIGNAL_COMPOSITE_STRONG_SELL = 30
QUANT_SIGNAL_PROB_GAIN_STRONG_SELL = 35
QUANT_SIGNAL_COMPOSITE_BUY = 60
QUANT_SIGNAL_PROB_GAIN_BUY = 55
QUANT_SIGNAL_COMPOSITE_SELL_MAX = 45
QUANT_SIGNAL_PROB_GAIN_SELL_MAX = 40
QUANT_SIGNAL_COMPOSITE_HOLD_MIN = 45
QUANT_SIGNAL_COMPOSITE_HOLD_MAX = 60


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
    """Period-over-period growth rate as a decimal fraction (0.10 = +10%)."""
    current, previous = _clean(current), _clean(previous)
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


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


def _interp_score(value: Optional[float], points: List[Tuple[float, float]]) -> Optional[float]:
    """Linear interpolation across named breakpoints; clamps outside the range."""
    if value is None:
        return None
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if x0 <= value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def _score_high_good(value: Optional[float], tiers: List[Tuple[float, float]]) -> Optional[float]:
    """tiers: descending list of (min_threshold, score) — higher `value` scores higher."""
    if value is None:
        return None
    for min_threshold, score in tiers:
        if value >= min_threshold:
            return score
    return tiers[-1][1]


def _dynamic_tiers_high_good(median: Optional[float]) -> Optional[List[Tuple[float, float]]]:
    """Build a "higher is better" tier list anchored on a real sector median, or None if unavailable."""
    if median is None or median <= 0:
        return None
    return [(median * multiplier, score) for multiplier, score in HIGH_GOOD_TIER_MULTIPLIERS]


def _dynamic_tiers_low_good(median: Optional[float]) -> Optional[List[Tuple[float, float]]]:
    """Build a "lower is better" tier list anchored on a real sector median, or None if unavailable."""
    if median is None or median <= 0:
        return None
    return [(median * multiplier, score) for multiplier, score in LOW_GOOD_TIER_MULTIPLIERS]


def _score_low_good(value: Optional[float], tiers: List[Tuple[float, float]]) -> Optional[float]:
    """tiers: ascending list of (max_threshold, score) — lower `value` scores higher."""
    if value is None:
        return None
    for max_threshold, score in tiers:
        if value < max_threshold:
            return score
    return tiers[-1][1]


class QuantitativeAnalyzer:
    """Computes factor scores, Monte Carlo simulation, backtests, and statistics for one ticker."""

    def __init__(self, ticker: str, period: str = "3y"):
        self.ticker = ticker.upper()
        self.period = period
        self._stock = yf.Ticker(self.ticker)
        self._info = None

        self.close = self._stock.history(period=period)["Close"].dropna()
        self.returns = self.close.pct_change().dropna()

        self.spy_close = yf.Ticker("SPY").history(period=period)["Close"].dropna()
        self.spy_returns = self.spy_close.pct_change().dropna()

        aligned = pd.concat(
            [self.returns.rename("stock"), self.spy_returns.rename("spy")], axis=1, join="inner"
        ).dropna()
        self._aligned_stock_returns = aligned["stock"]
        self._aligned_spy_returns = aligned["spy"]

    @property
    def info(self) -> dict:
        """Lazily-fetched, cached ``yfinance`` info dict (``{}`` on failure)."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    def _beta(self) -> Optional[float]:
        """CAPM beta vs. SPY (covariance / SPY variance) over the aligned return window."""
        stock_r, spy_r = self._aligned_stock_returns, self._aligned_spy_returns
        if len(spy_r) < 2:
            return None
        var_spy = np.var(spy_r, ddof=1)
        if not var_spy:
            return None
        return _clean(np.cov(stock_r, spy_r, ddof=1)[0][1] / var_spy)

    def _annualized_return_vol(self, close: pd.Series, returns: pd.Series) -> Tuple[Optional[float], Optional[float]]:
        """Annualize a total return and volatility from a price/returns series."""
        total_return = _clean(close.iloc[-1] / close.iloc[0] - 1) if len(close) > 1 else None
        n = len(returns)
        annualized_return = None
        if total_return is not None and n:
            annualized_return = (1 + total_return) ** (TRADING_DAYS / n) - 1
        annualized_vol = _clean(returns.std() * np.sqrt(TRADING_DAYS)) if n else None
        return annualized_return, annualized_vol

    # ------------------------------------------------------------------
    # 1. Factor scores
    # ------------------------------------------------------------------

    def _momentum_score(self) -> Tuple[Optional[float], Dict]:
        """12-1/6-month/3-month price momentum, weighted and scored 0-100."""
        close = self.close
        mom_12_1 = mom_6m = mom_3m = None
        try:
            if len(close) > MOMENTUM_12_1_LOOKBACK_DAYS:
                mom_12_1 = _clean(close.iloc[-MOMENTUM_12_1_SKIP_DAYS] / close.iloc[-MOMENTUM_12_1_LOOKBACK_DAYS] - 1)
            if len(close) > MOMENTUM_6M_LOOKBACK_DAYS:
                mom_6m = _clean(close.iloc[-1] / close.iloc[-MOMENTUM_6M_LOOKBACK_DAYS] - 1)
            if len(close) > MOMENTUM_3M_LOOKBACK_DAYS:
                mom_3m = _clean(close.iloc[-1] / close.iloc[-MOMENTUM_3M_LOOKBACK_DAYS] - 1)
        except Exception:
            pass

        weighted_sum, weight_total = 0.0, 0.0
        for value, weight in [(mom_12_1, MOMENTUM_WEIGHT_12_1), (mom_6m, MOMENTUM_WEIGHT_6M), (mom_3m, MOMENTUM_WEIGHT_3M)]:
            if value is not None:
                weighted_sum += value * weight
                weight_total += weight

        momentum_value = weighted_sum / weight_total if weight_total else None
        score = _interp_score(momentum_value, MOMENTUM_POINTS)

        return score, {
            "momentum_12_1": mom_12_1, "momentum_6m": mom_6m, "momentum_3m": mom_3m,
        }

    def _quality_score(self) -> Tuple[Optional[float], Dict]:
        """ROE/ROA/margins/leverage, tier-scored against the real sector median (falls back to fixed tiers if that's unavailable)."""
        try:
            financials = self._stock.income_stmt
            balance_sheet = self._stock.balance_sheet
        except Exception:
            financials, balance_sheet = None, None

        net_income = _first_valid(financials, "Net Income") if financials is not None else None
        revenue = _first_valid(financials, "Total Revenue") if financials is not None else None
        gross_profit = _first_valid(financials, "Gross Profit") if financials is not None else None
        operating_income = _first_valid(financials, "Operating Income") if financials is not None else None
        total_assets = _first_valid(balance_sheet, "Total Assets") if balance_sheet is not None else None
        total_equity = _first_valid(balance_sheet, "Stockholders Equity") if balance_sheet is not None else None
        total_debt = _first_valid(balance_sheet, "Total Debt") if balance_sheet is not None else None

        roe = net_income / total_equity if net_income is not None and total_equity else None
        roa = net_income / total_assets if net_income is not None and total_assets else None
        gross_margin = gross_profit / revenue if gross_profit is not None and revenue else None
        operating_margin = operating_income / revenue if operating_income is not None and revenue else None
        debt_to_equity = total_debt / total_equity if total_debt is not None and total_equity else None

        try:
            sector_fundamentals = SectorBenchmarks().get_sector_fundamentals(self.info.get("sector"))
        except Exception:
            sector_fundamentals = {}

        roe_tiers = _dynamic_tiers_high_good(sector_fundamentals.get("median_roe")) or ROE_TIERS
        roa_tiers = _dynamic_tiers_high_good(sector_fundamentals.get("median_roa")) or ROA_TIERS
        gross_margin_tiers = _dynamic_tiers_high_good(sector_fundamentals.get("median_gross_margin")) or GROSS_MARGIN_TIERS
        operating_margin_tiers = _dynamic_tiers_high_good(sector_fundamentals.get("median_operating_margin")) or OPERATING_MARGIN_TIERS
        debt_equity_tiers = _dynamic_tiers_low_good(sector_fundamentals.get("median_debt_equity")) or DEBT_EQUITY_TIERS

        metrics = {
            "roe": _score_high_good(roe, roe_tiers),
            "roa": _score_high_good(roa, roa_tiers),
            "gross_margin": _score_high_good(gross_margin, gross_margin_tiers),
            "operating_margin": _score_high_good(operating_margin, operating_margin_tiers),
            "debt_to_equity": _score_low_good(debt_to_equity, debt_equity_tiers),
        }
        valid = [v for v in metrics.values() if v is not None]
        score = sum(valid) / len(valid) if valid else None

        return score, {
            "roe": _clean(roe), "roa": _clean(roa), "gross_margin": _clean(gross_margin),
            "operating_margin": _clean(operating_margin), "debt_to_equity": _clean(debt_to_equity),
            "component_scores": metrics,
            "sector_benchmarks": sector_fundamentals or None,
        }

    def _value_score(self) -> Tuple[Optional[float], Dict]:
        """P/E, P/B, EV/EBITDA (vs. the real sector median), and FCF yield, tier-scored and averaged. FCF yield has no sector equivalent, so it always uses fixed tiers."""
        info = self.info
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        ev_ebitda = info.get("enterpriseToEbitda")
        market_cap = info.get("marketCap")
        fcf = info.get("freeCashflow")
        fcf_yield = fcf / market_cap if fcf is not None and market_cap else None

        try:
            sector_multiples = SectorBenchmarks().get_sector_multiples(info.get("sector"))
        except Exception:
            sector_multiples = {}

        pe_tiers = _dynamic_tiers_low_good(sector_multiples.get("pe")) or PE_TIERS
        pb_tiers = _dynamic_tiers_low_good(sector_multiples.get("pb")) or PB_TIERS
        ev_ebitda_tiers = _dynamic_tiers_low_good(sector_multiples.get("ev_ebitda")) or EV_EBITDA_TIERS

        metrics = {
            "pe": _score_low_good(pe, pe_tiers),
            "pb": _score_low_good(pb, pb_tiers),
            "ev_ebitda": _score_low_good(ev_ebitda, ev_ebitda_tiers),
            "fcf_yield": _score_high_good(fcf_yield, FCF_YIELD_TIERS),
        }
        valid = [v for v in metrics.values() if v is not None]
        score = sum(valid) / len(valid) if valid else None

        return score, {
            "pe": _clean(pe), "pb": _clean(pb), "ev_ebitda": _clean(ev_ebitda),
            "fcf_yield": _clean(fcf_yield), "component_scores": metrics,
            "sector_benchmarks": sector_multiples or None,
        }

    def _growth_score(self) -> Tuple[Optional[float], Dict]:
        """YoY revenue/EPS/FCF growth plus forward EPS growth estimate, tier-scored and averaged."""
        try:
            financials = self._stock.income_stmt
            cashflow = self._stock.cashflow
        except Exception:
            financials, cashflow = None, None

        def _yoy(df, label):
            try:
                row = df.loc[label]
                return _pct_change(row.iloc[0], row.iloc[1])
            except Exception:
                return None

        revenue_growth = _yoy(financials, "Total Revenue") if financials is not None else None
        eps_growth = _yoy(financials, "Diluted EPS") if financials is not None else None
        fcf_growth = _yoy(cashflow, "Free Cash Flow") if cashflow is not None else None

        forward_eps_growth = None
        try:
            growth_est = self._stock.growth_estimates
            if growth_est is not None and "0y" in growth_est.index:
                forward_eps_growth = _clean(growth_est.loc["0y", "stockTrend"])
        except Exception:
            pass

        metrics = {
            "revenue_growth_yoy": _score_high_good(revenue_growth, GROWTH_TIERS),
            "eps_growth_yoy": _score_high_good(eps_growth, GROWTH_TIERS),
            "fcf_growth_yoy": _score_high_good(fcf_growth, GROWTH_TIERS),
            "forward_eps_growth": _score_high_good(forward_eps_growth, GROWTH_TIERS),
        }
        valid = [v for v in metrics.values() if v is not None]
        score = sum(valid) / len(valid) if valid else None

        return score, {
            "revenue_growth_yoy": _clean(revenue_growth), "eps_growth_yoy": _clean(eps_growth),
            "fcf_growth_yoy": _clean(fcf_growth), "forward_eps_growth": _clean(forward_eps_growth),
            "component_scores": metrics,
        }

    def _low_vol_score(self) -> Tuple[Optional[float], Dict]:
        """Annualized volatility and beta, each tier-scored 0-100 (lower = higher score) and averaged."""
        annualized_vol = _clean(self.returns.std() * np.sqrt(TRADING_DAYS))
        beta = self._beta()

        metrics = {
            "volatility": _score_low_good(annualized_vol, VOL_TIERS),
            "beta": _score_low_good(beta, BETA_TIERS),
        }
        valid = [v for v in metrics.values() if v is not None]
        score = sum(valid) / len(valid) if valid else None

        return score, {
            "annualized_volatility": annualized_vol, "beta": beta, "component_scores": metrics,
        }

    def get_factor_scores(self) -> Dict:
        """Weighted composite of Momentum/Quality/Value/Growth/Low-Volatility factor scores."""
        momentum_score, momentum_detail = self._momentum_score()
        quality_score, quality_detail = self._quality_score()
        value_score, value_detail = self._value_score()
        growth_score, growth_detail = self._growth_score()
        low_vol_score, low_vol_detail = self._low_vol_score()

        weights = {
            "momentum": FACTOR_WEIGHT_MOMENTUM, "quality": FACTOR_WEIGHT_QUALITY, "value": FACTOR_WEIGHT_VALUE,
            "growth": FACTOR_WEIGHT_GROWTH, "low_vol": FACTOR_WEIGHT_LOW_VOL,
        }
        scores = {
            "momentum": momentum_score, "quality": quality_score, "value": value_score,
            "growth": growth_score, "low_vol": low_vol_score,
        }

        weighted_sum = sum(scores[k] * weights[k] for k in weights if scores[k] is not None)
        weight_total = sum(weights[k] for k in weights if scores[k] is not None)
        composite_score = _clean(weighted_sum / weight_total) if weight_total else None

        factor_rating = None
        if composite_score is not None:
            if composite_score > FACTOR_RATING_EXCELLENT_THRESHOLD:
                factor_rating = "Excellent"
            elif composite_score > FACTOR_RATING_GOOD_THRESHOLD:
                factor_rating = "Good"
            elif composite_score > FACTOR_RATING_AVERAGE_THRESHOLD:
                factor_rating = "Average"
            elif composite_score > FACTOR_RATING_BELOW_AVERAGE_THRESHOLD:
                factor_rating = "Below Average"
            else:
                factor_rating = "Poor"

        return {
            "momentum": {"score": momentum_score, **momentum_detail},
            "quality": {"score": quality_score, **quality_detail},
            "value": {"score": value_score, **value_detail},
            "growth": {"score": growth_score, **growth_detail},
            "low_volatility": {"score": low_vol_score, **low_vol_detail},
            "composite_score": composite_score,
            "factor_rating": factor_rating,
        }

    # ------------------------------------------------------------------
    # 2. Monte Carlo
    # ------------------------------------------------------------------

    def get_monte_carlo(self) -> Optional[Dict]:
        """1-year Monte Carlo simulation of price paths via geometric Brownian motion. Returns None if there isn't enough recent return data to estimate drift/volatility."""
        try:
            recent_returns = self.returns.tail(MONTE_CARLO_LOOKBACK_DAYS)
            if len(recent_returns) < MONTE_CARLO_MIN_RETURNS:
                return None

            mean, std = recent_returns.mean(), recent_returns.std()
            current_price = float(self.close.iloc[-1])

            n_sims, n_days = MONTE_CARLO_SIMULATIONS, TRADING_DAYS
            drift = mean - 0.5 * std ** 2

            # Takes about 1-2 seconds to run all the simulated paths.
            shocks = np.random.normal(loc=drift, scale=std, size=(n_sims, n_days))
            log_path = np.cumsum(shocks, axis=1)
            price_paths = current_price * np.exp(log_path)
            ending_prices = price_paths[:, -1]

            sample_paths = [
                [round(float(p), 2) for p in price_paths[i]]
                for i in range(0, n_sims, MONTE_CARLO_PATH_SAMPLE_STRIDE)
            ]

            return {
                "current_price": current_price,
                "expected_price": _clean(ending_prices.mean()),
                "median_price": _clean(np.median(ending_prices)),
                "bull_case": _clean(np.percentile(ending_prices, BULL_CASE_PERCENTILE)),
                "base_case": _clean(np.percentile(ending_prices, BASE_CASE_PERCENTILE)),
                "bear_case": _clean(np.percentile(ending_prices, BEAR_CASE_PERCENTILE)),
                "worst_case": _clean(np.percentile(ending_prices, WORST_CASE_PERCENTILE)),
                "probability_of_gain": _clean((ending_prices > current_price).mean() * 100),
                "probability_above_10pct": _clean((ending_prices > current_price * PROB_ABOVE_10PCT_MULTIPLIER).mean() * 100),
                "probability_of_loss_20pct": _clean((ending_prices < current_price * PROB_LOSS_20PCT_MULTIPLIER).mean() * 100),
                "sample_paths": sample_paths,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 3. Backtesting
    # ------------------------------------------------------------------

    def _drawdown(self, strategy_returns: pd.Series) -> Optional[float]:
        """Max drawdown (as a decimal fraction) of a strategy's cumulative return series."""
        cumulative = (1 + strategy_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = cumulative / running_max - 1
        return _clean(drawdown.min())

    def _sharpe(self, annualized_return: Optional[float], annualized_vol: Optional[float]) -> Optional[float]:
        """Sharpe ratio from an annualized return/volatility pair."""
        if annualized_return is None or not annualized_vol:
            return None
        return _clean((annualized_return - RISK_FREE_RATE) / annualized_vol)

    def _trade_stats(self, position: pd.Series) -> Tuple[int, Optional[float]]:
        """Count round-trip trades and win rate from a 0/1 position series."""
        entries = position[(position == 1) & (position.shift(1).fillna(0) == 0)].index
        exits = position[(position == 0) & (position.shift(1).fillna(0) == 1)].index

        trades = []
        exit_list = list(exits)
        for entry in entries:
            exit_candidates = [e for e in exit_list if e > entry]
            exit_date = exit_candidates[0] if exit_candidates else self.close.index[-1]
            try:
                trade_return = self.close.loc[exit_date] / self.close.loc[entry] - 1
                trades.append(trade_return)
            except Exception:
                continue

        number_of_trades = len(trades)
        win_rate = _clean(sum(1 for t in trades if t > 0) / number_of_trades * 100) if number_of_trades else None
        return number_of_trades, win_rate

    def _strategy_stats_from_position(self, position: pd.Series) -> Dict:
        """Run a 0/1 position series through the close-return math and return standard strategy stats."""
        strategy_returns = position * self.returns.reindex(position.index).fillna(0)
        strategy_returns = strategy_returns.dropna()

        ann_return, ann_vol = self._annualized_return_vol(
            (1 + strategy_returns).cumprod(), strategy_returns
        )
        max_dd = self._drawdown(strategy_returns)
        sharpe = self._sharpe(ann_return, ann_vol)
        number_of_trades, win_rate = self._trade_stats(position)

        return {
            "total_return": _clean(((1 + strategy_returns).cumprod().iloc[-1] - 1) * 100),
            "annualized_return": _clean(ann_return * 100) if ann_return is not None else None,
            "max_drawdown": _clean(max_dd * 100) if max_dd is not None else None,
            "sharpe": sharpe,
            "number_of_trades": number_of_trades,
            "win_rate": win_rate,
        }

    def _backtest_buy_and_hold(self) -> Dict:
        """Simple buy-and-hold-the-whole-period baseline."""
        annualized_return, annualized_vol = self._annualized_return_vol(self.close, self.returns)
        max_dd = self._drawdown(self.returns)
        sharpe = self._sharpe(annualized_return, annualized_vol)
        return {
            "total_return": _clean((self.close.iloc[-1] / self.close.iloc[0] - 1) * 100),
            "annualized_return": _clean(annualized_return * 100) if annualized_return is not None else None,
            "max_drawdown": _clean(max_dd * 100) if max_dd is not None else None,
            "sharpe": sharpe,
        }

    def _backtest_sma_crossover(self) -> Dict:
        """Long when the fast SMA is above the slow SMA, flat otherwise (signal lagged 1 day)."""
        sma_fast = self.close.rolling(SMA_CROSSOVER_FAST_PERIOD).mean()
        sma_slow = self.close.rolling(SMA_CROSSOVER_SLOW_PERIOD).mean()
        signal = (sma_fast > sma_slow).astype(int)
        position = signal.shift(1).fillna(0)
        return self._strategy_stats_from_position(position)

    def _backtest_rsi_mean_reversion(self) -> Dict:
        """Long when RSI crosses up from oversold, flat when it crosses down from overbought."""
        delta = self.close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / RSI_MEAN_REVERSION_PERIOD, min_periods=RSI_MEAN_REVERSION_PERIOD, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / RSI_MEAN_REVERSION_PERIOD, min_periods=RSI_MEAN_REVERSION_PERIOD, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)

        position = pd.Series(0, index=self.close.index)
        in_position = False
        for i in range(1, len(rsi)):
            if not in_position and rsi.iloc[i] < RSI_OVERSOLD_THRESHOLD and rsi.iloc[i - 1] >= RSI_OVERSOLD_THRESHOLD:
                in_position = True
            elif in_position and rsi.iloc[i] > RSI_OVERBOUGHT_THRESHOLD and rsi.iloc[i - 1] <= RSI_OVERBOUGHT_THRESHOLD:
                in_position = False
            position.iloc[i] = 1 if in_position else 0
        position = position.shift(1).fillna(0)

        return self._strategy_stats_from_position(position)

    def get_backtesting(self) -> Dict:
        """Backtest Buy & Hold, SMA Crossover, and RSI Mean Reversion. Each runs independently so one failure doesn't blank out the others; best_strategy is whichever has the highest Sharpe ratio."""
        result = {"buy_and_hold": None, "sma_crossover": None, "rsi_mean_reversion": None, "best_strategy": None}

        try:
            result["buy_and_hold"] = self._backtest_buy_and_hold()
        except Exception:
            pass

        try:
            result["sma_crossover"] = self._backtest_sma_crossover()
        except Exception:
            pass

        try:
            result["rsi_mean_reversion"] = self._backtest_rsi_mean_reversion()
        except Exception:
            pass

        sharpe_by_strategy = {
            name: result[name]["sharpe"]
            for name in ("buy_and_hold", "sma_crossover", "rsi_mean_reversion")
            if result[name] and result[name].get("sharpe") is not None
        }
        if sharpe_by_strategy:
            result["best_strategy"] = max(sharpe_by_strategy, key=sharpe_by_strategy.get)

        return result

    # ------------------------------------------------------------------
    # 4. Statistical analysis
    # ------------------------------------------------------------------

    def _hurst_exponent(self, returns: pd.Series) -> Optional[float]:
        """Rescaled-range (R/S) Hurst exponent estimate from daily returns."""
        ts = returns.values
        n = len(ts)
        max_lag = min(HURST_MAX_LAG, n // 2)
        if max_lag < HURST_MIN_LAG:
            return None

        lags = range(HURST_MIN_LAG, max_lag)
        log_lags, log_rs = [], []
        for lag in lags:
            chunks = n // lag
            if chunks < 1:
                continue
            rs_list = []
            for i in range(chunks):
                chunk = ts[i * lag:(i + 1) * lag]
                mean = chunk.mean()
                deviations = np.cumsum(chunk - mean)
                r = deviations.max() - deviations.min()
                s = chunk.std()
                if s > 0:
                    rs_list.append(r / s)
            if rs_list:
                log_lags.append(np.log(lag))
                log_rs.append(np.log(np.mean(rs_list)))

        if len(log_lags) < 2:
            return None
        slope, _ = np.polyfit(log_lags, log_rs, 1)
        return _clean(slope)

    def get_statistical_analysis(self) -> Optional[Dict]:
        """Skewness, kurtosis, normality test (Jarque-Bera), autocorrelation, and Hurst exponent."""
        try:
            returns = self.returns
            n = len(returns)

            skewness = _clean(returns.skew())
            kurtosis = _clean(returns.kurt())

            jarque_bera = None
            p_value = None
            is_normal = None
            if skewness is not None and kurtosis is not None:
                jarque_bera = n / 6 * (skewness ** 2 + kurtosis ** 2 / 4)
                p_value = _clean(np.exp(-jarque_bera / 2))
                is_normal = bool(jarque_bera < JARQUE_BERA_NORMALITY_THRESHOLD)

            autocorr = {f"lag_{lag}": _clean(returns.autocorr(lag=lag)) for lag in AUTOCORR_LAGS}
            significance_threshold = _clean(2 / np.sqrt(n)) if n else None
            autocorr_significant = {
                k: (bool(abs(v) > significance_threshold) if v is not None and significance_threshold else None)
                for k, v in autocorr.items()
            }

            hurst = self._hurst_exponent(returns)
            hurst_interpretation = None
            if hurst is not None:
                if hurst > HURST_TRENDING_THRESHOLD:
                    hurst_interpretation = "trending"
                elif hurst < HURST_MEAN_REVERTING_THRESHOLD:
                    hurst_interpretation = "mean_reverting"
                else:
                    hurst_interpretation = "random_walk"

            return {
                "skewness": skewness,
                "kurtosis": kurtosis,
                "leptokurtic": bool(kurtosis > 3) if kurtosis is not None else None,
                "jarque_bera": _clean(jarque_bera),
                "p_value": p_value,
                "is_normal": is_normal,
                "autocorrelation": autocorr,
                "autocorrelation_significant": autocorr_significant,
                "hurst_exponent": hurst,
                "hurst_interpretation": hurst_interpretation,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 5. Portfolio metrics
    # ------------------------------------------------------------------

    def get_portfolio_metrics(self) -> Optional[Dict]:
        """Return/risk coordinates for the stock and SPY, plus a 50/50 diversification estimate."""
        try:
            stock_return, stock_vol = self._annualized_return_vol(self.close, self.returns)
            spy_return, spy_vol = self._annualized_return_vol(self.spy_close, self.spy_returns)

            correlation = None
            if len(self._aligned_stock_returns) > 1:
                correlation = _clean(np.corrcoef(self._aligned_stock_returns, self._aligned_spy_returns)[0][1])

            diversification_benefit_pct = None
            if stock_vol and spy_vol and correlation is not None:
                w = PORTFOLIO_EQUAL_WEIGHT
                combined_var = (
                    w ** 2 * stock_vol ** 2 + w ** 2 * spy_vol ** 2
                    + 2 * w * w * correlation * stock_vol * spy_vol
                )
                combined_vol = np.sqrt(combined_var)
                diversification_benefit_pct = _clean((stock_vol - combined_vol) / stock_vol * 100)

            suggestion = None
            if diversification_benefit_pct is not None:
                suggestion = f"Adding SPY reduces portfolio volatility by {diversification_benefit_pct:.1f}%"

            return {
                "return_risk_coordinates": {
                    "return": _clean(stock_return * 100) if stock_return is not None else None,
                    "risk": _clean(stock_vol * 100) if stock_vol is not None else None,
                },
                "spy_coordinates": {
                    "return": _clean(spy_return * 100) if spy_return is not None else None,
                    "risk": _clean(spy_vol * 100) if spy_vol is not None else None,
                },
                "correlation_to_spy": correlation,
                "diversification_benefit_pct": diversification_benefit_pct,
                "concentration_warning": "High concentration risk",
                "suggestion": suggestion,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 6. Full analysis
    # ------------------------------------------------------------------

    def _quant_signal(self, composite_score: Optional[float], prob_of_gain: Optional[float]) -> str:
        """Combine the composite factor score and Monte Carlo win probability into one signal."""
        if composite_score is not None and prob_of_gain is not None:
            if composite_score > QUANT_SIGNAL_COMPOSITE_STRONG_BUY and prob_of_gain > QUANT_SIGNAL_PROB_GAIN_STRONG_BUY:
                return "Strong Buy"
            if composite_score < QUANT_SIGNAL_COMPOSITE_STRONG_SELL and prob_of_gain < QUANT_SIGNAL_PROB_GAIN_STRONG_SELL:
                return "Strong Sell"
            if composite_score > QUANT_SIGNAL_COMPOSITE_BUY and prob_of_gain > QUANT_SIGNAL_PROB_GAIN_BUY:
                return "Buy"
            if composite_score < QUANT_SIGNAL_COMPOSITE_SELL_MAX or prob_of_gain < QUANT_SIGNAL_PROB_GAIN_SELL_MAX:
                return "Sell"
            if QUANT_SIGNAL_COMPOSITE_HOLD_MIN <= composite_score <= QUANT_SIGNAL_COMPOSITE_HOLD_MAX:
                return "Hold"
        elif composite_score is not None:
            if composite_score < QUANT_SIGNAL_COMPOSITE_SELL_MAX:
                return "Sell"
            if composite_score > QUANT_SIGNAL_COMPOSITE_BUY:
                return "Buy"
        return "Hold"

    def _peer_comparison(self) -> Optional[Dict]:
        """This ticker ranked against its real sector-ETF peers, via `utils.peer_comparison`."""
        try:
            pc = PeerComparison()
            peers = pc.get_sector_peers(self.ticker)
            if not peers:
                return None
            return pc.rank_vs_peers(self.ticker, peers)
        except Exception:
            return None

    def get_full_quantitative_analysis(self) -> Dict:
        """Aggregates factor scores, Monte Carlo, backtesting, statistics, portfolio, and peers into one signal. Each piece runs in its own try/except so one failure doesn't take down the whole result."""
        try:
            factors = self.get_factor_scores()
        except Exception:
            factors = None

        try:
            monte_carlo = self.get_monte_carlo()
        except Exception:
            monte_carlo = None

        try:
            backtesting = self.get_backtesting()
        except Exception:
            backtesting = None

        try:
            statistics = self.get_statistical_analysis()
        except Exception:
            statistics = None

        try:
            portfolio = self.get_portfolio_metrics()
        except Exception:
            portfolio = None

        peer_comparison = self._peer_comparison()

        composite_score = factors.get("composite_score") if factors else None
        prob_of_gain = monte_carlo.get("probability_of_gain") if monte_carlo else None

        return {
            "ticker": self.ticker,
            "factors": factors,
            "monte_carlo": monte_carlo,
            "backtesting": backtesting,
            "statistics": statistics,
            "portfolio": portfolio,
            "peer_comparison": peer_comparison,
            "quant_signal": self._quant_signal(composite_score, prob_of_gain),
        }
