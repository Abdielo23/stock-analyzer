"""Module 13 — Policy & Political Risk.

Truth Social's RSS feed is dead and Congress.gov's DEMO_KEY has no working search, so we pull raw data and filter/score it ourselves.
"""

import time
from typing import Dict, List, Optional, Tuple

import feedparser
import numpy as np
import requests
import yfinance as yf

from utils.feed_utils import fetch_feed
from utils.fred_utils import fetch_fred_series
from utils.sentiment_utils import score_text

TRUTH_SOCIAL_RSS_URL = "https://truthsocial.com/@realDonaldTrump.rss"
CONGRESS_API_URL = "https://api.congress.gov/v3/bill"
CONGRESS_API_KEY = "DEMO_KEY"
FED_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
FEDERAL_REGISTER_URL = "https://www.federalregister.gov/api/v1/documents.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}

TRUTH_SOCIAL_POST_LIMIT = 20
MARKET_IMPACT_BULLISH_THRESHOLD = 0.2
MARKET_IMPACT_BEARISH_THRESHOLD = -0.2

CONGRESS_BILL_SEARCH_LIMIT = 250
CONGRESS_TOP_MATCHES = 10
CONGRESS_BILL_DETAIL_DELAY_SECONDS = 0.5

FED_ANNOUNCEMENTS_LIMIT = 10
EXECUTIVE_ORDER_PER_PAGE = 20
FULL_ANALYSIS_STEP_DELAY_SECONDS = 0.5

# --- Policy risk-score components (0-100 each) and blend weights ---
POLITICAL_SENTIMENT_RISK_NEGATIVE_THRESHOLD = -0.2
POLITICAL_SENTIMENT_RISK_POSITIVE_THRESHOLD = 0.2
POLITICAL_SENTIMENT_RISK_HIGH = 70
POLITICAL_SENTIMENT_RISK_LOW = 30
POLITICAL_SENTIMENT_RISK_NEUTRAL = 50
LEGISLATIVE_RISK_HIGH = 70
LEGISLATIVE_RISK_LOW = 30
LEGISLATIVE_RISK_NEUTRAL = 50
FED_POLICY_RISK_HIGH = 70
FED_POLICY_RISK_LOW = 30
FED_POLICY_RISK_NEUTRAL = 50
POLICY_RISK_WEIGHT_SENTIMENT = 0.30
POLICY_RISK_WEIGHT_LEGISLATIVE = 0.25
POLICY_RISK_WEIGHT_FED = 0.25
POLICY_RISK_WEIGHT_REGULATORY = 0.20
POLICY_RISK_LABEL_HIGH_THRESHOLD = 65
POLICY_RISK_LABEL_MODERATE_THRESHOLD = 35
REGULATORY_ENVIRONMENT_ELEVATED_THRESHOLD = 65

# --- Combined political-signal thresholds (matches policy-risk-label bands) ---
POLITICAL_SIGNAL_HIGH_THRESHOLD = 65
POLITICAL_SIGNAL_LOW_THRESHOLD = 35

MARKET_KEYWORDS = [
    "stock", "market", "economy", "trade", "tariff", "china", "tax", "rate",
    "inflation", "dollar", "energy", "oil", "crypto", "fed", "interest",
]

# Keyed on yfinance's actual sector strings, e.g. "Financial Services" not "Financial".
SECTOR_KEYWORDS = {
    "Technology": ["tech", "ai", "chip", "semiconductor", "apple", "google", "meta"],
    "Energy": ["oil", "gas", "energy", "pipeline", "drill"],
    "Financial Services": ["bank", "fed", "interest", "rate", "wall street"],
    "Healthcare": ["pharma", "drug", "medicare", "obamacare"],
    "Industrials": ["factory", "manufacturing", "steel", "aluminum"],
}

# Multi-word phrases avoid false positives from generic single words (e.g. "technology"
# matching "University of Science and Technology" in bill titles).
CONGRESS_RELEVANCE_KEYWORDS = {
    "Technology": ["artificial intelligence", "antitrust", "semiconductor", "big tech", "social media", "data privacy", "tech company"],
    "Healthcare": ["drug pric", "pharmaceutical", "medicare", "medicaid", "fda "],
    "Financial Services": ["banking regulation", "cryptocurrency", "digital asset", "dodd-frank", "financial institution"],
    "Energy": ["climate change", "oil and gas", "renewable energy", "pipeline", "carbon emission"],
}

