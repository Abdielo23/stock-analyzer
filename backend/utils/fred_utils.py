"""Shared FRED (Federal Reserve Economic Data) series-fetching helper."""

from typing import Optional

import pandas as pd

FRED_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch_fred_series(series_id: str) -> Optional[pd.DataFrame]:
    """Fetch one FRED series as a DataFrame, or None on any failure.

    Uses pandas' read_csv instead of `requests`, since `requests` hangs against FRED
    (an Akamai TLS fingerprint mismatch) while pandas' fetcher doesn't.
    """
    try:
        return pd.read_csv(f"{FRED_BASE_URL}?id={series_id}").dropna()
    except Exception:
        return None
