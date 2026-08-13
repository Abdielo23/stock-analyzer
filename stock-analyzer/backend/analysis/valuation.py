"""Module 3 — Valuation.

DCF intrinsic value plus relative multiples vs. sector averages, backed by yfinance, Finviz, and stockanalysis.com scrapes.
"""

from typing import Dict, List, Optional, Tuple

import requests
import yfinance as yf
import numpy as np
from bs4 import BeautifulSoup

from analysis._scraping import fetch_finviz_raw, parse_number as _parse_number
from utils.sector_benchmarks import SectorBenchmarks

HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- DCF assumptions ---
RISK_FREE_RATE = 0.045
MARKET_PREMIUM = 0.055
TERMINAL_GROWTH = 0.025
PROJECTION_YEARS = 10
FCF_HISTORY_YEARS = 4
MIN_FCF_GROWTH_RATE = -0.05
MAX_FCF_GROWTH_RATE = 0.30

# --- Verdict thresholds: upside/downside % and multiple-signal counts ---
UNDERVALUED_UPSIDE_PCT = 15
OVERVALUED_DOWNSIDE_PCT = -15
MIN_CHEAP_OR_FAIR_MULTIPLES = 2
MIN_EXPENSIVE_MULTIPLES = 2

# --- Multiple signal bands: below 85% of sector avg is cheap, above 115% is expensive ---
MULTIPLE_CHEAP_RATIO = 0.85
MULTIPLE_EXPENSIVE_RATIO = 1.15

SECTOR_AVERAGES = {
    "Technology": {"PE": 28, "ForwardPE": 24, "EV_EBITDA": 20, "PB": 6},
    "Healthcare": {"PE": 22, "ForwardPE": 19, "EV_EBITDA": 15, "PB": 4},
    "Financial": {"PE": 13, "ForwardPE": 12, "EV_EBITDA": 10, "PB": 1.5},
    "Consumer": {"PE": 20, "ForwardPE": 18, "EV_EBITDA": 14, "PB": 3},
    "Energy": {"PE": 12, "ForwardPE": 11, "EV_EBITDA": 8, "PB": 2},
    "Default": {"PE": 20, "ForwardPE": 18, "EV_EBITDA": 14, "PB": 3},
}

