"""Shared VADER sentiment-scoring helpers.

Note: ``analysis/sentiment.py`` uses a separate keyword-based approach, not VADER.
Runs locally via the ``vaderSentiment`` package — no network calls.
"""

from collections import Counter
from typing import Dict, List, Optional

import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_vader = SentimentIntensityAnalyzer()

# 5-tier thresholds for turning a raw compound score into a bullish/bearish label.
VERY_BULLISH_THRESHOLD = 0.5
BULLISH_THRESHOLD = 0.1
BEARISH_THRESHOLD = -0.1
VERY_BEARISH_THRESHOLD = -0.5


def _clean(value: object) -> Optional[float]:
    """Cast to float, collapsing NaN/Inf/None/unparseable values to None."""
    try:
        if value is None:
            return None
        value = float(value)
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    except (TypeError, ValueError):
        return None


def score_text(text: str) -> Optional[float]:
    """Return VADER's compound sentiment score (-1..1) for a piece of text.

    No empty-string guard on purpose — VADER scores "" as neutral (0.0), and some callers rely on that.
    """
    try:
        return _clean(_vader.polarity_scores(text)["compound"])
    except Exception:
        return None


def label_for_compound(compound: Optional[float]) -> Optional[str]:
    """Map a VADER compound score to a 5-tier bullish/bearish label."""
    if compound is None:
        return None
    if compound > VERY_BULLISH_THRESHOLD:
        return "Very Bullish"
    if compound > BULLISH_THRESHOLD:
        return "Bullish"
    if compound >= BEARISH_THRESHOLD:
        return "Neutral"
    if compound >= VERY_BEARISH_THRESHOLD:
        return "Bearish"
    return "Very Bearish"


def score_items(items: List[dict], text_key: str = "title") -> List[dict]:
    """Attach `sentiment_compound`/`sentiment_label` to each item's text field.

    Returns new dicts (does not mutate the input list) with both keys added.
    """
    scored = []
    for item in items:
        compound = score_text(item.get(text_key, ""))
        scored.append({**item, "sentiment_compound": compound, "sentiment_label": label_for_compound(compound)})
    return scored


def aggregate_sentiment(scored_items: List[dict], weight_key: str = "score") -> Dict:
    """Summarize a list of items already scored via `score_items`, or return an empty shell if the list is empty."""
    if not scored_items:
        return {
            "avg_compound": None, "counts": {}, "overall_sentiment": None,
            "upvote_weighted_sentiment": None, "posts": [],
        }

    compounds = [i["sentiment_compound"] for i in scored_items]
    avg_compound = sum(compounds) / len(compounds)
    counts = dict(Counter(i["sentiment_label"] for i in scored_items))

    weights = [max(i.get(weight_key, 0), 0) for i in scored_items]
    total_weight = sum(weights)
    upvote_weighted = (
        sum(c * w for c, w in zip(compounds, weights)) / total_weight
        if total_weight else avg_compound
    )

    return {
        "avg_compound": avg_compound,
        "counts": counts,
        "overall_sentiment": label_for_compound(avg_compound),
        "upvote_weighted_sentiment": upvote_weighted,
        "posts": scored_items,
    }
