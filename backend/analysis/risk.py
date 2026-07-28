"""Risk analysis: returns, risk-adjusted ratios, drawdown, VaR/CVaR, volatility, and correlations, from yfinance daily closes.

Percent fields are already pre-multiplied (54.45 means 54.45%), unlike fundamental.py which uses decimal fractions.
"""

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

RISK_FREE_RATE = 0.045
TRADING_DAYS_PER_YEAR = 252
CORRELATION_TICKERS = ["SPY", "QQQ", "GLD", "TLT", "BTC-USD"]

# --- Ratio interpretation bands ---
SHARPE_EXCELLENT_THRESHOLD = 2
SHARPE_GOOD_THRESHOLD = 1
SHARPE_ACCEPTABLE_THRESHOLD = 0.5
BETA_AGGRESSIVE_THRESHOLD = 1.5
BETA_MODERATE_MIN_THRESHOLD = 0.8

# --- VaR ---
VAR_95_Z_SCORE = 1.645
VAR_99_Z_SCORE = 2.326
MONTE_CARLO_VAR_SIMULATIONS = 10_000
EXAMPLE_PORTFOLIO_DOLLARS = 10_000

# --- Volatility regime bands (annualized %, already pre-multiplied) ---
VOLATILITY_EXTREME_THRESHOLD = 40
VOLATILITY_HIGH_THRESHOLD = 25
VOLATILITY_NORMAL_MIN_THRESHOLD = 15

# --- Correlation interpretation bands ---
CORRELATION_HIGH_THRESHOLD = 0.7
CORRELATION_MODERATE_THRESHOLD = 0.4

HISTORY_TAIL = 100

# --- Composite risk-score weighting (0-100; higher = riskier) ---
RISK_SCORE_VOL_EXTREME_PTS = 30
RISK_SCORE_VOL_HIGH_PTS = 20
RISK_SCORE_VOL_NORMAL_PTS = 10
RISK_SCORE_DD_SEVERE_THRESHOLD = 50
RISK_SCORE_DD_SEVERE_PTS = 25
RISK_SCORE_DD_MODERATE_THRESHOLD = 30
RISK_SCORE_DD_MODERATE_PTS = 15
RISK_SCORE_DD_MILD_PTS = 5
RISK_SCORE_BETA_AGGRESSIVE_PTS = 20
RISK_SCORE_BETA_MODERATE_PTS = 10
RISK_SCORE_BETA_DEFENSIVE_PTS = 5
RISK_SCORE_SHARPE_POOR_PTS = 15
RISK_SCORE_SHARPE_ACCEPTABLE_PTS = 10
RISK_SCORE_SHARPE_GOOD_PTS = 5
RISK_SCORE_SORTINO_EXCELLENT_THRESHOLD = 1.5
RISK_SCORE_SORTINO_BONUS_PTS = -10
RISK_LABEL_CONSERVATIVE_MAX = 30
RISK_LABEL_MODERATE_MAX = 50
RISK_LABEL_AGGRESSIVE_MAX = 70


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


def _pct(value: Optional[float]) -> Optional[float]:
    """Convert a decimal fraction to a pre-multiplied percentage (0.05 -> 5.0)."""
    cleaned = _clean(value)
    return None if cleaned is None else cleaned * 100


def _annualized_return(total_return: Optional[float], trading_days: int) -> Optional[float]:
    """Compound `total_return` over `trading_days` up to an annualized rate."""
    if total_return is None or not trading_days:
        return None
    try:
        return (1 + total_return) ** (TRADING_DAYS_PER_YEAR / trading_days) - 1
    except (ValueError, ZeroDivisionError):
        return None


