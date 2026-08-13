import yfinance as yf
import pandas as pd
import numpy as np


def _clean_value(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _df_to_records(df: pd.DataFrame, index_name: str = "date"):
    if df is None or df.empty:
        return []
    df = df.reset_index()
    df.columns = [str(c) for c in df.columns]
    if df.columns[0].lower() in ("date", "index"):
        df = df.rename(columns={df.columns[0]: index_name})
    records = df.to_dict(orient="records")
    return [{k: _clean_value(v) for k, v in row.items()} for row in records]


def _df_transposed_to_records(df: pd.DataFrame, index_name: str = "item"):
    """For statements where columns are dates and rows are line items."""
    if df is None or df.empty:
        return []
    df = df.transpose().reset_index()
    df.columns = [str(c) for c in df.columns]
    df = df.rename(columns={df.columns[0]: index_name})
    records = df.to_dict(orient="records")
    return [{k: _clean_value(v) for k, v in row.items()} for row in records]


def get_price_history(ticker: str, period: str = "1y"):
    stock = yf.Ticker(ticker)
    # yfinance can add a placeholder row for today before the market closes.
    history = stock.history(period=period).dropna(subset=["Close"])
    return _df_to_records(history, index_name="date")


def get_fundamentals(ticker: str):
    stock = yf.Ticker(ticker)
    info = stock.info or {}

    return {
        "ticker": ticker.upper(),
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "beta": info.get("beta"),
        "pe": {
            "trailing": info.get("trailingPE"),
            "forward": info.get("forwardPE"),
        },
        "eps": {
            "trailing": info.get("trailingEps"),
            "forward": info.get("forwardEps"),
        },
        "margins": {
            "gross": info.get("grossMargins"),
            "operating": info.get("operatingMargins"),
            "profit": info.get("profitMargins"),
        },
        "returns": {
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
        },
        "debt": {
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
        },
        "free_cash_flow": info.get("freeCashflow"),
        "analyst": {
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "recommendation": info.get("recommendationKey"),
            "recommendation_mean": info.get("recommendationMean"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
        },
        "description": info.get("longBusinessSummary"),
    }


def get_stock_data(ticker: str, period: str = "1y"):
    stock = yf.Ticker(ticker)

    info = stock.info or {}
    history = _df_to_records(stock.history(period=period).dropna(subset=["Close"]), index_name="date")
    dividends = _df_to_records(stock.dividends.to_frame(name="dividend") if stock.dividends is not None else None, index_name="date")

    income_statement = _df_transposed_to_records(stock.income_stmt, index_name="line_item")
    balance_sheet = _df_transposed_to_records(stock.balance_sheet, index_name="line_item")
    cash_flow = _df_transposed_to_records(stock.cashflow, index_name="line_item")

    try:
        insider_trades = _df_to_records(stock.insider_transactions, index_name="date")
    except Exception:
        insider_trades = []

    return {
        "ticker": ticker.upper(),
        "info": {k: _clean_value(v) for k, v in info.items()},
        "history": history,
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "dividends": dividends,
        "insider_trades": insider_trades,
    }
