from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from data.fetcher import get_price_history, get_fundamentals, get_stock_data
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
from analysis.summary import InvestmentSummaryAnalyzer

app = FastAPI(title="Stock Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store_cache(request, call_next):
    # This is a live-data API — every response must reflect the latest
    # yfinance/scrape pull, never a browser- or proxy-cached copy.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


# ======================================================================
# Module 1 — Data Layer (backend/data/fetcher.py)
# ======================================================================

# Raw OHLCV price history for a ticker.
@app.get("/stock/{ticker}/price")
def price(ticker: str, period: str = "1y"):
    try:
        return get_price_history(ticker, period)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# Key snapshot metrics (market cap, P/E, EPS, beta, etc.) from yfinance's info dict.
@app.get("/stock/{ticker}/fundamentals")
def fundamentals(ticker: str):
    try:
        return get_fundamentals(ticker)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# Combined price history + fundamentals snapshot in one call.
@app.get("/stock/{ticker}/all")
def all_data(ticker: str, period: str = "1y"):
    try:
        return get_stock_data(ticker, period)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 2 — Fundamental Analysis (analysis/fundamental.py)
# ======================================================================

# Income/balance/cash-flow metrics plus a composite 0-100 health score.
@app.get("/stock/{ticker}/fundamental")
def fundamental_analysis(ticker: str):
    try:
        return FundamentalAnalyzer(ticker).get_full_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 3 — Valuation (analysis/valuation.py)
# ======================================================================

# DCF intrinsic value, relative multiples vs. sector, Finviz + historical financials.
@app.get("/stock/{ticker}/valuation")
def valuation_analysis(ticker: str):
    try:
        return ValuationAnalyzer(ticker).get_full_valuation()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 4 — Advanced Technical Analysis (analysis/technical.py)
# ======================================================================

# Trend (SMA/EMA/ADX/Ichimoku), momentum (RSI/MACD/Stochastic/Bollinger), support/resistance.
@app.get("/stock/{ticker}/technical")
def technical_analysis(ticker: str, period: str = "1y"):
    try:
        return TechnicalAnalyzer(ticker, period).get_full_technical()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 5 — Volume & Flow (analysis/volume.py)
# ======================================================================

# OBV, Accumulation/Distribution, Chaikin Money Flow, Volume Profile, VWAP, RVOL.
@app.get("/stock/{ticker}/volume")
def volume_analysis(ticker: str, period: str = "1y"):
    try:
        return VolumeAnalyzer(ticker, period).get_full_volume_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 6 — Risk Analysis (analysis/risk.py)
# ======================================================================

# Return/volatility stats, Sharpe/Sortino/Calmar, drawdown, VaR/CVaR, correlations.
@app.get("/stock/{ticker}/risk")
def risk_analysis(ticker: str, period: str = "2y"):
    try:
        return RiskAnalyzer(ticker, period).get_full_risk_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 7 — Insider & Institutional (analysis/institutional.py)
# ======================================================================

# Insider buy/sell activity, top institutional/mutual-fund holders, SEC filings.
@app.get("/stock/{ticker}/institutional")
def institutional_analysis(ticker: str):
    try:
        return InstitutionalAnalyzer(ticker).get_full_institutional_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 8 — Sentiment & Macro (analysis/sentiment.py)
# ======================================================================

# Fear & Greed, VIX, FRED macro series, analyst ratings, news sentiment, sector performance.
@app.get("/stock/{ticker}/sentiment")
def sentiment_analysis(ticker: str):
    try:
        return SentimentAnalyzer(ticker).get_full_sentiment_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 9 — Earnings Analysis (analysis/earnings.py)
# ======================================================================

# Beat-rate history, next-earnings estimates, EPS/revenue trend, guidance, earnings quality.
@app.get("/stock/{ticker}/earnings")
def earnings_analysis(ticker: str):
    try:
        return EarningsAnalyzer(ticker).get_full_earnings_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 10 — Quantitative Analysis (analysis/quantitative.py)
# ======================================================================

# 5-factor scores, Monte Carlo simulation, strategy backtests, statistical analysis.
@app.get("/stock/{ticker}/quantitative")
def quantitative_analysis(ticker: str, period: str = "3y"):
    try:
        return QuantitativeAnalyzer(ticker, period).get_full_quantitative_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 11 — Social Sentiment (analysis/social.py)
# ======================================================================

# Reddit/WSB mention counts, VADER sentiment, meme signals (rockets/YOLO/DD posts).
@app.get("/stock/{ticker}/social")
def social_analysis(ticker: str):
    try:
        return SocialSentimentAnalyzer(ticker).get_full_social_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 12 — Global News & Geopolitical Risk (analysis/geopolitical.py)
# ======================================================================

# Ticker/sector news sentiment, GDELT events, weighted geopolitical risk score, global market context.
@app.get("/stock/{ticker}/geopolitical")
def geopolitical_analysis(ticker: str):
    try:
        return GeopoliticalAnalyzer(ticker).get_full_geopolitical_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 13 — Policy & Political Risk (analysis/political.py)
# ======================================================================

# Truth Social sentiment, Congress bill activity, Fed policy stance, executive orders.
@app.get("/stock/{ticker}/political")
def political_analysis(ticker: str):
    try:
        return PoliticalAnalyzer(ticker).get_full_political_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 14 — Advanced Macro & Supply Chain (analysis/macro.py)
# ======================================================================

# Yield curve, credit markets, commodities, sector-specific supply-chain risk, liquidity, sector rotation.
@app.get("/stock/{ticker}/macro")
def macro_analysis(ticker: str):
    try:
        return MacroAnalyzer(ticker).get_full_macro_analysis()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 15 — Economic Calendar & Fed Events (analysis/calendar.py)
# ======================================================================

# Ticker-specific unified calendar: FOMC dates, Fed speeches, economic releases, earnings, holidays.
@app.get("/stock/{ticker}/calendar")
def stock_calendar(ticker: str):
    try:
        return EconomicCalendarAnalyzer(ticker).get_full_calendar()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# General (non-ticker-specific) calendar view, using SPY as a sector-agnostic default.
@app.get("/calendar")
def general_calendar():
    try:
        # No ticker context — SPY has no yfinance "sector", so this
        # naturally yields the sector-agnostic "Default"/general market view.
        return EconomicCalendarAnalyzer("SPY").get_full_calendar()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ======================================================================
# Module 16 — Investment Summary (analysis/summary.py)
# ======================================================================

# Master aggregator: calls all 15 other modules, then builds the full statement + AI prompt + verdict.
# WARNING: slow — 60-120 seconds. Use a longer client-side timeout.
@app.get("/stock/{ticker}/summary")
def investment_summary(ticker: str):
    try:
        return InvestmentSummaryAnalyzer(ticker).get_full_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
