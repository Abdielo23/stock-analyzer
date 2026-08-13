"""Fundamental analysis: income, balance sheet, cash flow, and profitability metrics plus a 0-100 health score.

Pulls from yfinance; a missing statement line becomes None instead of raising.
"""

from typing import Dict, Optional

import numpy as np
import yfinance as yf

# Each metric gets partial credit between a low and high threshold; the weights below add up to 100.
HEALTH_SCORE_MAX = 100.0
HEALTH_SCORE_MIN = 0.0

GROSS_MARGIN_LOW, GROSS_MARGIN_HIGH, GROSS_MARGIN_WEIGHT = 0.20, 0.50, 7
OPERATING_MARGIN_LOW, OPERATING_MARGIN_HIGH, OPERATING_MARGIN_WEIGHT = 0.05, 0.25, 9
NET_MARGIN_LOW, NET_MARGIN_HIGH, NET_MARGIN_WEIGHT = 0.03, 0.20, 9
DEBT_TO_EQUITY_LOW, DEBT_TO_EQUITY_HIGH, DEBT_TO_EQUITY_PENALTY_WEIGHT = 0.3, 2.0, 25
POSITIVE_FCF_POINTS = 15
POSITIVE_FCF_GROWTH_POINTS = 10
ROE_LOW, ROE_HIGH, ROE_WEIGHT = 0.0, 0.15, 12.5
ROIC_LOW, ROIC_HIGH, ROIC_WEIGHT = 0.0, 0.15, 12.5


