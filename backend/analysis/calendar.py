"""Builds a unified calendar of FOMC meetings, Fed speeches, economic releases, earnings, and market holidays for a ticker.

FOMC dates are scraped from the Fed's HTML page, economic releases are a synthetic hand-computed calendar (not live data), and market holidays are hardcoded for the year.
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from analysis.earnings import EarningsAnalyzer
from utils.feed_utils import fetch_feed
from utils.sentiment_utils import score_text

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_SPEECHES_RSS_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
HEADERS = {"User-Agent": "Mozilla/5.0"}

RECENT_SPEECH_WINDOW_DAYS = 30
FED_SPEECH_ALERT_WINDOW_DAYS = 7
FOMC_ALERT_WINDOW_DAYS = 7
CPI_NFP_ALERT_WINDOW_DAYS = 7
EARNINGS_ALERT_WINDOW_DAYS = 7
TIMELINE_ECONOMIC_RELEASE_WINDOW_DAYS = 30
TIMELINE_HOLIDAY_WINDOW_DAYS = 30
TIMELINE_EARNINGS_WINDOW_DAYS = 30
MOST_CRITICAL_WINDOW_DAYS = 14
MOST_CRITICAL_COUNT = 3
ECONOMIC_RELEASE_WINDOW_DAYS = 60
ECONOMIC_RELEASE_LOOKAHEAD_MONTHS = 4

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

FOMC_HISTORICAL_IMPACT = {
    "average_move_fomc_day": "+/-0.8%",
    "average_move_surprise_hike": "-1.5%",
    "average_move_surprise_cut": "+2.1%",
    "average_move_hold_as_expected": "+0.3%",
}

FOMC_SECTOR_SENSITIVITY = {
    "Technology": "High — growth stocks sensitive to rate changes",
    "Financial Services": "High — banks benefit from rate hikes",
    "Real Estate": "Very High — REITs hurt by rate hikes",
    "Utilities": "High — yield-sensitive sector",
    "Healthcare": "Low — defensive, less rate sensitive",
    "Energy": "Medium — more commodity driven",
    "Default": "Medium",
}

CHAIR_SPEECH_IMPACT = {
    "jackson_hole": "+/-1.5%",
    "regular_hawkish": "-0.8%",
    "regular_dovish": "+1.1%",
    "congressional_testimony": "+/-0.6%",
}

MAJOR_MARKET_MOVER_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "GS", "BAM", "V", "MA"]

# Hardcoded for the current year — Good Friday's date comes from the Easter algorithm, not a fixed day.
NYSE_HOLIDAYS_2026 = [
    ("New Year's Day", date(2026, 1, 1)),
    ("Martin Luther King Jr. Day", date(2026, 1, 19)),
    ("Presidents Day", date(2026, 2, 16)),
    ("Good Friday", date(2026, 4, 3)),
    ("Memorial Day", date(2026, 5, 25)),
    ("Juneteenth", date(2026, 6, 19)),
    ("Independence Day (observed)", date(2026, 7, 3)),
    ("Labor Day", date(2026, 9, 7)),
    ("Thanksgiving Day", date(2026, 11, 26)),
    ("Christmas Day", date(2026, 12, 25)),
]

# Expected dates for these are computed per-year by _release_candidate_date.
ECONOMIC_RELEASE_DEFINITIONS = [
    {"name": "CPI", "impact": "⚡⚡⚡ Very High",
     "description": "Consumer Price Index — most watched inflation gauge",
     "what_to_watch": "Watch core CPI (ex food/energy) MoM and YoY — a hot print raises odds of Fed hawkishness and pressures growth stocks."},
    {"name": "NFP", "impact": "⚡⚡⚡ Very High",
     "description": "Monthly jobs report — key Fed decision input",
     "what_to_watch": "Payroll growth, unemployment rate, and wage growth all feed directly into the Fed's dual mandate calculus."},
    {"name": "PPI", "impact": "⚡⚡ High",
     "description": "Producer Price Index — leading indicator for CPI",
     "what_to_watch": "Rising input-price pressure here often shows up in consumer prices (CPI) a month or two later."},
    {"name": "Retail Sales", "impact": "⚡⚡ High",
     "description": "Consumer spending health indicator",
     "what_to_watch": "Consumer spending drives ~70% of GDP — a surprise miss/beat can move Consumer Discretionary sharply."},
    {"name": "PCE", "impact": "⚡⚡⚡ Very High",
     "description": "Personal Consumption Expenditures — Fed's preferred inflation gauge",
     "what_to_watch": "This is the inflation measure the Fed itself targets — often moves markets more than CPI despite less media attention."},
    {"name": "Industrial Production", "impact": "⚡ Medium",
     "description": "Manufacturing and industrial output health check",
     "what_to_watch": "A read on factory-sector momentum; weakness here can foreshadow broader economic slowing."},
    {"name": "Housing Starts", "impact": "⚡ Medium",
     "description": "New residential construction activity",
     "what_to_watch": "Sensitive to mortgage rates — a weak print is a headwind for homebuilders and REITs."},
    {"name": "Consumer Confidence", "impact": "⚡⚡ High",
     "description": "Consumer sentiment about the economy",
     "what_to_watch": "A leading indicator for future spending — sharp drops can presage a slowdown in retail/discretionary demand."},
    {"name": "GDP Advance", "impact": "⚡⚡⚡ Very High",
     "description": "First GDP estimate — major market mover",
     "what_to_watch": "The first, roughest cut at quarterly growth — big surprises versus consensus move the whole market."},
    {"name": "GDP Final", "impact": "⚡⚡ High",
     "description": "Final revised GDP figure for the quarter",
     "what_to_watch": "Usually a smaller market mover than the Advance estimate since most of the surprise is already priced in."},
]
IMPACT_RANK = {"⚡⚡⚡ Very High": 3, "⚡⚡ High": 2, "⚡ Medium": 1}


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


def _sector_key(sector: Optional[str]) -> Optional[str]:
    """Map yfinance's real sector string onto FOMC_SECTOR_SENSITIVITY's keys."""
    if sector == "Financial Services":
        return "Financial Services"
    return sector


def _first_friday(year: int, month: int) -> date:
    """The first Friday of a given month (used for the NFP jobs report date)."""
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last occurrence of `weekday` (0=Monday) in a given month."""
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def _days_in_month(year: int, month: int) -> int:
    """Number of days in a given month."""
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


