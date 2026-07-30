"""Global news and geopolitical risk analysis: sentiment, GDELT events, risk score, and market context.

Reuters and AP News feeds are attempted but confirmed dead — see `NEWS_SOURCES`.
"""

import time
from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import numpy as np
import requests
import yfinance as yf

from utils.feed_utils import fetch_feed
from utils.sentiment_utils import score_text

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_MAX_RECORDS = 25
GDELT_TIMESPAN = "7d"

GOOGLE_NEWS_DEFAULT_MAX_RESULTS = 20
SECTOR_NEWS_MAX_RESULTS = 10
GOOGLE_NEWS_QUERY_DELAY_SECONDS = 1
SECTOR_NEWS_DELAY_SECONDS = 1
MULTI_SOURCE_NEWS_DELAY_SECONDS = 0.5
RSS_FEED_REQUEST_DELAY_SECONDS = 0.3
RSS_FEED_TIMEOUT_SECONDS = 10

DUPLICATE_TITLE_THRESHOLD = 0.8
MULTI_SOURCE_DEDUP_THRESHOLD = 0.7
MAX_MERGED_ARTICLES = 50

TOPIC_KEYWORDS = {
    "geopolitical": ["war", "invasion", "conflict", "missile", "sanction", "military", "troops", "nato", "nuclear"],
    "trade": ["tariff", "trade war", "export ban", "import", "customs", "wto", "trade deal", "embargo"],
    "supply_chain": ["supply chain", "shortage", "chip", "semiconductor", "factory", "manufacturing", "logistics", "shipping"],
    "regulatory": ["antitrust", "regulation", "ban", "lawsuit", "fine", "investigation", "sec", "ftc", "doj"],
    "political": ["congress", "senate", "election", "president", "policy", "legislation", "bill", "vote"],
    "macro": ["inflation", "recession", "gdp", "interest rate", "fed", "unemployment", "economy"],
}

# yfinance uses its own sector names, not GICS ones — e.g. "Consumer Cyclical" not "Consumer Discretionary".
CHINA_EXPOSED_SECTORS = {"Technology", "Consumer Cyclical", "Basic Materials", "Industrials"}
RUSSIA_EXPOSED_SECTORS = {"Energy", "Basic Materials"}
MIDDLE_EAST_EXPOSED_SECTORS = {"Energy"}

SUPPLY_CHAIN_HIGH = {"Technology", "Consumer Cyclical", "Industrials"}
SUPPLY_CHAIN_MEDIUM = {"Healthcare", "Basic Materials", "Consumer Defensive"}
SUPPLY_CHAIN_LOW = {"Financial Services", "Utilities", "Real Estate"}

SECTOR_NEWS_TERMS = {
    "Technology": "tech sector tariffs China semiconductors AI regulation",
    "Healthcare": "drug pricing regulation FDA pharmaceutical",
    "Financial Services": "banking regulation interest rates Fed policy",
    "Energy": "oil prices OPEC sanctions energy policy",
    "Consumer Cyclical": "consumer spending tariffs retail",
    "Industrials": "manufacturing tariffs supply chain infrastructure",
    "Basic Materials": "commodity prices China demand mining",
}

GLOBAL_MARKETS = {
    "^GSPC": "S&P 500", "^VIX": "VIX", "GC=F": "Gold", "CL=F": "Crude Oil",
    "DX-Y.NYB": "US Dollar Index", "^TNX": "10Y Treasury Yield",
    "^FTSE": "FTSE 100", "^N225": "Nikkei 225", "^HSI": "Hang Seng",
}