def _clean(value: object) -> Optional[float]:
    """Cast to float, collapsing None/NaN/unparseable values to None."""
    try:
        if value is None:
            return None
        if isinstance(value, float) and np.isnan(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _row(df, label: str, col: int = 0) -> Optional[float]:
    """Grabs one cell from a yfinance statement; returns None if the row/column is missing (common since schemas vary by ticker)."""
    try:
        value = df.loc[label].iloc[col]
        return _clean(value)
    except (KeyError, IndexError, AttributeError):
        return None


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Safe division: None if either operand is missing or the denominator is 0."""
    a, b = _clean(a), _clean(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def _growth(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Period-over-period growth rate as a fraction (0.10 = +10%)."""
    current, previous = _clean(current), _clean(previous)
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _score_range(value: Optional[float], low: float, high: float, weight: float) -> float:
    """Linear partial credit between `low` (0 pts) and `high` (full `weight`)."""
    if value is None:
        return 0.0
    if value <= low:
        return 0.0
    if value >= high:
        return weight
    return weight * (value - low) / (high - low)


class FundamentalAnalyzer:
    """Fetches and scores one ticker's core financial statements via yfinance."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        self._info = None
        self._financials = None
        self._balance_sheet = None
        self._cashflow = None

    @property
    def info(self) -> dict:
        """Cached yfinance info dict; falls back to {} so one bad field doesn't break every metric."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    @property
    def financials(self):
        """Cached annual income statement. No try/except on purpose — a failure here should surface as a 502, not look like zero revenue."""
        if self._financials is None:
            self._financials = self._stock.financials
        return self._financials

    @property
    def balance_sheet(self):
        """Cached balance sheet (same reasoning as `financials`)."""
        if self._balance_sheet is None:
            self._balance_sheet = self._stock.balance_sheet
        return self._balance_sheet

    @property
    def cashflow(self):
        """Cached cash flow statement (same reasoning as `financials`)."""
        if self._cashflow is None:
            self._cashflow = self._stock.cashflow
        return self._cashflow

    def get_income_metrics(self) -> Dict[str, Optional[float]]:
        """Revenue, margins, EBITDA, and EPS. Margins/growth are decimal fractions (0.469 = 46.9%), not percentages."""
        fin = self.financials

        revenue = _row(fin, "Total Revenue", 0)
        revenue_prev = _row(fin, "Total Revenue", 1)
        gross_profit = _row(fin, "Gross Profit", 0)
        operating_income = _row(fin, "Operating Income", 0)
        net_income = _row(fin, "Net Income", 0)
        ebitda = _row(fin, "EBITDA", 0)
        eps = _row(fin, "Diluted EPS", 0)
        eps_prev = _row(fin, "Diluted EPS", 1)

        return {
            "revenue": revenue,
            "revenue_growth": _growth(revenue, revenue_prev),
            "gross_margin": _div(gross_profit, revenue),
            "operating_margin": _div(operating_income, revenue),
            "net_margin": _div(net_income, revenue),
            "ebitda": ebitda,
            "ebitda_margin": _div(ebitda, revenue),
            "eps": eps,
            "eps_growth": _growth(eps, eps_prev),
        }

    def get_balance_metrics(self) -> Dict[str, Optional[float]]:
        """Liquidity and leverage ratios from the balance sheet."""
        bs = self.balance_sheet
        fin = self.financials

        total_assets = _row(bs, "Total Assets", 0)
        total_debt = _row(bs, "Total Debt", 0)
        total_equity = _row(bs, "Stockholders Equity", 0)
        cash = _row(bs, "Cash And Cash Equivalents", 0)
        current_assets = _row(bs, "Current Assets", 0)
        current_liabilities = _row(bs, "Current Liabilities", 0)
        inventory = _row(bs, "Inventory", 0)
        operating_income = _row(fin, "Operating Income", 0)
        interest_expense = _row(fin, "Interest Expense", 0)

        quick_assets = None
        if current_assets is not None and inventory is not None:
            quick_assets = current_assets - inventory

        return {
            "total_assets": total_assets,
            "total_debt": total_debt,
            "total_equity": total_equity,
            "cash": cash,
            "current_ratio": _div(current_assets, current_liabilities),
            "quick_ratio": _div(quick_assets, current_liabilities),
            "cash_ratio": _div(cash, current_liabilities),
            "debt_to_equity": _div(total_debt, total_equity),
            "debt_to_assets": _div(total_debt, total_assets),
            "interest_coverage": _div(operating_income, abs(interest_expense) if interest_expense is not None else None),
        }

    def get_cashflow_metrics(self) -> Dict[str, Optional[float]]:
        """Free cash flow and its margin/growth. Falls back to operating CF + capex when yfinance has no FCF line (capex is already negative)."""
        cf = self.cashflow
        fin = self.financials

        operating_cashflow = _row(cf, "Operating Cash Flow", 0)
        capex = _row(cf, "Capital Expenditure", 0)
        fcf = _row(cf, "Free Cash Flow", 0)
        fcf_prev = _row(cf, "Free Cash Flow", 1)
        revenue = _row(fin, "Total Revenue", 0)
        net_income = _row(fin, "Net Income", 0)

        if fcf is None and operating_cashflow is not None and capex is not None:
            fcf = operating_cashflow + capex

        return {
            "operating_cashflow": operating_cashflow,
            "capex": capex,
            "free_cashflow": fcf,
            "fcf_margin": _div(fcf, revenue),
            "fcf_growth": _growth(fcf, fcf_prev),
            "fcf_to_net_income": _div(fcf, net_income),
        }

    def get_profitability_metrics(self) -> Dict[str, Optional[float]]:
        """ROE, ROA, ROIC, and turnover/leverage ratios. ROIC's tax rate falls back to info["effectiveTaxRate"] when Tax Provision/Pretax Income is missing."""
        fin = self.financials
        bs = self.balance_sheet

        net_income = _row(fin, "Net Income", 0)
        operating_income = _row(fin, "Operating Income", 0)
        revenue = _row(fin, "Total Revenue", 0)
        total_assets = _row(bs, "Total Assets", 0)
        total_equity = _row(bs, "Stockholders Equity", 0)
        total_debt = _row(bs, "Total Debt", 0)
        cash = _row(bs, "Cash And Cash Equivalents", 0)
        invested_capital = _row(bs, "Invested Capital", 0)

        tax_provision = _row(fin, "Tax Provision", 0)
        pretax_income = _row(fin, "Pretax Income", 0)
        tax_rate = _div(tax_provision, pretax_income)
        if tax_rate is None:
            tax_rate = self.info.get("effectiveTaxRate")

        if invested_capital is None and total_debt is not None and total_equity is not None:
            invested_capital = total_debt + total_equity - (cash or 0)

        nopat = None
        if operating_income is not None and tax_rate is not None:
            nopat = operating_income * (1 - tax_rate)

        return {
            "roe": _div(net_income, total_equity),
            "roa": _div(net_income, total_assets),
            "roic": _div(nopat, invested_capital),
            "asset_turnover": _div(revenue, total_assets),
            "equity_multiplier": _div(total_assets, total_equity),
        }

    def _health_score(self, income: dict, balance: dict, cash: dict, profitability: dict) -> float:
        """Blend margins, leverage, FCF trend, and returns into one 0-100 score."""
        score = 0.0

        score += _score_range(income.get("gross_margin"), GROSS_MARGIN_LOW, GROSS_MARGIN_HIGH, GROSS_MARGIN_WEIGHT)
        score += _score_range(income.get("operating_margin"), OPERATING_MARGIN_LOW, OPERATING_MARGIN_HIGH, OPERATING_MARGIN_WEIGHT)
        score += _score_range(income.get("net_margin"), NET_MARGIN_LOW, NET_MARGIN_HIGH, NET_MARGIN_WEIGHT)

        debt_to_equity = balance.get("debt_to_equity")
        if debt_to_equity is None:
            debt_score = 0.0
        else:
            debt_score = DEBT_TO_EQUITY_PENALTY_WEIGHT - _score_range(
                debt_to_equity, DEBT_TO_EQUITY_LOW, DEBT_TO_EQUITY_HIGH, DEBT_TO_EQUITY_PENALTY_WEIGHT
            )
        score += max(0.0, debt_score)

        if cash.get("free_cashflow") is not None and cash["free_cashflow"] > 0:
            score += POSITIVE_FCF_POINTS
        if cash.get("fcf_growth") is not None and cash["fcf_growth"] > 0:
            score += POSITIVE_FCF_GROWTH_POINTS

        score += _score_range(profitability.get("roe"), ROE_LOW, ROE_HIGH, ROE_WEIGHT)
        score += _score_range(profitability.get("roic"), ROIC_LOW, ROIC_HIGH, ROIC_WEIGHT)

        return round(min(HEALTH_SCORE_MAX, max(HEALTH_SCORE_MIN, score)), 1)

    def get_full_analysis(self) -> Dict:
        """Runs all four metric groups plus the health score."""
        income = self.get_income_metrics()
        balance = self.get_balance_metrics()
        cash = self.get_cashflow_metrics()
        profitability = self.get_profitability_metrics()

        return {
            "ticker": self.ticker,
            "income": income,
            "balance": balance,
            "cashflow": cash,
            "profitability": profitability,
            "health_score": self._health_score(income, balance, cash, profitability),
        }
