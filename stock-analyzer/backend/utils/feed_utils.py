"""Shared RSS/Atom feed-fetching helper."""

from typing import Optional

import feedparser
import requests

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "Mozilla/5.0"


def fetch_feed(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional["feedparser.FeedParserDict"]:
    """Fetch an RSS/Atom feed and parse it, or None on any failure.

    Fetches via `requests` first (with a timeout) instead of handing the URL straight to
    feedparser, since feedparser's own fetch has no timeout and can hang forever.
    """
    try:
        response = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception:
        return None