# benzinga's "markets" feed URL was repurposed and just returns 0 entries (not an error).
NEWS_SOURCES = {
    "reuters": {
        "business": "https://feeds.reuters.com/reuters/businessNews",
        "markets": "https://feeds.reuters.com/reuters/financialsNews",
        "technology": "https://feeds.reuters.com/reuters/technologyNews",
        "energy": "https://feeds.reuters.com/reuters/energyNews",
    },
    "marketwatch": {
        "top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "markets": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
        "real_time": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    },
    "seeking_alpha": {
        "ticker": "https://seekingalpha.com/symbol/{ticker}/feed.xml",
        "market": "https://seekingalpha.com/market_currents.xml",
    },
    "cnbc": {
        "top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "earnings": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
    },
    "benzinga": {
        "news": "https://www.benzinga.com/feed",
        "markets": "https://www.benzinga.com/markets/feed",
    },
    "ap_news": {
        "business": "https://rsshub.app/apnews/topics/business",
        "finance": "https://rsshub.app/apnews/topics/financial-markets",
    },
}

# --- Geopolitical risk-score components (0-100 each) and blend weights ---
CHINA_RISK_TECH = 70
CHINA_RISK_CONSUMER_CYCLICAL = 40
CHINA_RISK_DEFAULT = 20
RUSSIA_RISK_ENERGY = 60
RUSSIA_RISK_DEFAULT = 20
SUPPLY_CHAIN_RISK_HIGH = 70
SUPPLY_CHAIN_RISK_MEDIUM = 40
SUPPLY_CHAIN_RISK_LOW = 20
SUPPLY_CHAIN_RISK_DEFAULT = 40
REGULATORY_COUNT_HIGH_THRESHOLD = 5
REGULATORY_COUNT_MODERATE_THRESHOLD = 2
REGULATORY_RISK_HIGH = 70
REGULATORY_RISK_MODERATE = 40
REGULATORY_RISK_LOW = 20
NEWS_SENTIMENT_VERY_NEGATIVE_THRESHOLD = -0.3
NEWS_SENTIMENT_NEGATIVE_THRESHOLD = -0.1
NEWS_SENTIMENT_RISK_HIGH = 80
NEWS_SENTIMENT_RISK_MODERATE = 50
NEWS_SENTIMENT_RISK_LOW = 20
NEWS_SENTIMENT_RISK_UNKNOWN = 40
GEO_RISK_WEIGHT_CHINA = 0.25
GEO_RISK_WEIGHT_RUSSIA = 0.15
GEO_RISK_WEIGHT_SUPPLY_CHAIN = 0.25
GEO_RISK_WEIGHT_REGULATORY = 0.20
GEO_RISK_WEIGHT_NEWS_SENTIMENT = 0.15
GEO_RISK_LABEL_HIGH_THRESHOLD = 70
GEO_RISK_LABEL_MODERATE_THRESHOLD = 40

# --- Global market risk-on/risk-off signal thresholds ---
GOLD_RISK_OFF_THRESHOLD = 1
OIL_TENSION_THRESHOLD = 2
DOLLAR_RISK_OFF_THRESHOLD = 0.5
VIX_FEAR_INCREASING_THRESHOLD = 10
GLOBAL_RISK_MODE_VOTE_THRESHOLD = 3

# --- Combined geopolitical signal thresholds ---
HIGH_RISK_OVERALL_THRESHOLD = 65
LOW_RISK_OVERALL_THRESHOLD = 35
LOW_RISK_STRONGLY_POSITIVE_OVERALL_MAX = 50

# --- Multi-source sentiment consensus bands ---
CONSENSUS_STRONGLY_POSITIVE_THRESHOLD = 0.3
CONSENSUS_POSITIVE_THRESHOLD = 0.1
CONSENSUS_NEGATIVE_THRESHOLD = -0.1
CONSENSUS_STRONGLY_NEGATIVE_THRESHOLD = -0.3


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


def _classify_topic(title: str) -> Optional[str]:
    """Classify a headline into the topic (geopolitical/trade/supply_chain/etc.) with the most keyword hits."""
    title_lower = title.lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in title_lower)
        if count:
            scores[topic] = count
    return max(scores, key=scores.get) if scores else None