class EconomicCalendarAnalyzer:
    """Computes a unified economic/Fed/earnings calendar for one ticker's sector."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        info = {}
        try:
            info = self._stock.info or {}
        except Exception:
            pass
        self.sector = info.get("sector")

    # ------------------------------------------------------------------
    # 1. FOMC dates
    # ------------------------------------------------------------------

    def _parse_fomc_meetings(self, html: str) -> List[dict]:
        """Parse the FOMC calendar page's HTML into raw meeting-date records.

        There's no single table — headers and meeting rows are walked together to attribute each meeting to its year.
        """
        soup = BeautifulSoup(html, "lxml")
        elements = soup.find_all(["h4", "div"])

        current_year = None
        raw_meetings = []
        for el in elements:
            if el.name == "h4":
                m = re.search(r"(20\d{2})\s+FOMC Meetings", el.get_text())
                if m:
                    current_year = int(m.group(1))
                continue

            classes = el.get("class") or []
            if "fomc-meeting" in classes and "row" in classes:
                month_el = el.find(class_="fomc-meeting__month")
                date_el = el.find(class_="fomc-meeting__date")
                minutes_el = el.find(class_="fomc-meeting__minutes")
                if month_el and date_el and current_year:
                    raw_meetings.append({
                        "year": current_year,
                        "month_text": month_el.get_text(strip=True),
                        "date_text": date_el.get_text(strip=True),
                        "minutes_text": minutes_el.get_text(" ", strip=True) if minutes_el else "",
                    })

        meetings = []
        for raw in raw_meetings:
            parsed = self._parse_meeting_dates(raw["year"], raw["month_text"], raw["date_text"])
            if not parsed:
                continue
            meeting_date, decision_date = parsed

            minutes_release_date = None
            match = re.search(r"Released\s+(\w+\s+\d+,\s*\d+)", raw["minutes_text"])
            if match:
                try:
                    minutes_release_date = datetime.strptime(match.group(1), "%B %d, %Y").date()
                except ValueError:
                    minutes_release_date = None
            if minutes_release_date is None:
                minutes_release_date = decision_date + timedelta(weeks=3)

            meetings.append({
                "meeting_date": meeting_date.isoformat(),
                "decision_date": decision_date.isoformat(),
                # Fed holds a press conference after every meeting since 2019, but the page only
                # shows that text after the fact, so we just hardcode True instead of scraping it.
                "is_press_conference": True,
                "minutes_release_date": minutes_release_date.isoformat(),
                "_decision_date_obj": decision_date,
                "_meeting_year": raw["year"],
            })

        return meetings

    def _parse_meeting_dates(self, year: int, month_text: str, date_text: str) -> Optional[Tuple[date, date]]:
        """Parse one meeting's month/date-range text into (meeting_date, decision_date)."""
        clean = date_text.replace("*", "").strip()
        if "(" in clean or "-" not in clean:
            return None  # skip non-standard entries (e.g. notation votes)

        months = [m.strip() for m in month_text.split("/")]
        start_month = MONTH_ABBR.get(months[0][:3].lower())
        end_month = MONTH_ABBR.get(months[-1][:3].lower())
        if not start_month or not end_month:
            return None

        try:
            start_day_str, end_day_str = clean.split("-")
            start_day = int(re.sub(r"\D", "", start_day_str))
            end_day = int(re.sub(r"\D", "", end_day_str))
            meeting_date = date(year, start_month, start_day)
            decision_year = year + 1 if (end_month < start_month) else year
            decision_date = date(decision_year, end_month, end_day)
            return meeting_date, decision_date
        except (ValueError, IndexError):
            return None

    def get_fomc_dates(self) -> Dict:
        """Upcoming FOMC meetings for the current year, falling back to next year if none remain."""
        empty = {
            "upcoming_meetings": [], "next_fomc": None, "days_until_next_fomc": None,
            "minutes_release_dates": [], "historical_impact": FOMC_HISTORICAL_IMPACT,
            "sector_sensitivity": FOMC_SECTOR_SENSITIVITY.get(_sector_key(self.sector), FOMC_SECTOR_SENSITIVITY["Default"]),
        }

        try:
            response = requests.get(FOMC_CALENDAR_URL, headers=HEADERS, timeout=15)
            response.raise_for_status()
            meetings = self._parse_fomc_meetings(response.text)

            today = date.today()
            # If no meetings remain this year (e.g. querying in December), fall back to next year's schedule.
            upcoming = [
                m for m in meetings
                if m["_decision_date_obj"] >= today and m["_meeting_year"] == today.year
            ]
            if not upcoming:
                upcoming = [
                    m for m in meetings
                    if m["_decision_date_obj"] >= today and m["_meeting_year"] == today.year + 1
                ]
            upcoming.sort(key=lambda m: m["_decision_date_obj"])

            for m in upcoming:
                m["days_until"] = (m["_decision_date_obj"] - today).days
                del m["_decision_date_obj"]
                del m["_meeting_year"]

            next_fomc = upcoming[0]["decision_date"] if upcoming else None
            days_until_next_fomc = upcoming[0]["days_until"] if upcoming else None
            minutes_release_dates = [m["minutes_release_date"] for m in upcoming]

            return {
                "upcoming_meetings": upcoming,
                "next_fomc": next_fomc,
                "days_until_next_fomc": days_until_next_fomc,
                "minutes_release_dates": minutes_release_dates,
                "historical_impact": FOMC_HISTORICAL_IMPACT,
                "sector_sensitivity": FOMC_SECTOR_SENSITIVITY.get(_sector_key(self.sector), FOMC_SECTOR_SENSITIVITY["Default"]),
            }
        except Exception:
            return empty

    # ------------------------------------------------------------------
    # 2. Fed speeches
    # ------------------------------------------------------------------

    def get_fed_speeches(self) -> Dict:
        """Recent (last 30 days) and upcoming Fed speeches, with sentiment and chair-speech flagging.

        The RSS feed only contains past speeches, so upcoming_speeches ends up always empty.
        """
        empty = {
            "upcoming_speeches": [], "recent_speeches": [], "next_powell_speech": None,
            "powell_speeches_last_30d": 0, "chair_speech_impact": CHAIR_SPEECH_IMPACT,
        }

        try:
            feed = fetch_feed(FED_SPEECHES_RSS_URL)

            now = datetime.now(timezone.utc)
            upcoming, recent = [], []

            for entry in feed.entries:
                raw_title = entry.get("title", "")
                if "," in raw_title:
                    speaker, title = raw_title.split(",", 1)
                    speaker, title = speaker.strip(), title.strip()
                else:
                    speaker, title = None, raw_title

                description = entry.get("summary", "")
                published_parsed = entry.get("published_parsed")
                published_dt = (
                    datetime(*published_parsed[:6], tzinfo=timezone.utc) if published_parsed else None
                )

                compound = score_text(f"{title} {description}")
                is_chair_speech = bool(speaker and "powell" in speaker.lower())

                item = {
                    "speaker": speaker,
                    "title": title,
                    "date": entry.get("published"),
                    "description": description,
                    "url": entry.get("link"),
                    "is_chair_speech": is_chair_speech,
                    "sentiment_compound": compound,
                }

                if published_dt is None:
                    continue
                if published_dt > now:
                    item["days_until"] = (published_dt.date() - now.date()).days
                    upcoming.append(item)
                else:
                    days_ago = (now.date() - published_dt.date()).days
                    item["days_ago"] = days_ago
                    if days_ago <= RECENT_SPEECH_WINDOW_DAYS:
                        recent.append(item)

            upcoming.sort(key=lambda x: x["days_until"])
            recent.sort(key=lambda x: x["days_ago"])

            next_powell = next((s for s in upcoming if s["is_chair_speech"]), None)
            powell_last_30d = sum(1 for s in recent if s["is_chair_speech"])

            return {
                "upcoming_speeches": upcoming,
                "recent_speeches": recent,
                "next_powell_speech": next_powell,
                "powell_speeches_last_30d": powell_last_30d,
                "chair_speech_impact": CHAIR_SPEECH_IMPACT,
            }
        except Exception:
            return empty

    # ------------------------------------------------------------------
    # 3. Economic releases (synthetic calendar)
    # ------------------------------------------------------------------

    def _release_candidate_date(self, name: str, year: int, month: int) -> Optional[date]:
        """Hand-computed expected release date for one economic indicator in a given month."""
        if name == "CPI":
            return date(year, month, 12)
        if name == "NFP":
            return _first_friday(year, month)
        if name == "PPI":
            return date(year, month, 12) + timedelta(days=14)
        if name == "Retail Sales":
            return date(year, month, 15)
        if name == "PCE":
            return date(year, month, min(27, _days_in_month(year, month)))
        if name == "Industrial Production":
            return date(year, month, 16)
        if name == "Housing Starts":
            return date(year, month, 18)
        if name == "Consumer Confidence":
            return _last_weekday(year, month, 1)  # Tuesday
        if name == "GDP Advance":
            return date(year, month, 27) if month in (1, 4, 7, 10) else None
        if name == "GDP Final":
            return date(year, month, 27) if month in (2, 5, 8, 11) else None
        return None

    def _release_sector_sensitivity(self, name: str, sector_key: Optional[str]) -> Optional[str]:
        """Sector-specific interpretation note for CPI and Housing Starts releases."""
        if name == "CPI":
            if sector_key in ("Technology",):
                return "High inflation print → negative; low/cooling inflation → positive for growth/Tech valuations"
            if sector_key in ("Financial Services",):
                return "High inflation print → positive (higher-for-longer rates); low inflation → negative for bank margins"
            if sector_key == "Energy":
                return "High inflation print → typically positive for Energy pricing power"
        elif name == "Housing Starts":
            return "Weak print → negative for Real Estate/REITs and homebuilders"
        return None

    def get_economic_releases(self) -> Dict:
        """Synthetic 60-day calendar of major US economic data releases.

        This file is named calendar.py on purpose but avoids `import calendar` (stdlib) to prevent shadowing.
        """
        sector_key = _sector_key(self.sector)
        today = date.today()
        releases = []

        for defn in ECONOMIC_RELEASE_DEFINITIONS:
            for month_offset in range(0, ECONOMIC_RELEASE_LOOKAHEAD_MONTHS):
                target_month = today.month - 1 + month_offset
                target_year = today.year + target_month // 12
                target_month = target_month % 12 + 1

                candidate = self._release_candidate_date(defn["name"], target_year, target_month)
                if candidate is None:
                    continue
                days_until = (candidate - today).days
                if 0 <= days_until <= ECONOMIC_RELEASE_WINDOW_DAYS:
                    entry = dict(defn)
                    entry["expected_date"] = candidate.isoformat()
                    entry["days_until"] = days_until
                    entry["sector_sensitivity"] = self._release_sector_sensitivity(defn["name"], sector_key)
                    releases.append(entry)

        releases.sort(key=lambda r: r["days_until"])
        next_30_days = [r for r in releases if r["days_until"] <= 30]

        highest_impact_upcoming = sorted(
            releases, key=lambda r: (-IMPACT_RANK.get(r["impact"], 0), r["days_until"])
        )[:3]

        return {
            "next_30_days": next_30_days,
            "next_60_days": releases,
            "highest_impact_upcoming": highest_impact_upcoming,
        }

    # ------------------------------------------------------------------
    # 4. Earnings season calendar
    # ------------------------------------------------------------------

    def get_earnings_season_calendar(self) -> Dict:
        """This ticker's next earnings date plus major market-mover tickers' next earnings dates."""
        month = date.today().month
        peak_months = {1, 2, 4, 5, 7, 8, 10, 11}
        earnings_season_phase = "Peak earnings season" if month in peak_months else "Off season"

        try:
            ticker_next_earnings = EarningsAnalyzer(self.ticker).get_next_earnings()
        except Exception:
            ticker_next_earnings = None

        major_earnings_this_month = []
        for sym in MAJOR_MARKET_MOVER_TICKERS:
            try:
                next_earnings = EarningsAnalyzer(sym).get_next_earnings()
                major_earnings_this_month.append({
                    "ticker": sym,
                    "next_earnings_date": next_earnings.get("next_earnings_date"),
                    "days_until_earnings": next_earnings.get("days_until_earnings"),
                })
            except Exception:
                major_earnings_this_month.append({"ticker": sym, "next_earnings_date": None, "days_until_earnings": None})

        major_earnings_this_month.sort(
            key=lambda e: e["days_until_earnings"] if e["days_until_earnings"] is not None else 9999
        )

        return {
            "earnings_season_phase": earnings_season_phase,
            "ticker_next_earnings": ticker_next_earnings,
            "major_earnings_this_month": major_earnings_this_month,
        }

    # ------------------------------------------------------------------
    # 5. Market holidays
    # ------------------------------------------------------------------

    def get_market_holidays(self) -> Dict:
        """Remaining NYSE market holidays for the rest of this year."""
        today = date.today()
        upcoming = []
        for name, d in NYSE_HOLIDAYS_2026:
            days_until = (d - today).days
            if days_until >= 0:
                upcoming.append({"name": name, "date": d.isoformat(), "days_until": days_until})

        upcoming.sort(key=lambda h: h["days_until"])
        next_holiday = upcoming[0] if upcoming else None

        return {
            "upcoming_holidays": upcoming,
            "next_holiday": next_holiday,
            "days_until_next_holiday": next_holiday["days_until"] if next_holiday else None,
        }

    # ------------------------------------------------------------------
    # 6. Full calendar
    # ------------------------------------------------------------------

    def _build_unified_timeline(
        self, fomc: Optional[Dict], fed_speeches: Optional[Dict],
        economic_releases: Optional[Dict], earnings_calendar: Optional[Dict], market_holidays: Optional[Dict],
    ) -> List[dict]:
        """Merge FOMC/speech/release/earnings/holiday events into one date-sorted timeline."""
        timeline = []

        if fomc:
            for m in fomc["upcoming_meetings"]:
                timeline.append({
                    "date": m["decision_date"], "days_until": m["days_until"], "event_type": "fomc",
                    "title": "FOMC Rate Decision", "impact_level": "⚡⚡⚡ Very High",
                    "sector_relevance": fomc["sector_sensitivity"],
                })

        if fed_speeches:
            for s in fed_speeches["upcoming_speeches"]:
                timeline.append({
                    "date": s.get("date"), "days_until": s["days_until"], "event_type": "fed_speech",
                    "title": f"{s.get('speaker', 'Fed')}: {s['title']}", "impact_level": "⚡⚡ High" if s["is_chair_speech"] else "⚡ Medium",
                    "sector_relevance": "High for rate-sensitive sectors" if s["is_chair_speech"] else "Moderate",
                })

        if economic_releases:
            for r in economic_releases["next_30_days"]:
                timeline.append({
                    "date": r["expected_date"], "days_until": r["days_until"], "event_type": "economic_release",
                    "title": r["name"], "impact_level": r["impact"],
                    "sector_relevance": r.get("sector_sensitivity") or "General market impact",
                })

        if earnings_calendar and earnings_calendar.get("ticker_next_earnings"):
            te = earnings_calendar["ticker_next_earnings"]
            if te.get("days_until_earnings") is not None and 0 <= te["days_until_earnings"] <= TIMELINE_EARNINGS_WINDOW_DAYS:
                timeline.append({
                    "date": te.get("next_earnings_date"), "days_until": te["days_until_earnings"],
                    "event_type": "earnings", "title": f"{self.ticker} Earnings", "impact_level": "⚡⚡⚡ Very High",
                    "sector_relevance": f"Direct — {self.ticker}'s own report",
                })

        if market_holidays:
            for h in market_holidays["upcoming_holidays"]:
                if h["days_until"] <= TIMELINE_HOLIDAY_WINDOW_DAYS:
                    timeline.append({
                        "date": h["date"], "days_until": h["days_until"], "event_type": "market_holiday",
                        "title": f"{h['name']} (Market Closed)", "impact_level": "⚡ Medium",
                        "sector_relevance": "Low volume/volatility expected around this date",
                    })

        timeline.sort(key=lambda e: e["days_until"])
        return timeline

    def _build_alerts(
        self, fomc: Optional[Dict], economic_releases: Optional[Dict],
        fed_speeches: Optional[Dict], earnings_calendar: Optional[Dict], sector_label: str,
    ) -> List[str]:
        """Human-readable urgency alerts for events within their respective alert windows."""
        alerts = []
        if fomc and fomc.get("days_until_next_fomc") is not None and fomc["days_until_next_fomc"] < FOMC_ALERT_WINDOW_DAYS:
            alerts.append(f"⚠️ FOMC Decision in {fomc['days_until_next_fomc']} days — historically volatile for {sector_label}")

        for r in (economic_releases["next_30_days"] if economic_releases else []):
            if r["name"] == "CPI" and r["days_until"] < CPI_NFP_ALERT_WINDOW_DAYS:
                alerts.append(f"⚠️ CPI Release in {r['days_until']} days — key inflation print for Fed decision")
            if r["name"] == "NFP" and r["days_until"] < CPI_NFP_ALERT_WINDOW_DAYS:
                alerts.append(f"⚠️ NFP Jobs Report in {r['days_until']} days — major market catalyst")

        if fed_speeches and fed_speeches.get("next_powell_speech"):
            np_speech = fed_speeches["next_powell_speech"]
            if np_speech.get("days_until", 999) < FED_SPEECH_ALERT_WINDOW_DAYS:
                alerts.append(f"⚠️ Powell Speech in {np_speech['days_until']} days — watch for rate guidance signals")

        if earnings_calendar and earnings_calendar.get("ticker_next_earnings"):
            te = earnings_calendar["ticker_next_earnings"]
            if te.get("days_until_earnings") is not None and te["days_until_earnings"] < EARNINGS_ALERT_WINDOW_DAYS:
                alerts.append(f"⚠️ {self.ticker} Earnings in {te['days_until_earnings']} days — high volatility expected")

        return alerts

    def get_full_calendar(self) -> Dict:
        """Aggregate FOMC, Fed speeches, economic releases, earnings, and holidays into one calendar.

        Each piece is fetched in its own try/except so one failing source doesn't break the rest.
        """
        try:
            fomc = self.get_fomc_dates()
        except Exception:
            fomc = None

        try:
            fed_speeches = self.get_fed_speeches()
        except Exception:
            fed_speeches = None

        try:
            economic_releases = self.get_economic_releases()
        except Exception:
            economic_releases = None

        try:
            earnings_calendar = self.get_earnings_season_calendar()
        except Exception:
            earnings_calendar = None

        try:
            market_holidays = self.get_market_holidays()
        except Exception:
            market_holidays = None

        sector_label = self.sector or "this sector"
        timeline = self._build_unified_timeline(fomc, fed_speeches, economic_releases, earnings_calendar, market_holidays)
        alerts = self._build_alerts(fomc, economic_releases, fed_speeches, earnings_calendar, sector_label)

        most_critical_upcoming = sorted(
            [e for e in timeline if e["days_until"] <= MOST_CRITICAL_WINDOW_DAYS],
            key=lambda e: (-IMPACT_RANK.get(e["impact_level"], 0), e["days_until"]),
        )[:MOST_CRITICAL_COUNT]

        return {
            "ticker": self.ticker,
            "fomc": fomc,
            "fed_speeches": fed_speeches,
            "economic_releases": economic_releases,
            "earnings_calendar": earnings_calendar,
            "market_holidays": market_holidays,
            "unified_timeline": timeline,
            "alerts": alerts,
            "most_critical_upcoming": most_critical_upcoming,
        }
