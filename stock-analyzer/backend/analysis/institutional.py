"""Insider & institutional analysis — pulls from yfinance, SEC EDGAR full-text search, and Finviz into one combined "smart money" signal."""

import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from analysis._scraping import fetch_finviz_raw, parse_number as _parse_number

SEC_HEADERS = {"User-Agent": "stockanalyzer/1.0 contact@example.com"}
SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_SEARCH_RESULT_LIMIT = 20
SEC_INSIDER_SEARCH_LOOKBACK_DAYS = 365
SEC_13F_SEARCH_LOOKBACK_DAYS = 90
THIRTEEN_F_REQUEST_DELAY_SECONDS = 0.5

MAJOR_HOLDERS = ["Vanguard", "BlackRock", "Fidelity", "Berkshire", "State Street"]

INSIDER_TRANSACTIONS_LOOKBACK_YEARS = 1
TOP_N_HOLDERS = 10
TOP_N_RECENT_ACTIVITY = 10

# --- Insider buy/sell signal bands ---
BUY_SELL_RATIO_STRONG_BUY_MIN = 2
BUY_SELL_RATIO_BUY_MIN = 1
BUY_SELL_RATIO_STRONG_SELL_MAX = 0.25
BUY_SELL_RATIO_SELL_MAX = 0.5

# --- Smart-money combined signal thresholds ---
SMART_MONEY_INST_OWNERSHIP_BULLISH_MIN = 60
SMART_MONEY_SHORT_FLOAT_BULLISH_MAX = 5
SMART_MONEY_SHORT_FLOAT_BEARISH_MIN = 15


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


def _classify_transaction(text: Optional[str]) -> str:
    """Classify a yfinance insider-transaction "Text" field into a coarse type."""
    text = (text or "").lower()
    if "sale" in text:
        return "Sale"
    if "purchase" in text:
        return "Purchase"
    if "gift" in text:
        return "Gift"
    if "award" in text or "grant" in text:
        return "Award/Grant"
    return "Other"


