"""Shared Finviz scraping helpers.

Scrapes the quote.ashx page since Finviz has no official API.
"""

from typing import Optional

import requests
from bs4 import BeautifulSoup

FINVIZ_HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_number(text: Optional[str]) -> Optional[float]:
    """Parse a Finviz cell like "1.23B" or "(4.5%)" into a float, or None if it's a placeholder."""
    if text is None:
        return None
    text = text.strip()
    if text in ("", "-", "N/A"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    multiplier = 1
    suffix = text[-1:].upper()
    if suffix in ("K", "M", "B", "T"):
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
        text = text[:-1]
    text = text.replace("%", "").replace(",", "").strip()
    try:
        value = float(text) * multiplier
        return -value if negative else value
    except ValueError:
        return None


def fetch_finviz_raw(ticker: str) -> dict:
    """Scrape finviz.com/quote.ashx into a flat {label: raw_value_string} dict.

    Finviz splits data across several tables, so labels get merged together.
    Uses stripped_strings instead of get_text() to avoid nested % spans
    (e.g. 52W High/Low) getting concatenated into the value. Network/parse
    errors are left to bubble up to the caller.
    """
    url = f"https://finviz.com/quote.ashx?t={ticker.upper()}"
    response = requests.get(url, headers=FINVIZ_HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    raw = {}
    for table in soup.find_all("table", class_="snapshot-table2"):
        cells = table.find_all("td")
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].get_text(strip=True)
            values = list(cells[i + 1].stripped_strings)
            raw[label] = values[0] if values else None

    return raw