POSITIVE_BILL_KEYWORDS = ["deregulation", "tax cut", "subsidy", "incentive", "relief", "promote"]
NEGATIVE_BILL_KEYWORDS = ["regulate", "control", "ban", "limit", "tax", "restrict", "fine", "penalty"]

REGULATORY_BASELINE = {
    "Technology": 65,
    "Healthcare": 70,
    "Financial Services": 60,
    "Energy": 55,
    "Consumer Cyclical": 45,
}

HISTORICAL_EVENTS = {
    "Technology": [
        {"event": "Trump tariffs on Chinese tech goods (2018-2019)",
         "impact": "Negative — supply chain disruption for Apple, semiconductors",
         "market_move": "-15% to -25% for affected stocks"},
        {"event": "Antitrust investigations Big Tech (2019-present)",
         "impact": "Negative — regulatory overhang on GOOGL, META, AMZN",
         "market_move": "Significant multiple compression"},
        {"event": "CHIPS Act signed (2022)",
         "impact": "Positive — $52B for domestic semiconductor manufacturing",
         "market_move": "+10% to +20% for US chip makers"},
        {"event": "AI Executive Order (2023)",
         "impact": "Mixed — safety requirements but validates AI importance",
         "market_move": "Minimal direct impact"},
        {"event": "China export controls on chips (2022-2024)",
         "impact": "Negative for NVDA, AMD — restricted China sales",
         "market_move": "-5% to -15% on announcement days"},
    ],
    "Energy": [
        {"event": "Paris Agreement withdrawal (2017, 2025)",
         "impact": "Positive for fossil fuels, negative for renewables",
         "market_move": "+5% to +10% for oil majors"},
        {"event": "Keystone XL cancellation (2021)",
         "impact": "Negative for pipeline companies",
         "market_move": "-8% for TransCanada"},
        {"event": "Inflation Reduction Act (2022)",
         "impact": "Positive for renewables/EV, mixed for traditional energy",
         "market_move": "+20% for clean energy ETFs"},
    ],
    "Healthcare": [
        {"event": "Medicare drug price negotiation (IRA 2022)",
         "impact": "Negative for pharma pricing power",
         "market_move": "-5% to -10% for targeted pharma companies"},
        {"event": "ACA repeal attempts (2017)",
         "impact": "Uncertainty for insurers and hospitals",
         "market_move": "High volatility, mixed outcomes"},
    ],
    "Financial Services": [
        {"event": "Dodd-Frank rollback (2018)",
         "impact": "Positive for regional banks",
         "market_move": "+10% to +15% for mid-size banks"},
        {"event": "Basel III endgame proposal (2023)",
         "impact": "Negative for large bank capital requirements",
         "market_move": "-5% for big banks on announcement"},
    ],
    "DEFAULT": [
        {"event": "Fed rate hikes 2022-2023 (500bps)",
         "impact": "Negative for growth stocks, positive for value/banks",
         "market_move": "S&P -20% in 2022"},
        {"event": "Trump tariffs 2025 (Liberation Day)",
         "impact": "Negative — broad market selloff, supply chain concerns",
         "market_move": "S&P -10% in days following announcement"},
        {"event": "COVID stimulus packages (2020-2021)",
         "impact": "Positive — massive liquidity injection",
         "market_move": "S&P +100% from March 2020 low"},
    ],
}


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


def _classify_bill_impact(title: str) -> str:
    """Classify a bill title as positive/negative/neutral for markets, via keyword counts."""
    title_lower = title.lower()
    positive_hits = sum(1 for kw in POSITIVE_BILL_KEYWORDS if kw in title_lower)
    # don't double-count "tax" against titles that already matched "tax cut"
    negative_keywords = NEGATIVE_BILL_KEYWORDS
    if "tax cut" in title_lower:
        negative_keywords = [kw for kw in NEGATIVE_BILL_KEYWORDS if kw != "tax"]
    negative_hits = sum(1 for kw in negative_keywords if kw in title_lower)

    if positive_hits > negative_hits:
        return "positive"
    if negative_hits > positive_hits:
        return "negative"
    return "neutral"


def _classify_fed_announcement(title: str) -> str:
    """Classify a Fed press-release title into a coarse announcement category."""
    t = title.lower()
    if any(k in t for k in ["federal funds rate", "fomc", "monetary policy"]):
        return "rate_decision"
    if any(k in t for k in ["balance sheet", "asset purchase", "quantitative"]):
        return "quantitative_easing"
    if any(k in t for k in ["minutes", "outlook", "statement"]):
        return "guidance"
    if "speech" in t or "remarks" in t:
        return "speech"
    return "announcement"