class InstitutionalAnalyzer:
    """Fetches insider, institutional, and SEC-filing data for one ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        self._info = None

    @property
    def info(self) -> dict:
        """Lazily-fetched, cached ``yfinance`` info dict (``{}`` on failure)."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    def _fetch_current_insiders(self) -> List[dict]:
        """Current insider roster (name/position/shares/latest transaction date)."""
        try:
            current_insiders = []
            roster = self._stock.insider_roster_holders
            if roster is not None and not roster.empty:
                for _, row in roster.head(TOP_N_HOLDERS).iterrows():
                    current_insiders.append({
                        "name": row.get("Name"),
                        "position": row.get("Position"),
                        "shares_owned_directly": _clean(row.get("Shares Owned Directly")),
                        "latest_transaction_date": str(row.get("Latest Transaction Date")),
                    })
            return current_insiders
        except Exception:
            return []

    def _split_buys_and_sells(self, transactions: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Splits last year's transactions into buys/sells by reading the Text field, since yfinance's Transaction column is always blank; grants/gifts are excluded since they aren't real market signals."""
        df = transactions.copy()
        df["Text"] = df["Text"].fillna("")

        cutoff = pd.Timestamp.now() - pd.DateOffset(years=INSIDER_TRANSACTIONS_LOOKBACK_YEARS)
        recent = df[df["Start Date"] >= cutoff].copy()

        is_sale = recent["Text"].str.contains("Sale", case=False, na=False)
        is_purchase = recent["Text"].str.contains("Purchase", case=False, na=False)
        return recent[is_purchase], recent[is_sale]

    def _buy_sell_ratio_and_signal(self, total_buys: int, total_sells: int) -> Tuple[object, str]:
        """Compute the buy/sell ratio (or "all_buys") and its bullish/bearish signal."""
        buy_sell_ratio = None
        if total_sells == 0 and total_buys > 0:
            buy_sell_ratio = "all_buys"
        elif total_sells > 0:
            buy_sell_ratio = total_buys / total_sells

        signal = "neutral"
        if buy_sell_ratio == "all_buys" or (isinstance(buy_sell_ratio, (int, float)) and buy_sell_ratio > BUY_SELL_RATIO_STRONG_BUY_MIN):
            signal = "strong_buying"
        elif isinstance(buy_sell_ratio, (int, float)) and buy_sell_ratio > BUY_SELL_RATIO_BUY_MIN:
            signal = "buying"
        elif isinstance(buy_sell_ratio, (int, float)) and buy_sell_ratio < BUY_SELL_RATIO_STRONG_SELL_MAX:
            signal = "strong_selling"
        elif isinstance(buy_sell_ratio, (int, float)) and buy_sell_ratio < BUY_SELL_RATIO_SELL_MAX:
            signal = "selling"

        return buy_sell_ratio, signal

    def _row_to_transaction_dict(self, row: pd.Series) -> dict:
        """Shape one insider-transaction row into {name, shares, value, date}."""
        return {
            "name": row.get("Insider"),
            "shares": _clean(row.get("Shares")),
            "value": _clean(row.get("Value")),
            "date": str(row.get("Start Date").date()) if pd.notna(row.get("Start Date")) else None,
        }

    def _largest_transaction(self, df: pd.DataFrame) -> Optional[dict]:
        """The highest-value transaction in `df`, or None if `df` is empty."""
        if not len(df):
            return None
        ranked = df["Value"].fillna(0)
        return self._row_to_transaction_dict(df.loc[ranked.idxmax()])

    def _recent_activity(self, df: pd.DataFrame) -> List[dict]:
        """The most recent `TOP_N_RECENT_ACTIVITY` transactions, newest first."""
        recent_activity = []
        for _, row in df.sort_values("Start Date", ascending=False).head(TOP_N_RECENT_ACTIVITY).iterrows():
            recent_activity.append({
                "name": row.get("Insider"),
                "title": row.get("Position"),
                "transaction_type": _classify_transaction(row.get("Text")),
                "shares": _clean(row.get("Shares")),
                "value": _clean(row.get("Value")),
                "date": str(row["Start Date"].date()) if pd.notna(row["Start Date"]) else None,
            })
        return recent_activity

    def get_insider_trades(self) -> Dict:
        """Insider buy/sell tallies, largest trades, recent activity, and a signal; returns an empty shell if yfinance has no insider data for this ticker."""
        empty = {
            "total_buys": None, "total_sells": None, "buy_sell_ratio": None,
            "net_shares": None, "largest_buy": None, "largest_sell": None,
            "recent_activity": [], "current_insiders": [], "signal": None,
        }

        try:
            transactions = self._stock.insider_transactions
        except Exception:
            transactions = None

        if transactions is None or transactions.empty:
            return empty

        current_insiders = self._fetch_current_insiders()
        buys, sells = self._split_buys_and_sells(transactions)

        total_buys = len(buys)
        total_sells = len(sells)
        net_shares = _clean(buys["Shares"].sum() - sells["Shares"].sum())
        buy_sell_ratio, signal = self._buy_sell_ratio_and_signal(total_buys, total_sells)

        df = transactions.copy()
        df["Text"] = df["Text"].fillna("")

        return {
            "total_buys": total_buys,
            "total_sells": total_sells,
            "buy_sell_ratio": buy_sell_ratio if buy_sell_ratio == "all_buys" else _clean(buy_sell_ratio),
            "net_shares": net_shares,
            "largest_buy": self._largest_transaction(buys),
            "largest_sell": self._largest_transaction(sells),
            "recent_activity": self._recent_activity(df),
            "current_insiders": current_insiders,
            "signal": signal,
        }

    def get_institutional_holders(self) -> Dict:
        """Top institutional and mutual-fund holders, plus a "major holders present" check; each sub-fetch is wrapped separately since yfinance sometimes has one but not the others."""
        result = {
            "top_institutions": [], "top_funds": [],
            "total_inst_ownership_pct": None, "major_holders_present": {},
        }

        try:
            ih = self._stock.institutional_holders
            if ih is not None and not ih.empty:
                for _, row in ih.head(TOP_N_HOLDERS).iterrows():
                    result["top_institutions"].append({
                        "name": row.get("Holder"),
                        "shares": _clean(row.get("Shares")),
                        "value": _clean(row.get("Value")),
                        "pct_held": _clean(row.get("pctHeld") * 100) if row.get("pctHeld") is not None else None,
                        "date_reported": str(row.get("Date Reported")),
                    })
        except Exception:
            pass

        try:
            mh = self._stock.mutualfund_holders
            if mh is not None and not mh.empty:
                for _, row in mh.head(TOP_N_HOLDERS).iterrows():
                    result["top_funds"].append({
                        "name": row.get("Holder"),
                        "shares": _clean(row.get("Shares")),
                        "value": _clean(row.get("Value")),
                        "pct_held": _clean(row.get("pctHeld") * 100) if row.get("pctHeld") is not None else None,
                        "date_reported": str(row.get("Date Reported")),
                    })
        except Exception:
            pass

        try:
            held_pct = self.info.get("heldPercentInstitutions")
            result["total_inst_ownership_pct"] = _clean(held_pct * 100) if held_pct is not None else None
        except Exception:
            pass

        try:
            all_names = " ".join(
                [h["name"] or "" for h in result["top_institutions"] + result["top_funds"]]
            ).lower()
            result["major_holders_present"] = {
                name: name.lower() in all_names for name in MAJOR_HOLDERS
            }
        except Exception:
            result["major_holders_present"] = {name: False for name in MAJOR_HOLDERS}

        return result

    def scrape_sec_insider(self, ticker: Optional[str] = None) -> List[Dict]:
        """SEC EDGAR full-text search for recent Form 4 filings; never raises, returns [] if the API is rate-limited or down. `shares`/`price_per_share` are always None since the search index doesn't expose per-transaction amounts."""
        ticker = (ticker or self.ticker).upper()

        try:
            company_name = self.info.get("longName") or self.info.get("shortName") or ticker
            company_key = company_name.split()[0].lower()

            end = date.today()
            start = end - timedelta(days=SEC_INSIDER_SEARCH_LOOKBACK_DAYS)

            response = requests.get(
                SEC_SEARCH_URL,
                params={
                    "q": f'"{ticker}"',
                    "dateRange": "custom",
                    "startdt": start.isoformat(),
                    "enddt": end.isoformat(),
                    "forms": "4",
                },
                headers=SEC_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            hits = response.json().get("hits", {}).get("hits", [])[:SEC_SEARCH_RESULT_LIMIT]

            filings = []
            for hit in hits:
                source = hit.get("_source", {})
                display_names = source.get("display_names", [])
                filer_names = [d for d in display_names if company_key not in d.lower()]

                filings.append({
                    "filer_name": ", ".join(filer_names) if filer_names else ", ".join(display_names),
                    "filed_date": source.get("file_date"),
                    "form_type": source.get("form"),
                    "transaction_date": source.get("period_ending"),
                    "shares": None,
                    "price_per_share": None,
                })

            return filings
        except Exception:
            return []

    def scrape_finviz_ownership(self, ticker: Optional[str] = None) -> Dict[str, Optional[float]]:
        """Scrapes Finviz's ownership/short-interest fields; returns an all-None shell if the scrape fails."""
        ticker = (ticker or self.ticker).upper()
        result = {
            "insider_own_pct": None, "insider_trans_pct": None,
            "inst_own_pct": None, "inst_trans_pct": None,
            "short_float_pct": None, "short_ratio": None, "short_interest": None,
        }

        try:
            raw = fetch_finviz_raw(ticker)
            result["insider_own_pct"] = _parse_number(raw.get("Insider Own"))
            result["insider_trans_pct"] = _parse_number(raw.get("Insider Trans"))
            result["inst_own_pct"] = _parse_number(raw.get("Inst Own"))
            result["inst_trans_pct"] = _parse_number(raw.get("Inst Trans"))
            result["short_float_pct"] = _parse_number(raw.get("Short Float"))
            result["short_ratio"] = _parse_number(raw.get("Short Ratio"))
            result["short_interest"] = _parse_number(raw.get("Short Interest"))
        except Exception:
            pass

        return result

    def get_13f_changes(self) -> Dict:
        """SEC EDGAR search for 13F filers mentioning this ticker; kept out of the full analysis since 13F filings aren't indexed under the company's own CIK, so this only gets filer names, not real position changes."""
        note = "13F data requires SEC CIK lookup - available via EDGAR directly"

        try:
            end = date.today()
            start = end - timedelta(days=SEC_13F_SEARCH_LOOKBACK_DAYS)

            time.sleep(THIRTEEN_F_REQUEST_DELAY_SECONDS)
            response = requests.get(
                SEC_SEARCH_URL,
                params={
                    "q": f'"{self.ticker}"',
                    "dateRange": "custom",
                    "startdt": start.isoformat(),
                    "enddt": end.isoformat(),
                    "forms": "13F",
                },
                headers=SEC_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            hits = response.json().get("hits", {}).get("hits", [])[:SEC_SEARCH_RESULT_LIMIT]

            company_name = self.info.get("longName") or self.info.get("shortName") or self.ticker
            company_key = company_name.split()[0].lower()

            filers = set()
            for hit in hits:
                for name in hit.get("_source", {}).get("display_names", []):
                    if company_key not in name.lower():
                        filers.add(name)

            return {
                "note": note,
                "recent_13f_filers": sorted(filers),
            }
        except Exception:
            return {"note": note, "recent_13f_filers": []}

    def _smart_money_signal(self, insider_signal: Optional[str], inst_own_pct: Optional[float], short_float: Optional[float]) -> str:
        """Combine insider activity, institutional ownership, and short interest into one signal."""
        if (
            insider_signal in ("buying", "strong_buying")
            and inst_own_pct is not None and inst_own_pct > SMART_MONEY_INST_OWNERSHIP_BULLISH_MIN
            and short_float is not None and short_float < SMART_MONEY_SHORT_FLOAT_BULLISH_MAX
        ):
            return "bullish"
        if (
            insider_signal in ("selling", "strong_selling")
            and short_float is not None and short_float > SMART_MONEY_SHORT_FLOAT_BEARISH_MIN
        ):
            return "bearish"
        return "neutral"

    def get_full_institutional_analysis(self) -> Dict:
        """Aggregates insider trades, institutional holders, SEC filings, and a smart-money signal; each sub-call is wrapped separately so one failing data source doesn't break the rest."""
        try:
            insider_trades = self.get_insider_trades()
        except Exception:
            insider_trades = None

        try:
            institutional_holders = self.get_institutional_holders()
        except Exception:
            institutional_holders = None

        try:
            sec_filings = self.scrape_sec_insider()
        except Exception:
            sec_filings = []

        try:
            finviz_ownership = self.scrape_finviz_ownership()
        except Exception:
            finviz_ownership = None

        insider_signal = insider_trades.get("signal") if insider_trades else None
        inst_own_pct = institutional_holders.get("total_inst_ownership_pct") if institutional_holders else None
        short_float = finviz_ownership.get("short_float_pct") if finviz_ownership else None

        return {
            "ticker": self.ticker,
            "insider_trades": insider_trades,
            "institutional_holders": institutional_holders,
            "sec_filings": sec_filings,
            "finviz_ownership": finviz_ownership,
            "smart_money_signal": self._smart_money_signal(insider_signal, inst_own_pct, short_float),
        }