SECTOR_MAP = {
    "Technology": "Technology",
    "Healthcare": "Healthcare",
    "Financial Services": "Financial",
    "Consumer Cyclical": "Consumer",
    "Consumer Defensive": "Consumer",
    "Energy": "Energy",
}


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


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Safe division: None if either operand is missing or the denominator is 0."""
    a, b = _clean(a), _clean(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


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


class ValuationAnalyzer:
    """Computes DCF + relative-multiple valuation for one ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        self._info = None
        self._financials = None
        self._balance_sheet = None
        self._cashflow = None

    @property
    def info(self) -> dict:
        """Cached yfinance info dict; returns {} on failure so one missing field doesn't break every metric."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    @property
    def financials(self):
        """Cached income statement; not caught here since missing data should surface as a real error, not a silent empty result."""
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

    def _wacc_components(self) -> Dict[str, Optional[float]]:
        """WACC via CAPM cost of equity + after-tax cost of debt; missing inputs leave outputs as None instead of guessing."""
        beta = self.info.get("beta")
        cost_of_equity = None
        if beta is not None:
            cost_of_equity = RISK_FREE_RATE + beta * MARKET_PREMIUM

        interest_expense = _first_valid(self.financials, "Interest Expense")
        total_debt = _first_valid(self.balance_sheet, "Total Debt")
        total_equity = _first_valid(self.balance_sheet, "Stockholders Equity")

        cost_of_debt = _div(abs(interest_expense) if interest_expense is not None else None, total_debt)

        tax_provision = _first_valid(self.financials, "Tax Provision")
        pretax_income = _first_valid(self.financials, "Pretax Income")
        tax_rate = _div(tax_provision, pretax_income)

        wacc = None
        if cost_of_equity is not None and total_debt is not None and total_equity is not None:
            total_capital = total_debt + total_equity
            if total_capital > 0:
                weight_equity = total_equity / total_capital
                weight_debt = total_debt / total_capital
                debt_term = weight_debt * (cost_of_debt or 0) * (1 - (tax_rate if tax_rate is not None else 0))
                wacc = weight_equity * cost_of_equity + debt_term

        return {
            "wacc": wacc,
            "cost_of_equity": cost_of_equity,
            "cost_of_debt": cost_of_debt,
            "tax_rate": tax_rate,
            "total_debt": total_debt,
            "total_equity": total_equity,
        }

    def _recent_fcf_history(self) -> List[float]:
        """Return up to the last `FCF_HISTORY_YEARS` reported FCF values (most recent first)."""
        try:
            fcf_row = self.cashflow.loc["Free Cash Flow"]
            fcf_history = [_clean(v) for v in fcf_row]
            return [v for v in fcf_history if v is not None][:FCF_HISTORY_YEARS]
        except (KeyError, AttributeError):
            return []

    def _fcf_growth_rate(self, fcf_history: List[float]) -> Optional[float]:
        """Average YoY FCF growth, clamped so one weird year doesn't blow up the multi-decade projection."""
        growth_rates = []
        for i in range(len(fcf_history) - 1):
            g = _div(fcf_history[i] - fcf_history[i + 1], abs(fcf_history[i + 1]))
            if g is not None:
                growth_rates.append(g)

        if not growth_rates:
            return None

        avg_growth = sum(growth_rates) / len(growth_rates)
        return max(MIN_FCF_GROWTH_RATE, min(MAX_FCF_GROWTH_RATE, avg_growth))

    def _dcf_valuation_scenario(self, upside_pct: Optional[float]) -> Optional[str]:
        """Classify DCF upside/downside into Undervalued/Overvalued/Fairly Valued."""
        if upside_pct is None:
            return None
        if upside_pct > UNDERVALUED_UPSIDE_PCT:
            return "Undervalued"
        if upside_pct < OVERVALUED_DOWNSIDE_PCT:
            return "Overvalued"
        return "Fairly Valued"

    def dcf_valuation(self) -> Optional[Dict]:
        """DCF valuation with a Gordon-growth terminal value; returns None with too little FCF history, or a partial dict if WACC can't be computed."""
        fcf_history = self._recent_fcf_history()
        if len(fcf_history) < 2:
            return None

        fcf_growth_rate = self._fcf_growth_rate(fcf_history)
        if fcf_growth_rate is None:
            return None

        wacc_data = self._wacc_components()
        wacc = wacc_data["wacc"]

        last_fcf = fcf_history[0]
        projected_fcfs = [last_fcf * (1 + fcf_growth_rate) ** t for t in range(1, PROJECTION_YEARS + 1)]
        current_price = self.info.get("currentPrice") or self.info.get("regularMarketPrice")

        if wacc is None or wacc <= TERMINAL_GROWTH:
            return {
                "wacc": wacc,
                "cost_of_equity": wacc_data["cost_of_equity"],
                "cost_of_debt": wacc_data["cost_of_debt"],
                "fcf_growth_rate": fcf_growth_rate,
                "projected_fcfs": projected_fcfs,
                "terminal_value": None,
                "intrinsic_value": None,
                "current_price": current_price,
                "upside_pct": None,
                "margin_of_safety": None,
                "scenario": None,
            }

        terminal_value = projected_fcfs[-1] * (1 + TERMINAL_GROWTH) / (wacc - TERMINAL_GROWTH)
        pv_fcfs = sum(fcf / (1 + wacc) ** t for t, fcf in enumerate(projected_fcfs, start=1))
        pv_terminal_value = terminal_value / (1 + wacc) ** PROJECTION_YEARS

        cash = _first_valid(self.balance_sheet, "Cash And Cash Equivalents")
        total_debt = wacc_data["total_debt"]
        net_debt = None
        if total_debt is not None and cash is not None:
            net_debt = total_debt - cash

        shares_outstanding = self.info.get("sharesOutstanding")

        intrinsic_value = None
        if shares_outstanding:
            equity_value = pv_fcfs + pv_terminal_value - (net_debt or 0)
            intrinsic_value = equity_value / shares_outstanding

        upside_pct = None
        margin_of_safety = None
        if intrinsic_value is not None and current_price:
            upside_pct = (intrinsic_value - current_price) / current_price * 100
            margin_of_safety = (intrinsic_value - current_price) / intrinsic_value * 100

        return {
            "wacc": wacc,
            "cost_of_equity": wacc_data["cost_of_equity"],
            "cost_of_debt": wacc_data["cost_of_debt"],
            "fcf_growth_rate": fcf_growth_rate,
            "projected_fcfs": projected_fcfs,
            "terminal_value": terminal_value,
            "intrinsic_value": intrinsic_value,
            "current_price": current_price,
            "upside_pct": upside_pct,
            "margin_of_safety": margin_of_safety,
            "scenario": self._dcf_valuation_scenario(upside_pct),
        }

    def _signal(self, value: Optional[float], avg: Optional[float]) -> Optional[str]:
        """Classify a multiple as cheap/expensive/fair relative to its sector average."""
        if value is None or avg is None:
            return None
        if value < avg * MULTIPLE_CHEAP_RATIO:
            return "cheap"
        if value > avg * MULTIPLE_EXPENSIVE_RATIO:
            return "expensive"
        return "fair"

    def multiples_valuation(self) -> Dict:
        """P/E, Forward P/E, PEG, EV/EBITDA, EV/Sales, Price/Book, Price/FCF vs. sector averages, falling back to a fixed table when the live sector benchmark is unavailable."""
        info = self.info

        pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        peg = info.get("pegRatio") or info.get("trailingPegRatio")
        ev_ebitda = info.get("enterpriseToEbitda")
        ev_sales = info.get("enterpriseToRevenue")
        price_book = info.get("priceToBook")
        price_fcf = _div(info.get("marketCap"), info.get("freeCashflow"))

        sector_key = SECTOR_MAP.get(info.get("sector"), "Default")
        fallback_avgs = SECTOR_AVERAGES[sector_key]

        try:
            dynamic_avgs = SectorBenchmarks().get_sector_multiples(info.get("sector"))
        except Exception:
            dynamic_avgs = {}

        pe_avg = dynamic_avgs.get("pe") or fallback_avgs["PE"]
        forward_pe_avg = dynamic_avgs.get("forward_pe") or fallback_avgs["ForwardPE"]
        ev_ebitda_avg = dynamic_avgs.get("ev_ebitda") or fallback_avgs["EV_EBITDA"]
        price_book_avg = dynamic_avgs.get("pb") or fallback_avgs["PB"]

        return {
            "sector": sector_key,
            "pe": {"value": pe, "sector_avg": pe_avg, "signal": self._signal(pe, pe_avg)},
            "forward_pe": {"value": forward_pe, "sector_avg": forward_pe_avg, "signal": self._signal(forward_pe, forward_pe_avg)},
            "peg": {"value": peg, "sector_avg": None, "signal": None},
            "ev_ebitda": {"value": ev_ebitda, "sector_avg": ev_ebitda_avg, "signal": self._signal(ev_ebitda, ev_ebitda_avg)},
            "ev_sales": {"value": ev_sales, "sector_avg": None, "signal": None},
            "price_book": {"value": price_book, "sector_avg": price_book_avg, "signal": self._signal(price_book, price_book_avg)},
            "price_fcf": {"value": price_fcf, "sector_avg": None, "signal": None},
        }

    def scrape_finviz(self, ticker: Optional[str] = None) -> Dict[str, Optional[float]]:
        """Scrapes Finviz's quote page; returns an all-None shell instead of raising since this data is just supplementary."""
        ticker = (ticker or self.ticker).upper()

        result = {
            "pe": None, "forward_pe": None, "peg": None, "eps_next_5y": None,
            "insider_own_pct": None, "inst_own_pct": None, "short_float_pct": None,
            "analyst_recommendation": None, "price_target": None,
            "52w_high": None, "52w_low": None, "rsi": None, "avg_volume": None,
        }

        try:
            raw = fetch_finviz_raw(ticker)

            field_map = {
                "pe": "P/E",
                "forward_pe": "Forward P/E",
                "peg": "PEG",
                "eps_next_5y": "EPS next 5Y",
                "insider_own_pct": "Insider Own",
                "inst_own_pct": "Inst Own",
                "short_float_pct": "Short Float",
                "analyst_recommendation": "Recom",
                "price_target": "Target Price",
                "52w_high": "52W High",
                "52w_low": "52W Low",
                "rsi": "RSI (14)",
                "avg_volume": "Avg Volume",
            }

            for key, label in field_map.items():
                try:
                    result[key] = _parse_number(raw.get(label))
                except Exception:
                    result[key] = None
        except Exception:
            pass

        return result

    def scrape_stockanalysis(self, ticker: Optional[str] = None) -> List[Dict]:
        """Scrapes stockanalysis.com's financials table for up to 5 years of history; returns [] on failure since the site's HTML isn't guaranteed stable."""
        ticker = (ticker or self.ticker).upper()
        url = f"https://stockanalysis.com/stocks/{ticker}/financials/"

        row_labels = {
            "revenue": "Revenue",
            "gross_profit": "Gross Profit",
            "operating_income": "Operating Income",
            "net_income": "Net Income",
            "eps": "Earnings Per Share",
        }

        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")

            table = soup.find("table")
            rows = [[td.get_text(strip=True) for td in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]

            header_row = rows[0]
            year_labels = header_row[2:]

            values_by_metric = {}
            for key, label in row_labels.items():
                for row in rows:
                    if not row or not row[0].startswith(label):
                        continue
                    data_cells = row[2:]
                    if any("%" in cell for cell in data_cells):
                        continue
                    values_by_metric[key] = data_cells
                    break

            years = []
            for i, year_label in enumerate(year_labels):
                entry = {"year": year_label}
                for key in row_labels:
                    cells = values_by_metric.get(key)
                    entry[key] = _parse_number(cells[i]) if cells and i < len(cells) else None
                entry["shares_outstanding"] = None
                entry["ebitda"] = None
                years.append(entry)

            return years
        except Exception:
            return []

    def _overall_verdict(self, dcf: Optional[Dict], multiples: Optional[Dict]) -> str:
        """Combines DCF upside and multiple signals into one verdict; needs both to agree before calling it under/overvalued."""
        dcf_upside = dcf.get("upside_pct") if dcf else None

        if multiples:
            benchmarked = [multiples["pe"], multiples["forward_pe"], multiples["ev_ebitda"], multiples["price_book"]]
            cheap_or_fair = sum(1 for m in benchmarked if m["signal"] in ("cheap", "fair"))
            expensive = sum(1 for m in benchmarked if m["signal"] == "expensive")
        else:
            cheap_or_fair = 0
            expensive = 0

        if dcf_upside is not None and dcf_upside > UNDERVALUED_UPSIDE_PCT and cheap_or_fair >= MIN_CHEAP_OR_FAIR_MULTIPLES:
            return "Undervalued"
        if dcf_upside is not None and dcf_upside < OVERVALUED_DOWNSIDE_PCT and expensive >= MIN_EXPENSIVE_MULTIPLES:
            return "Overvalued"
        return "Fairly Valued"

    def get_full_valuation(self) -> Dict:
        """Aggregates DCF, multiples, Finviz, and historical data; each piece is wrapped separately so one failing source doesn't break the rest."""
        try:
            dcf = self.dcf_valuation()
        except Exception:
            dcf = None

        try:
            multiples = self.multiples_valuation()
        except Exception:
            multiples = None

        try:
            finviz_data = self.scrape_finviz()
        except Exception:
            finviz_data = None

        try:
            historical_financials = self.scrape_stockanalysis()
        except Exception:
            historical_financials = None

        return {
            "ticker": self.ticker,
            "dcf": dcf,
            "multiples": multiples,
            "finviz_data": finviz_data,
            "historical_financials": historical_financials,
            "verdict": self._overall_verdict(dcf, multiples),
        }
