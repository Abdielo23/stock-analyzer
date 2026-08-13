"""Reddit/WallStreetBets sentiment: mention counts, VADER sentiment, WSB meme signals, and mention trend.

Data source: Reddit API via ``praw``. Falls back to a "credentials not
configured" shape until a user sets up ``backend/.env``.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import praw
from dotenv import load_dotenv

from utils.sentiment_utils import aggregate_sentiment, score_items

load_dotenv()

SUBREDDITS = ["wallstreetbets", "investing", "stocks", "SecurityAnalysis", "options"]
YOLO_KEYWORDS = ["YOLO", "CALLS", "PUTS", "TENDIES"]

DEFAULT_MENTION_SEARCH_LIMIT = 100
WSB_HOT_POST_LIMIT = 50
WSB_SEARCH_LIMIT = 50

# --- Mention trend ---
MENTION_TREND_DAYS = 7
TRENDING_MULTIPLIER = 2
TREND_WINDOW_DAYS = 3

# --- Combined social signal ---
SOCIAL_SIGNAL_BULLISH_MIN = 1
SOCIAL_SIGNAL_BEARISH_MAX = -1


class SocialSentimentAnalyzer:
    """Fetches and scores Reddit/WSB sentiment for one ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._reddit = None
        self._reddit_checked = False
        self._mentions_cache = None

    def setup_reddit(self) -> Optional["praw.Reddit"]:
        """Lazily-initialized, cached read-only Reddit client, or None if unconfigured."""
        if self._reddit_checked:
            return self._reddit
        self._reddit_checked = True

        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "StockAnalyzer/1.0")

        placeholder = (
            not client_id or not client_secret
            or client_id.startswith("your_") or client_secret.startswith("your_")
        )
        if placeholder:
            self._reddit = None
            return None

        try:
            reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
            reddit.read_only = True
            self._reddit = reddit
        except Exception:
            self._reddit = None

        return self._reddit

    def get_reddit_mentions(self, limit: int = DEFAULT_MENTION_SEARCH_LIMIT) -> Optional[Dict]:
        """Search all `SUBREDDITS` for `$TICKER`/`TICKER` mentions, deduped by post ID and cached."""
        if self._mentions_cache is not None:
            return self._mentions_cache

        reddit = self.setup_reddit()
        if reddit is None:
            return None

        posts = {}
        mentions_by_subreddit = {sub: 0 for sub in SUBREDDITS}
        queries = [f"${self.ticker}", self.ticker]

        try:
            for sub_name in SUBREDDITS:
                subreddit = reddit.subreddit(sub_name)
                for query in queries:
                    try:
                        for submission in subreddit.search(query, limit=limit, sort="new"):
                            if submission.id not in posts:
                                posts[submission.id] = {
                                    "id": submission.id,
                                    "title": submission.title,
                                    "score": submission.score,
                                    "num_comments": submission.num_comments,
                                    "created_utc": submission.created_utc,
                                    "url": submission.url,
                                    "subreddit": sub_name,
                                }
                                mentions_by_subreddit[sub_name] += 1
                    except Exception:
                        continue

            result = {
                "total_mentions": len(posts),
                "posts_found": list(posts.values()),
                "mentions_by_subreddit": mentions_by_subreddit,
            }
        except Exception:
            result = {"total_mentions": 0, "posts_found": [], "mentions_by_subreddit": mentions_by_subreddit}

        self._mentions_cache = result
        return result

    def get_reddit_sentiment(self) -> Optional[Dict]:
        """VADER sentiment across all mentioned posts' titles, or None if unavailable."""
        mentions = self.get_reddit_mentions()
        if mentions is None:
            return None

        try:
            scored_posts = score_items(mentions["posts_found"])
            aggregate = aggregate_sentiment(scored_posts)
            return {
                "avg_compound": aggregate["avg_compound"],
                "counts": aggregate["counts"],
                "overall_reddit_sentiment": aggregate["overall_sentiment"],
                "upvote_weighted_sentiment": aggregate["upvote_weighted_sentiment"],
                "posts": aggregate["posts"],
            }
        except Exception:
            return None

    def _wsb_signals(self, ticker_posts: List[dict]) -> Dict:
        """Rocket-emoji count, YOLO/loss-porn keyword mentions, and DD posts for a post list."""
        titles_upper = [p["title"].upper() for p in ticker_posts]
        rocket_count = sum(title.count("\U0001F680") for title in titles_upper)
        yolo_mentions = sum(1 for title in titles_upper if any(kw in title for kw in YOLO_KEYWORDS))
        loss_porn = sum(1 for title in titles_upper if "LOSS" in title or "RIP" in title)
        dd_posts = [
            p for p, title in zip(ticker_posts, titles_upper)
            if re.search(r"\bDD\b", title) or "DUE DILIGENCE" in title
        ]
        return {"rocket_count": rocket_count, "yolo_mentions": yolo_mentions, "loss_porn": loss_porn, "dd_posts": dd_posts}

    def get_wsb_analysis(self) -> Optional[Dict]:
        """WallStreetBets mentions, sentiment, and meme signals for this ticker.

        Combines current hot posts with a direct search, since a trending
        ticker might not match a literal title search or vice versa.
        """
        reddit = self.setup_reddit()
        if reddit is None:
            return None

        try:
            subreddit = reddit.subreddit("wallstreetbets")
            posts = {}

            try:
                for submission in subreddit.hot(limit=WSB_HOT_POST_LIMIT):
                    posts[submission.id] = {
                        "id": submission.id, "title": submission.title, "score": submission.score,
                        "num_comments": submission.num_comments, "created_utc": submission.created_utc,
                        "url": submission.url, "subreddit": "wallstreetbets",
                    }
            except Exception:
                pass

            try:
                for submission in subreddit.search(self.ticker, limit=WSB_SEARCH_LIMIT, sort="new"):
                    posts[submission.id] = {
                        "id": submission.id, "title": submission.title, "score": submission.score,
                        "num_comments": submission.num_comments, "created_utc": submission.created_utc,
                        "url": submission.url, "subreddit": "wallstreetbets",
                    }
            except Exception:
                pass

            ticker_upper = self.ticker.upper()
            ticker_posts = [
                p for p in posts.values()
                if ticker_upper in p["title"].upper() or f"${ticker_upper}" in p["title"].upper()
            ]

            wsb_signals = self._wsb_signals(ticker_posts)
            scored_posts = score_items(ticker_posts)
            aggregate = aggregate_sentiment(scored_posts)

            return {
                "wsb_mentions": len(ticker_posts),
                "wsb_sentiment": {
                    "avg_compound": aggregate["avg_compound"],
                    "counts": aggregate["counts"],
                    "overall_sentiment": aggregate["overall_sentiment"],
                },
                "wsb_signals": {
                    "rocket_count": wsb_signals["rocket_count"],
                    "yolo_mentions": wsb_signals["yolo_mentions"],
                    "loss_porn": wsb_signals["loss_porn"],
                },
                "dd_posts": wsb_signals["dd_posts"],
            }
        except Exception:
            return None

    def get_mention_trend(self) -> Optional[Dict]:
        """Daily mention counts over the last `MENTION_TREND_DAYS` days, plus a trend direction."""
        mentions = self.get_reddit_mentions()
        if mentions is None:
            return None

        try:
            now = datetime.now(timezone.utc)
            days = [(now - timedelta(days=i)).date() for i in range(MENTION_TREND_DAYS - 1, -1, -1)]
            daily_mentions = {str(d): 0 for d in days}

            for post in mentions["posts_found"]:
                post_date = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).date()
                key = str(post_date)
                if key in daily_mentions:
                    daily_mentions[key] += 1

            counts = list(daily_mentions.values())
            today_count = counts[-1]
            avg_count = sum(counts) / len(counts) if counts else 0
            is_trending = bool(avg_count and today_count > TRENDING_MULTIPLIER * avg_count)

            first_half_avg = sum(counts[:TREND_WINDOW_DAYS]) / TREND_WINDOW_DAYS
            second_half_avg = sum(counts[-TREND_WINDOW_DAYS:]) / TREND_WINDOW_DAYS
            if second_half_avg > first_half_avg:
                trend_direction = "increasing"
            elif second_half_avg < first_half_avg:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"

            return {
                "daily_mentions": daily_mentions,
                "is_trending": is_trending,
                "trend_direction": trend_direction,
            }
        except Exception:
            return None

    def get_future_features(self) -> Dict:
        """Static roadmap block describing planned X/Twitter and YouTube sentiment features."""
        ticker = self.ticker
        return {
            "twitter_x": {
                "status": "coming_soon",
                "description": "Real-time X/Twitter sentiment using cashtags ($TICKER)",
                "planned_features": [
                    "Live cashtag feed via X API v2",
                    "Sentiment analysis on tweets",
                    "Key financial accounts monitoring",
                    "Tweet volume trends",
                ],
                "links": {
                    "live_feed": f"https://x.com/search?q={ticker}&f=live",
                    "top_posts": f"https://x.com/search?q={ticker}+stock&f=top",
                    "cashtag": f"https://x.com/search?q=%24{ticker}&src=cashtag_click",
                },
                "api_docs": "https://developer.x.com/en/docs/x-api",
            },
            "youtube": {
                "status": "coming_soon",
                "description": "YouTube financial video analysis for the ticker",
                "planned_features": [
                    "Latest videos from top financial YouTubers",
                    "View count and engagement metrics",
                    "Title sentiment analysis via VADER",
                    "Filtered by trusted channels: Graham Stephan, Meet Kevin, ZipTrader, etc.",
                ],
                "api_docs": "https://developers.google.com/youtube/v3",
            },
        }

    def _social_signal(self, reddit_sentiment: Optional[Dict], mention_trend: Optional[Dict], wsb: Optional[Dict]) -> str:
        """Combine Reddit sentiment, a mention-trend spike, and WSB loss-porn/rocket balance."""
        score = 0
        overall_sentiment = reddit_sentiment.get("overall_reddit_sentiment") if reddit_sentiment else None
        if overall_sentiment in ("Bullish", "Very Bullish"):
            score += 1
        elif overall_sentiment in ("Bearish", "Very Bearish"):
            score -= 1

        if mention_trend and mention_trend.get("is_trending"):
            score += 1

        if wsb:
            signals = wsb.get("wsb_signals", {})
            if signals.get("loss_porn", 0) > signals.get("rocket_count", 0):
                score -= 1

        if score >= SOCIAL_SIGNAL_BULLISH_MIN:
            return "Bullish"
        if score <= SOCIAL_SIGNAL_BEARISH_MAX:
            return "Bearish"
        return "Neutral"

    def get_full_social_analysis(self) -> Dict:
        """Aggregate Reddit mentions/sentiment, WSB signals, mention trend, and an overall signal."""
        if self.setup_reddit() is None:
            return {
                "error": "Reddit credentials not configured",
                "instructions": {
                    "step1": "Go to reddit.com/prefs/apps",
                    "step2": "Click 'create app' at the bottom",
                    "step3": "Select type: script",
                    "step4": "Copy client_id (under app name) and client_secret",
                    "step5": "Add to backend/.env file",
                },
                "future_features": self.get_future_features(),
            }

        try:
            reddit_mentions = self.get_reddit_mentions()
        except Exception:
            reddit_mentions = None

        try:
            reddit_sentiment = self.get_reddit_sentiment()
        except Exception:
            reddit_sentiment = None

        try:
            wsb = self.get_wsb_analysis()
        except Exception:
            wsb = None

        try:
            mention_trend = self.get_mention_trend()
        except Exception:
            mention_trend = None

        return {
            "reddit": {
                "mentions": reddit_mentions,
                "sentiment": reddit_sentiment,
            },
            "wsb": wsb,
            "mention_trend": mention_trend,
            "future_features": self.get_future_features(),
            "social_signal": self._social_signal(reddit_sentiment, mention_trend, wsb),
        }