class RiskAnalyzer:
    """Computes return/risk statistics for one ticker vs. SPY and other benchmarks."""

    def __init__(self, ticker: str, period: str = "2y"):
        self.ticker = ticker.upper()
        self.period = period

        self.close = yf.Ticker(self.ticker).history(period=period)["Close"].dropna()
        self.returns = self.close.pct_change().dropna()

        self.spy_close = yf.Ticker("SPY").history(period=period)["Close"].dropna()
        self.spy_returns = self.spy_close.pct_change().dropna()

        aligned = pd.concat(
            [self.returns.rename("stock"), self.spy_returns.rename("spy")], axis=1, join="inner"
        ).dropna()
        self._aligned_stock_returns = aligned["stock"]
        self._aligned_spy_returns = aligned["spy"]

        self._drawdown_cache = None

    def _drawdown_series(self) -> pd.Series:
        """Lazily-computed, cached peak-to-trough drawdown series (as a decimal fraction)."""
        if self._drawdown_cache is None:
            cumulative = (1 + self.returns).cumprod()
            running_max = cumulative.cummax()
            self._drawdown_cache = cumulative / running_max - 1
        return self._drawdown_cache

    def get_return_metrics(self) -> Dict:
        """Total/annualized return, volatility, best/worst day and month."""
        close, returns = self.close, self.returns

        total_return = _clean(close.iloc[-1] / close.iloc[0] - 1)
        trading_days = len(returns)
        annualized_return = _annualized_return(total_return, trading_days)
        annualized_volatility = _clean(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

        best_day = _clean(returns.max())
        worst_day = _clean(returns.min())

        monthly = close.resample("ME").last().pct_change().dropna()
        best_month = _clean(monthly.max()) if len(monthly) else None
        worst_month = _clean(monthly.min()) if len(monthly) else None

        positive_days_pct = _clean((returns > 0).mean())

        return {
            "total_return": _pct(total_return),
            "annualized_return": _pct(annualized_return),
            "annualized_volatility": _pct(annualized_volatility),
            "best_day": _pct(best_day),
            "worst_day": _pct(worst_day),
            "best_month": _pct(best_month),
            "worst_month": _pct(worst_month),
            "positive_days_pct": _pct(positive_days_pct),
        }

    def _beta(self) -> Optional[float]:
        """CAPM beta vs. SPY (covariance / SPY variance) over the aligned return window."""
        stock_r, spy_r = self._aligned_stock_returns, self._aligned_spy_returns
        if len(spy_r) <= 1:
            return None
        var_spy = np.var(spy_r, ddof=1)
        if not var_spy:
            return None
        return _clean(np.cov(stock_r, spy_r, ddof=1)[0][1] / var_spy)

    def _stock_and_spy_annual_returns(self) -> Tuple[Optional[float], Optional[float]]:
        """Annualized total return for the stock and for SPY, as decimal fractions."""
        stock_total_return = _clean(self.close.iloc[-1] / self.close.iloc[0] - 1)
        stock_annual_return = _annualized_return(stock_total_return, len(self.returns))

        spy_total_return = _clean(self.spy_close.iloc[-1] / self.spy_close.iloc[0] - 1)
        spy_annual_return = _annualized_return(spy_total_return, len(self.spy_returns))
        return stock_annual_return, spy_annual_return

    def _sharpe_interpretation(self, sharpe: Optional[float]) -> Optional[str]:
        """Classify a Sharpe ratio as excellent/good/acceptable/poor."""
        if sharpe is None:
            return None
        if sharpe > SHARPE_EXCELLENT_THRESHOLD:
            return "excellent"
        if sharpe > SHARPE_GOOD_THRESHOLD:
            return "good"
        if sharpe > SHARPE_ACCEPTABLE_THRESHOLD:
            return "acceptable"
        return "poor"

    def _beta_interpretation(self, beta: Optional[float]) -> Optional[str]:
        """Classify a beta as aggressive/moderate/defensive relative to the market."""
        if beta is None:
            return None
        if beta > BETA_AGGRESSIVE_THRESHOLD:
            return "aggressive"
        if beta >= BETA_MODERATE_MIN_THRESHOLD:
            return "moderate"
        return "defensive"

    def get_risk_ratios(self) -> Dict:
        """Beta, alpha, Sharpe, Sortino, Treynor, Information Ratio, and Calmar ratios."""
        stock_r, spy_r = self._aligned_stock_returns, self._aligned_spy_returns

        beta = self._beta()
        stock_annual_return, spy_annual_return = self._stock_and_spy_annual_returns()

        alpha = None
        if beta is not None and stock_annual_return is not None and spy_annual_return is not None:
            alpha = stock_annual_return - (RISK_FREE_RATE + beta * (spy_annual_return - RISK_FREE_RATE))

        annualized_volatility = _clean(self.returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

        sharpe = None
        if stock_annual_return is not None and annualized_volatility:
            sharpe = (stock_annual_return - RISK_FREE_RATE) / annualized_volatility

        downside_returns = self.returns[self.returns < 0]
        downside_deviation = _clean(downside_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(downside_returns) else None
        sortino = None
        if stock_annual_return is not None and downside_deviation:
            sortino = (stock_annual_return - RISK_FREE_RATE) / downside_deviation

        treynor = None
        if stock_annual_return is not None and beta:
            treynor = (stock_annual_return - RISK_FREE_RATE) / beta

        tracking_error = None
        information_ratio = None
        if len(stock_r) > 1:
            tracking_error = _clean((stock_r - spy_r).std() * np.sqrt(TRADING_DAYS_PER_YEAR))
            if tracking_error and stock_annual_return is not None and spy_annual_return is not None:
                information_ratio = (stock_annual_return - spy_annual_return) / tracking_error

        max_drawdown = _clean(self._drawdown_series().min())
        calmar = None
        if stock_annual_return is not None and max_drawdown:
            calmar = stock_annual_return / abs(max_drawdown)

        return {
            "beta": beta,
            "beta_interpretation": self._beta_interpretation(beta),
            "alpha": _pct(alpha),
            "sharpe_ratio": _clean(sharpe),
            "sharpe_interpretation": self._sharpe_interpretation(sharpe),
            "sortino_ratio": _clean(sortino),
            "treynor_ratio": _clean(treynor),
            "information_ratio": _clean(information_ratio),
            "calmar_ratio": _clean(calmar),
        }

    def get_drawdown_analysis(self) -> Dict:
        """Max drawdown, its duration, current drawdown, and a 100-day history."""
        drawdown = self._drawdown_series()

        max_drawdown = _clean(drawdown.min())

        underwater = drawdown < 0
        max_duration = 0
        current_run = 0
        for is_underwater in underwater:
            if is_underwater:
                current_run += 1
                max_duration = max(max_duration, current_run)
            else:
                current_run = 0

        current_drawdown = _clean(drawdown.iloc[-1])
        total_return = _clean(self.close.iloc[-1] / self.close.iloc[0] - 1)

        recovery_factor = None
        if total_return is not None and max_drawdown:
            recovery_factor = total_return / abs(max_drawdown)

        series_tail = drawdown.tail(HISTORY_TAIL)
        drawdown_series = [
            {"date": str(idx.date()), "drawdown": _pct(value)}
            for idx, value in series_tail.items()
        ]

        return {
            "max_drawdown": _pct(max_drawdown),
            "max_drawdown_duration_days": max_duration,
            "current_drawdown": _pct(current_drawdown),
            "recovery_factor": _clean(recovery_factor),
            "drawdown_series": drawdown_series,
        }

    def get_var_analysis(self) -> Dict:
        """Historical, parametric, and Monte-Carlo Value-at-Risk (95%/99%) plus CVaR."""
        returns = self.returns
        mean, std = returns.mean(), returns.std()

        historical_var_95 = _clean(np.percentile(returns, 5))
        historical_var_99 = _clean(np.percentile(returns, 1))

        cvar_95 = _clean(returns[returns <= historical_var_95].mean()) if historical_var_95 is not None else None
        cvar_99 = _clean(returns[returns <= historical_var_99].mean()) if historical_var_99 is not None else None

        parametric_var_95 = _clean(mean - VAR_95_Z_SCORE * std)
        parametric_var_99 = _clean(mean - VAR_99_Z_SCORE * std)

        simulated = np.random.normal(loc=mean, scale=std, size=MONTE_CARLO_VAR_SIMULATIONS)
        monte_carlo_var_95 = _clean(np.percentile(simulated, 5))

        dollar_loss_95 = abs(historical_var_95) * EXAMPLE_PORTFOLIO_DOLLARS if historical_var_95 is not None else None
        interpretation = None
        if dollar_loss_95 is not None:
            interpretation = (
                f"If you invest ${EXAMPLE_PORTFOLIO_DOLLARS:,}, on a bad day (95% confidence) "
                f"you could lose ${dollar_loss_95:,.2f}"
            )

        return {
            "historical_var_95": _pct(historical_var_95),
            "historical_var_99": _pct(historical_var_99),
            "cvar_95": _pct(cvar_95),
            "cvar_99": _pct(cvar_99),
            "parametric_var_95": _pct(parametric_var_95),
            "parametric_var_99": _pct(parametric_var_99),
            "monte_carlo_var_95": _pct(monte_carlo_var_95),
            "interpretation": interpretation,
        }

    def get_volatility_analysis(self) -> Dict:
        """Rolling 20d/60d volatility, current regime, and relative volatility vs. SPY."""
        returns = self.returns

        rolling_vol_20 = returns.rolling(20).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        rolling_vol_60 = returns.rolling(60).std() * np.sqrt(TRADING_DAYS_PER_YEAR)

        rolling_vol_20_series = [
            {"date": str(idx.date()), "volatility": _pct(value)}
            for idx, value in rolling_vol_20.tail(HISTORY_TAIL).items()
        ]
        rolling_vol_60_series = [
            {"date": str(idx.date()), "volatility": _pct(value)}
            for idx, value in rolling_vol_60.tail(HISTORY_TAIL).items()
        ]

        current_vol = _clean(rolling_vol_20.iloc[-1]) if len(rolling_vol_20.dropna()) else None

        past_year_vol = rolling_vol_20.dropna().tail(TRADING_DAYS_PER_YEAR)
        volatility_percentile = None
        if current_vol is not None and len(past_year_vol):
            volatility_percentile = _clean((past_year_vol <= current_vol).mean() * 100)

        current_vol_pct = _pct(current_vol)
        volatility_regime = None
        if current_vol_pct is not None:
            if current_vol_pct > VOLATILITY_EXTREME_THRESHOLD:
                volatility_regime = "extreme"
            elif current_vol_pct > VOLATILITY_HIGH_THRESHOLD:
                volatility_regime = "high"
            elif current_vol_pct >= VOLATILITY_NORMAL_MIN_THRESHOLD:
                volatility_regime = "normal"
            else:
                volatility_regime = "low"

        spy_rolling_vol_20 = self.spy_returns.rolling(20).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        spy_current_vol = _clean(spy_rolling_vol_20.iloc[-1]) if len(spy_rolling_vol_20.dropna()) else None

        relative_volatility = None
        if current_vol and spy_current_vol:
            relative_volatility = current_vol / spy_current_vol

        return {
            "rolling_vol_20": rolling_vol_20_series,
            "rolling_vol_60": rolling_vol_60_series,
            "current_volatility": current_vol_pct,
            "volatility_percentile": volatility_percentile,
            "volatility_regime": volatility_regime,
            "spy_current_volatility": _pct(spy_current_vol),
            "relative_volatility": _clean(relative_volatility),
        }

    def get_correlation_matrix(self) -> Dict:
        """Correlation matrix vs. `CORRELATION_TICKERS` (SPY/QQQ/GLD/TLT/BTC-USD)."""
        tickers = list(dict.fromkeys([self.ticker] + CORRELATION_TICKERS))

        series = {}
        for t in tickers:
            try:
                if t == self.ticker:
                    s = self.close
                elif t == "SPY":
                    s = self.spy_close
                else:
                    s = yf.Ticker(t).history(period=self.period)["Close"].dropna()
                # Tickers can have different timezones (BTC-USD is UTC, stocks aren't), so normalize before joining.
                s = s.copy()
                s.index = s.index.tz_localize(None).normalize()
                series[t] = s
            except Exception:
                continue

        prices = pd.concat(series, axis=1, join="inner").dropna()
        returns = prices.pct_change().dropna()

        if returns.empty:
            return {"matrix": {}, "ticker_vs_spy": None, "ticker_vs_spy_interpretation": None}

        corr = returns.corr()
        matrix = {
            row: {col: _clean(corr.loc[row, col]) for col in corr.columns}
            for row in corr.index
        }

        ticker_vs_spy = matrix.get(self.ticker, {}).get("SPY")

        interpretation = None
        if ticker_vs_spy is not None:
            abs_corr = abs(ticker_vs_spy)
            if abs_corr > CORRELATION_HIGH_THRESHOLD:
                interpretation = "high"
            elif abs_corr >= CORRELATION_MODERATE_THRESHOLD:
                interpretation = "moderate"
            else:
                interpretation = "low"

        return {
            "matrix": matrix,
            "ticker_vs_spy": ticker_vs_spy,
            "ticker_vs_spy_interpretation": interpretation,
        }

    def _compute_risk_score(self, returns_metrics: Optional[Dict], ratios: Optional[Dict], drawdown: Optional[Dict]) -> float:
        """Blend volatility, drawdown, beta, Sharpe, and Sortino into one 0-100 risk score."""
        score = 0.0

        vol = returns_metrics.get("annualized_volatility") if returns_metrics else None
        if vol is not None:
            if vol > VOLATILITY_EXTREME_THRESHOLD:
                score += RISK_SCORE_VOL_EXTREME_PTS
            elif vol > VOLATILITY_HIGH_THRESHOLD:
                score += RISK_SCORE_VOL_HIGH_PTS
            elif vol >= VOLATILITY_NORMAL_MIN_THRESHOLD:
                score += RISK_SCORE_VOL_NORMAL_PTS

        max_dd = abs(drawdown.get("max_drawdown")) if drawdown and drawdown.get("max_drawdown") is not None else None
        if max_dd is not None:
            if max_dd > RISK_SCORE_DD_SEVERE_THRESHOLD:
                score += RISK_SCORE_DD_SEVERE_PTS
            elif max_dd > RISK_SCORE_DD_MODERATE_THRESHOLD:
                score += RISK_SCORE_DD_MODERATE_PTS
            else:
                score += RISK_SCORE_DD_MILD_PTS

        beta = ratios.get("beta") if ratios else None
        if beta is not None:
            if beta > BETA_AGGRESSIVE_THRESHOLD:
                score += RISK_SCORE_BETA_AGGRESSIVE_PTS
            elif beta >= BETA_MODERATE_MIN_THRESHOLD:
                score += RISK_SCORE_BETA_MODERATE_PTS
            else:
                score += RISK_SCORE_BETA_DEFENSIVE_PTS

        sharpe = ratios.get("sharpe_ratio") if ratios else None
        if sharpe is not None:
            if sharpe < SHARPE_ACCEPTABLE_THRESHOLD:
                score += RISK_SCORE_SHARPE_POOR_PTS
            elif sharpe <= SHARPE_GOOD_THRESHOLD:
                score += RISK_SCORE_SHARPE_ACCEPTABLE_PTS
            else:
                score += RISK_SCORE_SHARPE_GOOD_PTS

        sortino = ratios.get("sortino_ratio") if ratios else None
        if sortino is not None and sortino > RISK_SCORE_SORTINO_EXCELLENT_THRESHOLD:
            score += RISK_SCORE_SORTINO_BONUS_PTS

        return max(0.0, min(100.0, score))

    def _risk_label(self, risk_score: float) -> str:
        """Classify a 0-100 risk score into Conservative/Moderate/Aggressive/Speculative."""
        if risk_score < RISK_LABEL_CONSERVATIVE_MAX:
            return "Conservative"
        if risk_score <= RISK_LABEL_MODERATE_MAX:
            return "Moderate"
        if risk_score <= RISK_LABEL_AGGRESSIVE_MAX:
            return "Aggressive"
        return "Speculative"

    def get_full_risk_analysis(self) -> Dict:
        """Aggregate returns, ratios, drawdown, VaR, volatility, and correlations into one risk score; each piece runs in its own try/except so one failure doesn't break the rest."""
        try:
            returns_metrics = self.get_return_metrics()
        except Exception:
            returns_metrics = None

        try:
            ratios = self.get_risk_ratios()
        except Exception:
            ratios = None

        try:
            drawdown = self.get_drawdown_analysis()
        except Exception:
            drawdown = None

        try:
            var = self.get_var_analysis()
        except Exception:
            var = None

        try:
            volatility = self.get_volatility_analysis()
        except Exception:
            volatility = None

        try:
            correlations = self.get_correlation_matrix()
        except Exception:
            correlations = None

        risk_score = self._compute_risk_score(returns_metrics, ratios, drawdown)

        return {
            "ticker": self.ticker,
            "returns": returns_metrics,
            "ratios": ratios,
            "drawdown": drawdown,
            "var": var,
            "volatility": volatility,
            "correlations": correlations,
            "risk_score": round(risk_score, 1),
            "risk_label": self._risk_label(risk_score),
        }