class PoliticalAnalyzer:
    """Computes policy/political risk context for one ticker's sector."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        info = {}
        try:
            info = self._stock.info or {}
        except Exception:
            pass
        self.company_name = info.get("longName") or info.get("shortName") or self.ticker
        self.sector = info.get("sector")

        self._truth_social_cache = None
        self._congress_cache = None
        self._fed_cache = None

    def _relevance_keywords(self) -> List[str]:
        """Market-wide keywords plus this ticker's sector-specific keywords."""
        return MARKET_KEYWORDS + SECTOR_KEYWORDS.get(self.sector, [])

    def get_truth_social_news(self) -> Dict:
        """Recent Truth Social posts filtered to market/sector-relevant ones, with sentiment.

        Fetches the feed directly (not via the shared feed_utils helper) so we can tell a
        network failure apart from the feed just being dead/empty.
        """
        if self._truth_social_cache is not None:
            return self._truth_social_cache

        empty = {
            "all_posts": [], "relevant_posts": [], "relevant_count": 0,
            "avg_sentiment": None, "market_impact_summary": None,
            "note": None,
        }

        try:
            response = requests.get(TRUTH_SOCIAL_RSS_URL, headers=HEADERS, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo or not feed.entries:
                result = dict(empty)
                result["note"] = "Truth Social RSS feed is currently unavailable or returned no parseable entries."
                self._truth_social_cache = result
                return result

            keywords = self._relevance_keywords()
            all_posts = []
            relevant_posts = []

            for entry in feed.entries[:TRUTH_SOCIAL_POST_LIMIT]:
                text = entry.get("title") or entry.get("summary") or ""
                compound = score_text(text)
                post = {
                    "text": text,
                    "published": entry.get("published"),
                    "link": entry.get("link"),
                    "sentiment_compound": compound,
                }
                all_posts.append(post)

                if any(kw in text.lower() for kw in keywords):
                    if compound is not None and compound > MARKET_IMPACT_BULLISH_THRESHOLD:
                        market_impact = "bullish"
                    elif compound is not None and compound < MARKET_IMPACT_BEARISH_THRESHOLD:
                        market_impact = "bearish"
                    else:
                        market_impact = "neutral"
                    relevant_posts.append({**post, "market_impact": market_impact})

            compounds = [p["sentiment_compound"] for p in relevant_posts if p["sentiment_compound"] is not None]
            avg_sentiment = _clean(sum(compounds) / len(compounds)) if compounds else None

            bullish = sum(1 for p in relevant_posts if p["market_impact"] == "bullish")
            bearish = sum(1 for p in relevant_posts if p["market_impact"] == "bearish")
            if not relevant_posts:
                market_impact_summary = None
            elif bullish > bearish:
                market_impact_summary = "bullish"
            elif bearish > bullish:
                market_impact_summary = "bearish"
            else:
                market_impact_summary = "neutral"

            result = {
                "all_posts": all_posts,
                "relevant_posts": relevant_posts,
                "relevant_count": len(relevant_posts),
                "avg_sentiment": avg_sentiment,
                "market_impact_summary": market_impact_summary,
                "note": None,
            }
        except Exception:
            result = dict(empty)
            result["note"] = "Could not reach the Truth Social RSS feed."

        self._truth_social_cache = result
        return result

    def _fetch_bill_detail(self, congress: str, bill_type: str, number: str) -> Optional[dict]:
        """Fetch one bill's detail record (sponsor, introduced date, status) from Congress.gov."""
        try:
            url = f"{CONGRESS_API_URL}/{congress}/{bill_type}/{number}"
            response = requests.get(
                url, params={"format": "json", "api_key": CONGRESS_API_KEY},
                headers=HEADERS, timeout=15,
            )
            response.raise_for_status()
            return response.json().get("bill")
        except Exception:
            return None

    def _search_relevant_bills(self, keywords: List[str]) -> List[dict]:
        """Fetch a recent-updates batch from Congress.gov and filter client-side by keyword.

        The API's `query` search parameter doesn't actually filter anything, so we pull a
        large recent batch and filter it ourselves.
        """
        response = requests.get(
            CONGRESS_API_URL,
            params={"format": "json", "limit": CONGRESS_BILL_SEARCH_LIMIT, "sort": "updateDate+desc", "api_key": CONGRESS_API_KEY},
            headers=HEADERS, timeout=15,
        )
        response.raise_for_status()
        bills = response.json().get("bills", [])
        matches = [b for b in bills if any(kw in (b.get("title") or "").lower() for kw in keywords)]
        return matches[:CONGRESS_TOP_MATCHES]

    def _build_bill_entries(self, top_matches: List[dict]) -> Tuple[List[dict], int, int]:
        """Fetch detail for each matched bill and classify its market impact."""
        recent_bills = []
        positive_count = 0
        negative_count = 0

        for i, b in enumerate(top_matches):
            detail = self._fetch_bill_detail(b.get("congress"), (b.get("type") or "").lower(), b.get("number"))
            if i < len(top_matches) - 1:
                time.sleep(CONGRESS_BILL_DETAIL_DELAY_SECONDS)

            title = b.get("title", "")
            sponsor, introduced_date, status = None, None, None
            if detail:
                sponsors = detail.get("sponsors") or []
                sponsor = sponsors[0].get("fullName") if sponsors else None
                introduced_date = detail.get("introducedDate")
                status = "Became Law" if detail.get("laws") else (detail.get("latestAction") or {}).get("text")

            impact = _classify_bill_impact(title)
            if impact == "positive":
                positive_count += 1
            elif impact == "negative":
                negative_count += 1

            recent_bills.append({
                "title": title,
                "bill_number": f"{(b.get('type') or '').upper()} {b.get('number')}",
                "introduced_date": introduced_date,
                "latest_action": (b.get("latestAction") or {}).get("text"),
                "sponsor": sponsor,
                "status": status,
                "impact": impact,
            })

        return recent_bills, positive_count, negative_count

    def get_congress_activity(self) -> Dict:
        """Recent sector-relevant bills from Congress.gov, with a legislative-risk signal. Cached."""
        if self._congress_cache is not None:
            return self._congress_cache

        empty = {"recent_bills": [], "sector_legislative_risk": None, "positive_bills_count": 0, "negative_bills_count": 0}

        try:
            keywords = CONGRESS_RELEVANCE_KEYWORDS.get(
                self.sector, [self.sector.lower()] if self.sector else ["regulation"]
            )
            top_matches = self._search_relevant_bills(keywords)
            recent_bills, positive_count, negative_count = self._build_bill_entries(top_matches)

            if positive_count > negative_count:
                sector_legislative_risk = "favorable"
            elif negative_count > positive_count:
                sector_legislative_risk = "unfavorable"
            else:
                sector_legislative_risk = "neutral"

            result = {
                "recent_bills": recent_bills,
                "sector_legislative_risk": sector_legislative_risk,
                "positive_bills_count": positive_count,
                "negative_bills_count": negative_count,
            }
        except Exception:
            result = empty

        self._congress_cache = result
        return result

    def _sector_fed_impact(self, fed_stance: Optional[str], has_qe: bool) -> str:
        """Classify how the current Fed stance (hiking/cutting/holding) affects this ticker's sector."""
        if has_qe:
            return "positive"
        if fed_stance == "hiking":
            if self.sector in ("Technology", "Real Estate", "Utilities"):
                return "negative"
            if self.sector == "Financial Services":
                return "positive"
            return "neutral"
        if fed_stance == "cutting":
            if self.sector in ("Technology", "Real Estate"):
                return "positive"
            if self.sector == "Financial Services":
                return "negative"
            return "neutral"
        return "neutral"

    def get_fed_policy_impact(self) -> Dict:
        """Recent Fed press releases (with sentiment) plus the current rate stance and sector impact. Cached."""
        if self._fed_cache is not None:
            return self._fed_cache

        announcements = []
        try:
            feed = fetch_feed(FED_RSS_URL)
            for entry in feed.entries[:FED_ANNOUNCEMENTS_LIMIT]:
                title = entry.get("title", "")
                announcements.append({
                    "title": title,
                    "published": entry.get("published"),
                    "link": entry.get("link"),
                    "sentiment_compound": score_text(title),
                    "category": _classify_fed_announcement(title),
                })
        except Exception:
            announcements = []

        time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)

        fed_stance = None
        try:
            df = fetch_fred_series("FEDFUNDS")
            current = _clean(df["FEDFUNDS"].iloc[-1])
            previous = _clean(df["FEDFUNDS"].iloc[-2]) if len(df) > 1 else None
            if current is not None and previous is not None:
                if current > previous:
                    fed_stance = "hiking"
                elif current < previous:
                    fed_stance = "cutting"
                else:
                    fed_stance = "holding"
        except Exception:
            fed_stance = None

        has_qe = any(a["category"] == "quantitative_easing" for a in announcements)

        result = {
            "recent_fed_announcements": announcements,
            "fed_stance": fed_stance,
            "sector_fed_impact": self._sector_fed_impact(fed_stance, has_qe),
        }
        self._fed_cache = result
        return result

    def get_executive_orders(self) -> Dict:
        """Recent executive orders from the Federal Register, filtered to sector-relevant ones."""
        empty = {"recent_executive_orders": [], "relevant_orders": [], "sector_relevant_count": 0}
        try:
            params = [
                ("fields[]", "title"), ("fields[]", "publication_date"), ("fields[]", "abstract"),
                ("conditions[type][]", "PRESDOCU"),
                ("conditions[presidential_document_type][]", "executive_order"),
                ("per_page", EXECUTIVE_ORDER_PER_PAGE),
            ]
            response = requests.get(FEDERAL_REGISTER_URL, params=params, headers=HEADERS, timeout=15)
            response.raise_for_status()
            results = response.json().get("results", [])

            keywords = self._relevance_keywords()
            orders = []
            relevant = []

            for r in results:
                title = r.get("title", "")
                abstract = r.get("abstract") or ""
                text = f"{title} {abstract}"
                order = {
                    "title": title,
                    "date": r.get("publication_date"),
                    "abstract": abstract or None,
                    "sentiment_compound": score_text(text),
                }
                orders.append(order)
                if any(kw in text.lower() for kw in keywords):
                    relevant.append(order)

            return {
                "recent_executive_orders": orders,
                "relevant_orders": relevant,
                "sector_relevant_count": len(relevant),
            }
        except Exception:
            return empty

    def _political_sentiment_risk(self, sentiment: Optional[float]) -> int:
        """Risk score from Truth Social sentiment (more negative = higher risk)."""
        if sentiment is None:
            return POLITICAL_SENTIMENT_RISK_NEUTRAL
        if sentiment < POLITICAL_SENTIMENT_RISK_NEGATIVE_THRESHOLD:
            return POLITICAL_SENTIMENT_RISK_HIGH
        if sentiment > POLITICAL_SENTIMENT_RISK_POSITIVE_THRESHOLD:
            return POLITICAL_SENTIMENT_RISK_LOW
        return POLITICAL_SENTIMENT_RISK_NEUTRAL

    def _legislative_risk(self, positive: int, negative: int) -> int:
        """Risk score from the balance of favorable vs. unfavorable pending bills."""
        if negative > positive:
            return LEGISLATIVE_RISK_HIGH
        if positive > negative:
            return LEGISLATIVE_RISK_LOW
        return LEGISLATIVE_RISK_NEUTRAL

    def _fed_policy_risk(self, sector_fed_impact: Optional[str]) -> int:
        """Risk score from whether the current Fed stance favors or hurts this sector."""
        if sector_fed_impact == "negative":
            return FED_POLICY_RISK_HIGH
        if sector_fed_impact == "positive":
            return FED_POLICY_RISK_LOW
        return FED_POLICY_RISK_NEUTRAL

    def get_policy_risk_score(self) -> Dict:
        """Weighted 0-100 policy risk score across sentiment/legislative/Fed/regulatory components."""
        truth_social = self.get_truth_social_news()
        congress = self.get_congress_activity()
        fed = self.get_fed_policy_impact()

        political_sentiment_risk = self._political_sentiment_risk(truth_social.get("avg_sentiment"))

        pos = congress.get("positive_bills_count", 0)
        neg = congress.get("negative_bills_count", 0)
        legislative_risk = self._legislative_risk(pos, neg)

        sector_fed_impact = fed.get("sector_fed_impact")
        fed_policy_risk = self._fed_policy_risk(sector_fed_impact)

        regulatory_environment = REGULATORY_BASELINE.get(self.sector, 50)

        overall = (
            political_sentiment_risk * POLICY_RISK_WEIGHT_SENTIMENT + legislative_risk * POLICY_RISK_WEIGHT_LEGISLATIVE
            + fed_policy_risk * POLICY_RISK_WEIGHT_FED + regulatory_environment * POLICY_RISK_WEIGHT_REGULATORY
        )

        if overall > POLICY_RISK_LABEL_HIGH_THRESHOLD:
            risk_label = "High Policy Risk"
        elif overall >= POLICY_RISK_LABEL_MODERATE_THRESHOLD:
            risk_label = "Moderate Policy Risk"
        else:
            risk_label = "Low Policy Risk"

        key_policy_risks = []
        if political_sentiment_risk >= POLITICAL_SENTIMENT_RISK_HIGH:
            key_policy_risks.append("Recent political rhetoric carries notably negative sentiment relevant to this company/sector")
        if legislative_risk >= LEGISLATIVE_RISK_HIGH:
            key_policy_risks.append(f"More unfavorable than favorable pending legislation ({neg} negative vs {pos} positive bills identified)")
        if fed_policy_risk >= FED_POLICY_RISK_HIGH:
            key_policy_risks.append(f"Current Fed policy stance ({fed.get('fed_stance')}) is unfavorable for the {self.sector} sector")
        if regulatory_environment >= REGULATORY_ENVIRONMENT_ELEVATED_THRESHOLD:
            key_policy_risks.append(f"{self.sector} sector carries an elevated baseline regulatory/political scrutiny risk")
        if not key_policy_risks:
            key_policy_risks.append("No significantly elevated policy risk factors identified at this time")

        return {
            "component_scores": {
                "political_sentiment_risk": political_sentiment_risk,
                "legislative_risk": legislative_risk,
                "fed_policy_risk": fed_policy_risk,
                "regulatory_environment": regulatory_environment,
            },
            "overall_policy_risk": _clean(overall),
            "risk_label": risk_label,
            "key_policy_risks": key_policy_risks,
        }

    def get_historical_policy_events(self) -> Dict:
        """Sector-specific plus default historical policy events and their market impact."""
        events = list(HISTORICAL_EVENTS.get(self.sector, []))
        events += HISTORICAL_EVENTS["DEFAULT"]
        return {"relevant_historical_events": events}

    def _political_signal(self, overall: Optional[float]) -> str:
        """Classify the overall policy risk score into High/Moderate/Low Risk."""
        if overall is not None and overall > POLITICAL_SIGNAL_HIGH_THRESHOLD:
            return "High Risk"
        if overall is not None and overall < POLITICAL_SIGNAL_LOW_THRESHOLD:
            return "Low Risk"
        return "Moderate Risk"

    def get_full_political_analysis(self) -> Dict:
        """Aggregate Truth Social, Congress, Fed policy, executive orders, and a policy risk score.

        Each sub-call is wrapped in its own try/except so one failing data source doesn't
        take down the whole endpoint.
        """
        try:
            truth_social = self.get_truth_social_news()
        except Exception:
            truth_social = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            congress = self.get_congress_activity()
        except Exception:
            congress = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            fed_policy = self.get_fed_policy_impact()
        except Exception:
            fed_policy = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            executive_orders = self.get_executive_orders()
        except Exception:
            executive_orders = None

        try:
            policy_risk = self.get_policy_risk_score()
        except Exception:
            policy_risk = None

        try:
            historical_events = self.get_historical_policy_events()
        except Exception:
            historical_events = {"relevant_historical_events": []}

        overall = policy_risk.get("overall_policy_risk") if policy_risk else None

        return {
            "ticker": self.ticker,
            "truth_social": {
                "relevant_posts": truth_social.get("relevant_posts") if truth_social else [],
                "avg_sentiment": truth_social.get("avg_sentiment") if truth_social else None,
                "market_impact_summary": truth_social.get("market_impact_summary") if truth_social else None,
                "note": truth_social.get("note") if truth_social else None,
            },
            "congress": {
                "recent_bills": congress.get("recent_bills") if congress else [],
                "sector_legislative_risk": congress.get("sector_legislative_risk") if congress else None,
            },
            "fed_policy": {
                "recent_announcements": fed_policy.get("recent_fed_announcements") if fed_policy else [],
                "sector_fed_impact": fed_policy.get("sector_fed_impact") if fed_policy else None,
            },
            "executive_orders": {
                "relevant_orders": executive_orders.get("relevant_orders") if executive_orders else [],
            },
            "policy_risk": {
                "overall_policy_risk": policy_risk.get("overall_policy_risk") if policy_risk else None,
                "risk_label": policy_risk.get("risk_label") if policy_risk else None,
                "key_policy_risks": policy_risk.get("key_policy_risks") if policy_risk else [],
            },
            "historical_events": historical_events,
            "political_signal": self._political_signal(overall),
        }