class GeopoliticalAnalyzer:
    """Computes geopolitical/global-news risk context for one ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        self._info = None
        self._ticker_news_cache = None

    @property
    def info(self) -> dict:
        """Lazily-fetched, cached ``yfinance`` info dict (``{}`` on failure)."""
        if self._info is None:
            try:
                self._info = self._stock.info or {}
            except Exception:
                self._info = {}
        return self._info

    @property
    def company_name(self) -> str:
        """The ticker's long/short name from `info`, falling back to the ticker symbol itself."""
        return self.info.get("longName") or self.info.get("shortName") or self.ticker

    def get_google_news(self, query: str, max_results: int = GOOGLE_NEWS_DEFAULT_MAX_RESULTS) -> List[dict]:
        """Fetch and score Google News RSS results for `query`, newest first; returns [] on failure."""
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            feed = fetch_feed(url)

            articles = []
            for entry in feed.entries[:max_results]:
                title = entry.get("title")
                if not title:
                    continue
                source = entry.get("source")
                articles.append({
                    "title": title,
                    "link": entry.get("link"),
                    "published": entry.get("published"),
                    "_published_parsed": entry.get("published_parsed"),
                    "source": source.get("title") if source else None,
                    "sentiment_compound": score_text(title),
                })

            articles.sort(key=lambda a: a["_published_parsed"] or time.gmtime(0), reverse=True)
            for a in articles:
                del a["_published_parsed"]
            return articles
        except Exception:
            return []

    def _is_duplicate_title(self, title: str, seen_titles: List[str], threshold: float = DUPLICATE_TITLE_THRESHOLD) -> bool:
        """Fuzzy-match `title` against `seen_titles` (sequence-similarity ratio above `threshold`)."""
        normalized = title.lower().strip()
        return any(
            SequenceMatcher(None, normalized, seen.lower().strip()).ratio() > threshold
            for seen in seen_titles
        )

    def get_ticker_news(self) -> Dict:
        """Google News coverage across 4 ticker-specific queries, deduped and topic-classified. Cached after the first call."""
        if self._ticker_news_cache is not None:
            return self._ticker_news_cache

        queries = [
            f"{self.company_name} news",
            f"{self.ticker} stock",
            f"{self.ticker} geopolitical",
            f"{self.ticker} tariff OR sanction OR war OR supply chain",
        ]

        all_articles = []
        seen_titles = []
        for i, query in enumerate(queries):
            for article in self.get_google_news(query, max_results=GOOGLE_NEWS_DEFAULT_MAX_RESULTS):
                if self._is_duplicate_title(article["title"], seen_titles):
                    continue
                seen_titles.append(article["title"])
                article["topic"] = _classify_topic(article["title"])
                all_articles.append(article)
            if i < len(queries) - 1:
                time.sleep(GOOGLE_NEWS_QUERY_DELAY_SECONDS)

        topic_breakdown = dict(Counter(a["topic"] for a in all_articles if a["topic"]))
        dominant_topic = max(topic_breakdown, key=topic_breakdown.get) if topic_breakdown else None

        compounds = [a["sentiment_compound"] for a in all_articles if a["sentiment_compound"] is not None]
        overall_sentiment = _clean(sum(compounds) / len(compounds)) if compounds else None

        result = {
            "articles": all_articles,
            "topic_breakdown": topic_breakdown,
            "dominant_topic": dominant_topic,
            "overall_news_sentiment": overall_sentiment,
        }
        self._ticker_news_cache = result
        return result

    def get_sector_news(self) -> Dict:
        """Google News coverage for this ticker's sector, using a curated search query per sector."""
        sector = self.info.get("sector")
        query = SECTOR_NEWS_TERMS.get(sector, f"{sector} sector news geopolitical" if sector else "market sector news")

        try:
            headlines = self.get_google_news(query, max_results=SECTOR_NEWS_MAX_RESULTS)
        except Exception:
            headlines = []

        compounds = [a["sentiment_compound"] for a in headlines if a["sentiment_compound"] is not None]
        sentiment = _clean(sum(compounds) / len(compounds)) if compounds else None

        return {
            "sector": sector,
            "sector_headlines": headlines,
            "sector_sentiment": sentiment,
        }

    def get_gdelt_events(self) -> Dict:
        """Recent global events mentioning this ticker/company, via GDELT's doc/doc API.

        Tone is approximated via VADER on each headline since GDELT's "artlist" mode has no per-article tone score.
        """
        empty = {"events": [], "avg_tone": None, "event_count": 0}
        try:
            params = {
                "query": f'{self.ticker} OR "{self.company_name}"',
                "mode": "artlist",
                "maxrecords": GDELT_MAX_RECORDS,
                "timespan": GDELT_TIMESPAN,
                "format": "json",
                "sourcelang": "english",
            }
            response = requests.get(
                GDELT_URL, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
            data = response.json()
            raw_articles = data.get("articles", [])[:GDELT_MAX_RECORDS]

            events = []
            titles = []
            for a in raw_articles:
                title = a.get("title")
                events.append({
                    "title": title,
                    "url": a.get("url"),
                    "domain": a.get("domain"),
                    "date": a.get("seendate"),
                    "tone": score_text(title) if title else None,
                })
                if title:
                    titles.append(title)

            avg_tone = None
            if titles:
                compounds = [score_text(t) for t in titles]
                avg_tone = _clean(sum(compounds) / len(compounds))

            return {"events": events, "avg_tone": avg_tone, "event_count": len(events)}
        except Exception:
            return empty

    def _fetch_rss_source(self, url: str, source_name: str, source_category: str) -> Tuple[List[dict], bool]:
        """Fetch + parse one RSS feed, tagged with its source/category.

        `succeeded` means the request completed, even if the feed came back empty.
        """
        feed = fetch_feed(url, timeout=RSS_FEED_TIMEOUT_SECONDS)
        if feed is None:
            return [], False

        try:
            articles = []
            for entry in feed.entries:
                title = entry.get("title")
                if not title:
                    continue
                articles.append({
                    "title": title,
                    "link": entry.get("link"),
                    "published": entry.get("published"),
                    "_published_parsed": entry.get("published_parsed"),
                    "source_name": source_name,
                    "source_category": source_category,
                })
            return articles, True
        except Exception:
            return [], False

    def _is_ticker_relevant(self, title: str) -> bool:
        """Whether `title` mentions the ticker, company name, or sector."""
        title_lower = title.lower()
        if self.ticker.lower() in title_lower:
            return True
        company_key = self.company_name.split()[0].lower()
        if company_key and company_key in title_lower:
            return True
        sector = self.info.get("sector")
        if sector:
            sector_key = sector.split()[0].lower()
            if sector_key in title_lower:
                return True
        return False

    def _fetch_all_wire_source_articles(self) -> Tuple[Dict[str, List[dict]], Dict[str, str]]:
        """Fetch every feed in `NEWS_SOURCES`; a source is "ok" if at least one of its feeds was reachable."""
        by_source_articles = {name: [] for name in NEWS_SOURCES}
        sources_status = {}

        source_order = list(NEWS_SOURCES.items())
        for source_idx, (source_name, feeds) in enumerate(source_order):
            source_succeeded_once = False
            feed_items = list(feeds.items())

            for feed_idx, (category, url) in enumerate(feed_items):
                resolved_url = url.replace("{ticker}", self.ticker) if source_name == "seeking_alpha" else url
                articles, ok = self._fetch_rss_source(resolved_url, source_name, category)
                if ok:
                    source_succeeded_once = True
                by_source_articles[source_name].extend(articles)

                is_last_feed_overall = (
                    source_idx == len(source_order) - 1 and feed_idx == len(feed_items) - 1
                )
                if not is_last_feed_overall:
                    time.sleep(RSS_FEED_REQUEST_DELAY_SECONDS)

            sources_status[source_name] = "ok" if source_succeeded_once else "failed"

        return by_source_articles, sources_status

    def _fold_in_google_news(self, by_source_articles: Dict[str, List[dict]], sources_status: Dict[str, str]) -> None:
        """Add the already-cached Google News ticker coverage as its own "source" (mutates both args in place).

        Reuses the `get_ticker_news()` cache instead of re-fetching.
        """
        try:
            google_articles = [
                {
                    "title": a["title"], "link": a.get("link"), "published": a.get("published"),
                    "_published_parsed": None, "source_name": "google_news", "source_category": None,
                    "sentiment_compound": a.get("sentiment_compound"),
                }
                for a in self.get_ticker_news().get("articles", [])
            ]
            by_source_articles["google_news"] = google_articles
            sources_status["google_news"] = "ok" if google_articles else "failed"
        except Exception:
            sources_status["google_news"] = "failed"

    def _merge_and_score_articles(self, by_source_articles: Dict[str, List[dict]]) -> List[dict]:
        """Merge all sources, dedupe by title similarity, score, classify, and sort newest-first.

        Wire sources are processed before google_news so a story picked up by both keeps its original source.
        """
        seen_titles = []
        merged = []
        for source_name in list(NEWS_SOURCES.keys()) + ["google_news"]:
            for article in by_source_articles[source_name]:
                if self._is_duplicate_title(article["title"], seen_titles, threshold=MULTI_SOURCE_DEDUP_THRESHOLD):
                    continue
                seen_titles.append(article["title"])

                if "sentiment_compound" not in article:
                    article["sentiment_compound"] = score_text(article["title"])
                article["topic"] = _classify_topic(article["title"])
                article["is_ticker_specific"] = self._is_ticker_relevant(article["title"])
                merged.append(article)

        merged.sort(key=lambda a: a.get("_published_parsed") or time.gmtime(0), reverse=True)
        for a in merged:
            a.pop("_published_parsed", None)
        return merged

    def _summarize_by_source(self, merged: List[dict]) -> Dict[str, dict]:
        """Per-source article count and average sentiment, from an already-merged article list."""
        by_source = {}
        for source_name in list(NEWS_SOURCES.keys()) + ["google_news"]:
            source_articles = [a for a in merged if a["source_name"] == source_name]
            compounds = [a["sentiment_compound"] for a in source_articles if a["sentiment_compound"] is not None]
            by_source[source_name] = {
                "count": len(source_articles),
                "avg_sentiment": _clean(sum(compounds) / len(compounds)) if compounds else None,
                "articles": source_articles,
            }
        return by_source

    def _sentiment_consensus_label(self, combined_sentiment: Optional[float]) -> Optional[str]:
        """Classify a combined multi-source sentiment score into a 5-tier consensus label."""
        if combined_sentiment is None:
            return None
        if combined_sentiment > CONSENSUS_STRONGLY_POSITIVE_THRESHOLD:
            return "Strongly Positive"
        if combined_sentiment > CONSENSUS_POSITIVE_THRESHOLD:
            return "Positive"
        if combined_sentiment >= CONSENSUS_NEGATIVE_THRESHOLD:
            return "Neutral"
        if combined_sentiment >= CONSENSUS_STRONGLY_NEGATIVE_THRESHOLD:
            return "Negative"
        return "Strongly Negative"

    def get_multi_source_news(self) -> Dict:
        """Merge Google News with 5 wire-service RSS feeds into one deduped, scored feed."""
        by_source_articles, sources_status = self._fetch_all_wire_source_articles()
        self._fold_in_google_news(by_source_articles, sources_status)

        merged = self._merge_and_score_articles(by_source_articles)
        by_source = self._summarize_by_source(merged)

        all_compounds = [a["sentiment_compound"] for a in merged if a["sentiment_compound"] is not None]
        combined_sentiment = _clean(sum(all_compounds) / len(all_compounds)) if all_compounds else None

        topic_counts = Counter(a["topic"] for a in merged if a["topic"])
        most_covered_topic = max(topic_counts, key=topic_counts.get) if topic_counts else None

        return {
            "all_articles": merged[:MAX_MERGED_ARTICLES],
            "ticker_specific": [a for a in merged if a["is_ticker_specific"]],
            "by_source": by_source,
            "combined_sentiment": combined_sentiment,
            "most_covered_topic": most_covered_topic,
            "sentiment_consensus": self._sentiment_consensus_label(combined_sentiment),
            "sources_status": sources_status,
        }

    def _china_risk_score(self, sector: Optional[str]) -> int:
        """China tariff/export-control exposure score by sector."""
        if sector == "Technology":
            return CHINA_RISK_TECH
        if sector == "Consumer Cyclical":
            return CHINA_RISK_CONSUMER_CYCLICAL
        return CHINA_RISK_DEFAULT

    def _russia_risk_score(self, sector: Optional[str]) -> int:
        """Russia sanctions/energy-market disruption exposure score by sector."""
        return RUSSIA_RISK_ENERGY if sector == "Energy" else RUSSIA_RISK_DEFAULT

    def _supply_chain_risk_score(self, sector: Optional[str]) -> int:
        """Global supply-chain disruption exposure score by sector."""
        if sector in SUPPLY_CHAIN_HIGH:
            return SUPPLY_CHAIN_RISK_HIGH
        if sector in SUPPLY_CHAIN_MEDIUM:
            return SUPPLY_CHAIN_RISK_MEDIUM
        if sector in SUPPLY_CHAIN_LOW:
            return SUPPLY_CHAIN_RISK_LOW
        return SUPPLY_CHAIN_RISK_DEFAULT

    def _regulatory_risk_score(self, regulatory_count: int) -> int:
        """Regulatory scrutiny score from the count of regulatory-themed articles."""
        if regulatory_count > REGULATORY_COUNT_HIGH_THRESHOLD:
            return REGULATORY_RISK_HIGH
        if regulatory_count >= REGULATORY_COUNT_MODERATE_THRESHOLD:
            return REGULATORY_RISK_MODERATE
        return REGULATORY_RISK_LOW

    def _news_sentiment_risk_score(self, sentiment: Optional[float]) -> int:
        """Risk score from overall news sentiment (more negative = higher risk)."""
        if sentiment is None:
            return NEWS_SENTIMENT_RISK_UNKNOWN
        if sentiment < NEWS_SENTIMENT_VERY_NEGATIVE_THRESHOLD:
            return NEWS_SENTIMENT_RISK_HIGH
        if sentiment < NEWS_SENTIMENT_NEGATIVE_THRESHOLD:
            return NEWS_SENTIMENT_RISK_MODERATE
        return NEWS_SENTIMENT_RISK_LOW

    def _geopolitical_risk_factors(
        self, sector: Optional[str], china_risk: int, russia_risk: int, supply_chain_risk: int,
        regulatory_risk: int, regulatory_count: int, news_sentiment_risk: int,
    ) -> List[str]:
        """Human-readable risk factor sentences for whichever components scored high."""
        risk_factors = []
        if china_risk >= CHINA_RISK_CONSUMER_CYCLICAL:
            if china_risk >= CHINA_RISK_TECH:
                risk_factors.append(f"{sector} sector faces significant China tariff and export control exposure")
            else:
                risk_factors.append(f"{sector} sector has moderate China trade/demand exposure")
        if russia_risk >= RUSSIA_RISK_ENERGY:
            risk_factors.append(f"{sector} sector is exposed to Russia-linked sanctions and energy market disruption")
        if supply_chain_risk >= SUPPLY_CHAIN_RISK_HIGH:
            risk_factors.append(f"{sector} sector carries high global supply chain disruption risk")
        if regulatory_risk >= REGULATORY_RISK_HIGH:
            risk_factors.append(f"Elevated regulatory scrutiny — {regulatory_count} regulatory-themed articles in recent coverage")
        if news_sentiment_risk >= NEWS_SENTIMENT_RISK_HIGH:
            risk_factors.append("Recent news sentiment around the company is notably negative")
        if not risk_factors:
            risk_factors.append(f"{sector or 'This company'} shows no significantly elevated geopolitical risk factors at this time")
        return risk_factors

    def get_geopolitical_risk_score(self) -> Dict:
        """Weighted 0-100 geopolitical risk score across China/Russia/supply-chain/regulatory/news exposure."""
        sector = self.info.get("sector")
        country = self.info.get("country")

        china_risk = self._china_risk_score(sector)
        russia_risk = self._russia_risk_score(sector)
        supply_chain_risk = self._supply_chain_risk_score(sector)

        try:
            ticker_news = self.get_ticker_news()
        except Exception:
            ticker_news = None

        regulatory_count = ticker_news["topic_breakdown"].get("regulatory", 0) if ticker_news else 0
        regulatory_risk = self._regulatory_risk_score(regulatory_count)

        sentiment = ticker_news.get("overall_news_sentiment") if ticker_news else None
        news_sentiment_risk = self._news_sentiment_risk_score(sentiment)

        overall = (
            china_risk * GEO_RISK_WEIGHT_CHINA + russia_risk * GEO_RISK_WEIGHT_RUSSIA
            + supply_chain_risk * GEO_RISK_WEIGHT_SUPPLY_CHAIN + regulatory_risk * GEO_RISK_WEIGHT_REGULATORY
            + news_sentiment_risk * GEO_RISK_WEIGHT_NEWS_SENTIMENT
        )

        if overall > GEO_RISK_LABEL_HIGH_THRESHOLD:
            risk_label = "High Geopolitical Risk"
        elif overall >= GEO_RISK_LABEL_MODERATE_THRESHOLD:
            risk_label = "Moderate Geopolitical Risk"
        else:
            risk_label = "Low Geopolitical Risk"

        risk_factors = self._geopolitical_risk_factors(
            sector, china_risk, russia_risk, supply_chain_risk, regulatory_risk, regulatory_count, news_sentiment_risk
        )

        return {
            "sector": sector,
            "country": country,
            "china_risk": china_risk,
            "russia_risk": russia_risk,
            "supply_chain_risk": supply_chain_risk,
            "regulatory_risk": regulatory_risk,
            "news_sentiment_risk": news_sentiment_risk,
            "overall_geopolitical_risk": _clean(overall),
            "risk_label": risk_label,
            "risk_factors": risk_factors,
        }

    def get_global_market_context(self) -> Dict:
        """5-day change for gold/oil/dollar/VIX/yields/major indices, plus a risk-on/risk-off vote."""
        markets = {}
        for symbol, name in GLOBAL_MARKETS.items():
            try:
                hist = yf.Ticker(symbol).history(period="5d")["Close"].dropna()
                if len(hist) >= 2:
                    current_price = _clean(hist.iloc[-1])
                    change_5d_pct = _clean((hist.iloc[-1] / hist.iloc[0] - 1) * 100)
                else:
                    current_price, change_5d_pct = None, None
            except Exception:
                current_price, change_5d_pct = None, None

            markets[symbol] = {"name": name, "current_price": current_price, "change_5d_pct": change_5d_pct}

        gold_change = markets["GC=F"]["change_5d_pct"]
        oil_change = markets["CL=F"]["change_5d_pct"]
        dollar_change = markets["DX-Y.NYB"]["change_5d_pct"]
        vix_change = markets["^VIX"]["change_5d_pct"]
        yield_change = markets["^TNX"]["change_5d_pct"]

        signals = {
            "gold_signal": "risk_off" if gold_change is not None and gold_change > GOLD_RISK_OFF_THRESHOLD else "neutral",
            "oil_signal": "geopolitical_tension" if oil_change is not None and oil_change > OIL_TENSION_THRESHOLD else "neutral",
            "dollar_signal": "risk_off" if dollar_change is not None and dollar_change > DOLLAR_RISK_OFF_THRESHOLD else "neutral",
            "vix_signal": "fear_increasing" if vix_change is not None and vix_change > VIX_FEAR_INCREASING_THRESHOLD else "neutral",
        }

        risk_off_votes = sum([
            gold_change is not None and gold_change > 0,
            dollar_change is not None and dollar_change > 0,
            vix_change is not None and vix_change > 0,
            yield_change is not None and yield_change < 0,
        ])
        risk_on_votes = sum([
            gold_change is not None and gold_change <= 0,
            dollar_change is not None and dollar_change <= 0,
            vix_change is not None and vix_change <= 0,
            yield_change is not None and yield_change > 0,
        ])

        if risk_off_votes >= GLOBAL_RISK_MODE_VOTE_THRESHOLD:
            global_risk_mode = "risk_off"
        elif risk_on_votes >= GLOBAL_RISK_MODE_VOTE_THRESHOLD:
            global_risk_mode = "risk_on"
        else:
            global_risk_mode = "neutral"

        return {"markets": markets, "signals": signals, "global_risk_mode": global_risk_mode}

    def _geopolitical_signal(
        self, overall_risk: Optional[float], global_mode: Optional[str],
        dominant_topic: Optional[str], sentiment_consensus: Optional[str],
    ) -> str:
        """Combine the risk score, global market mode, dominant topic, and multi-source consensus."""
        high_risk = (
            (overall_risk is not None and overall_risk > HIGH_RISK_OVERALL_THRESHOLD)
            or global_mode == "risk_off"
            or dominant_topic in ("geopolitical", "trade")
            or sentiment_consensus == "Strongly Negative"
        )
        # strongly positive consensus can pull a borderline case down to Low Risk, but never beats a high score
        low_risk = (not high_risk) and (
            (overall_risk is not None and overall_risk < LOW_RISK_OVERALL_THRESHOLD and global_mode != "risk_off")
            or (
                sentiment_consensus == "Strongly Positive"
                and overall_risk is not None and overall_risk < LOW_RISK_STRONGLY_POSITIVE_OVERALL_MAX
                and global_mode != "risk_off"
            )
        )

        if high_risk:
            return "High Risk"
        if low_risk:
            return "Low Risk"
        return "Moderate Risk"

    def get_full_geopolitical_analysis(self) -> Dict:
        """Aggregate ticker/sector news, GDELT events, risk score, market context, and a signal.

        Each sub-call is wrapped in its own try/except so one failing data source doesn't break the rest.
        """
        try:
            ticker_news = self.get_ticker_news()
        except Exception:
            ticker_news = None

        try:
            time.sleep(SECTOR_NEWS_DELAY_SECONDS)
            sector_news = self.get_sector_news()
        except Exception:
            sector_news = None

        try:
            gdelt_events = self.get_gdelt_events()
        except Exception:
            gdelt_events = {"events": [], "avg_tone": None, "event_count": 0}

        try:
            geopolitical_risk = self.get_geopolitical_risk_score()
        except Exception:
            geopolitical_risk = None

        try:
            global_market_context = self.get_global_market_context()
        except Exception:
            global_market_context = None

        try:
            time.sleep(MULTI_SOURCE_NEWS_DELAY_SECONDS)
            multi_source_news = self.get_multi_source_news()
        except Exception:
            multi_source_news = None

        overall_risk = geopolitical_risk.get("overall_geopolitical_risk") if geopolitical_risk else None
        global_mode = global_market_context.get("global_risk_mode") if global_market_context else None
        dominant_topic = ticker_news.get("dominant_topic") if ticker_news else None
        sentiment_consensus = multi_source_news.get("sentiment_consensus") if multi_source_news else None

        # prefer the richer multi-source sentiment here, without mutating the cached ticker_news dict
        ticker_news_out = dict(ticker_news) if ticker_news else None
        if ticker_news_out is not None and multi_source_news and multi_source_news.get("combined_sentiment") is not None:
            ticker_news_out["overall_news_sentiment"] = multi_source_news["combined_sentiment"]

        return {
            "ticker": self.ticker,
            "ticker_news": ticker_news_out,
            "sector_news": sector_news,
            "gdelt_events": gdelt_events,
            "geopolitical_risk": geopolitical_risk,
            "global_market_context": global_market_context,
            "multi_source_news": multi_source_news,
            "geopolitical_signal": self._geopolitical_signal(overall_risk, global_mode, dominant_topic, sentiment_consensus),
        }
