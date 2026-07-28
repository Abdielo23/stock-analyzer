"""Supply-chain/geographic risk mined from each company's SEC 10-K "Item 1A. Risk Factors" section.

The real risk-factors header has to be picked out from duplicate cross-reference and table-of-contents hits of the same phrase.
"""

import json
import re
import time
import warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# 10-K docs open with an XML declaration but the body is HTML, which just triggers a harmless bs4 warning.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_HEADERS = {"User-Agent": "stockanalyzer/1.0 contact@example.com"}
FILING_SEARCH_LOOKBACK_DAYS = 400
EDGAR_REQUEST_DELAY_SECONDS = 0.5
RISK_SECTION_CHAR_LIMIT = 50_000
CROSS_REFERENCE_LOOKBEHIND_CHARS = 50
TOC_LOOKAHEAD_CHARS = 80

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

GEOGRAPHIC_KEYWORDS = {
    "china": ["china", "chinese", "prc", "people's republic"],
    "taiwan": ["taiwan", "tsmc", "taiwanese"],
    "russia": ["russia", "russian", "moscow"],
    "middle_east": ["middle east", "saudi", "opec", "iran", "israel"],
    "india": ["india", "indian", "bangalore", "mumbai"],
    "vietnam": ["vietnam", "vietnamese"],
    "mexico": ["mexico", "mexican", "tijuana", "monterrey"],
    "europe": ["europe", "european", "germany", "france", "uk"],
}

SUPPLY_CHAIN_KEYWORDS = [
    "supplier", "supply chain", "manufacturer", "manufacturing",
    "sourced from", "produced in", "assembled in", "component",
    "raw material", "single source", "sole supplier",
    "concentration risk", "geographic concentration",
]

RISK_KEYWORDS = [
    "tariff", "trade restriction", "export control", "sanction",
    "disruption", "shortage", "dependency", "reliance",
    "risk factor", "material adverse",
]

# Exposure-level bands, in mentions per 1000 words of the risk section.
EXPOSURE_HIGH_THRESHOLD = 5
EXPOSURE_MEDIUM_THRESHOLD = 2

# Overall supply-chain-risk classification thresholds.
CRITICAL_RISK_MENTIONS_THRESHOLD = 20
HIGH_RISK_MENTIONS_THRESHOLD = 15
MODERATE_RISK_MENTIONS_THRESHOLD = 8

RISK_SENTENCES_PER_REGION = 3
TOP_KEY_RISK_STATEMENTS = 5


class SupplyChainAnalyzer:
    """Mines a ticker's latest 10-K risk factors for real geographic/supply-chain exposure."""

    def __init__(self):
        self._last_filing_date: Optional[str] = None

    def get_latest_10k_url(self, ticker: str) -> Optional[str]:
        """Find and build the direct document URL for a ticker's most recent 10-K."""
        try:
            end = date.today()
            start = end - timedelta(days=FILING_SEARCH_LOOKBACK_DAYS)
            response = requests.get(
                SEC_SEARCH_URL,
                params={
                    "q": f'"{ticker.upper()}"',
                    "forms": "10-K",
                    "dateRange": "custom",
                    "startdt": start.isoformat(),
                    "enddt": end.isoformat(),
                },
                headers=SEC_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            hits = response.json().get("hits", {}).get("hits", [])

            # One accession number covers several files (10-K plus exhibits) — only file_type "10-K" is the real one.
            candidates = [h for h in hits if h.get("_source", {}).get("file_type") == "10-K"]
            if not candidates:
                return None
            candidates.sort(key=lambda h: h["_source"].get("file_date", ""), reverse=True)
            best = candidates[0]

            source = best["_source"]
            cik = str(source["ciks"][0]).lstrip("0")
            accession = source["adsh"].replace("-", "")
            filename = best["_id"].split(":")[-1]
            self._last_filing_date = source.get("file_date")

            return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"
        except Exception:
            return None

    def _find_risk_section_bounds(self, text: str) -> Optional[tuple]:
        """Locate the true "Item 1A. Risk Factors" section's (start, end) offsets, skipping cross-references and TOC lines."""
        start_candidates = list(re.finditer(r"Item\s+1A\.?\s+Risk Factors", text, re.IGNORECASE))
        real_start = None
        for m in start_candidates:
            preceding = text[max(0, m.start() - CROSS_REFERENCE_LOOKBEHIND_CHARS):m.start()].lower()
            if "refer to" in preceding or preceding.rstrip().endswith(('"', "“")):
                continue
            following = text[m.start():m.start() + TOC_LOOKAHEAD_CHARS]
            if re.search(r"Item\s+1B", following, re.IGNORECASE):
                continue
            real_start = m.start()
            break

        if real_start is None:
            return None

        end_candidates = []
        for pattern in (r"Item\s+1B\.?\s+Unresolved", r"Item\s+2\.?\s+Properties"):
            for m in re.finditer(pattern, text, re.IGNORECASE):
                if m.start() > real_start:
                    end_candidates.append(m.start())
        end = min(end_candidates) if end_candidates else real_start + RISK_SECTION_CHAR_LIMIT

        return real_start, end

    def get_10k_risk_section(self, filing_url: str) -> Optional[str]:
        """Fetch a 10-K document and extract its "Item 1A. Risk Factors" text, capped at `RISK_SECTION_CHAR_LIMIT` chars."""
        try:
            time.sleep(EDGAR_REQUEST_DELAY_SECONDS)
            response = requests.get(filing_url, headers=SEC_HEADERS, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            text = soup.get_text(" ", strip=True)

            bounds = self._find_risk_section_bounds(text)
            if bounds is None:
                return None
            start, end = bounds
            return text[start:end][:RISK_SECTION_CHAR_LIMIT]
        except Exception:
            return None

    def _region_mention_count(self, text_lower: str, region: str) -> int:
        """Total mentions of any of a region's keyword variants."""
        return sum(text_lower.count(variant) for variant in GEOGRAPHIC_KEYWORDS[region])

    def _exposure_level(self, mentions_per_1000_words: float) -> str:
        """Classify a region's mention density into High/Medium/Low/None."""
        if mentions_per_1000_words == 0:
            return "None"
        if mentions_per_1000_words > EXPOSURE_HIGH_THRESHOLD:
            return "High"
        if mentions_per_1000_words >= EXPOSURE_MEDIUM_THRESHOLD:
            return "Medium"
        return "Low"

    def _split_sentences(self, text: str) -> List[str]:
        """Simple sentence splitter (splits on ./!/? followed by whitespace)."""
        return re.split(r"(?<=[.!?])\s+", text)

    def _region_risk_sentences(self, sentences: List[str], region: str) -> List[str]:
        """Up to `RISK_SENTENCES_PER_REGION` sentences mentioning both this region and a risk keyword."""
        variants = GEOGRAPHIC_KEYWORDS[region]
        matches = []
        for sentence in sentences:
            s_lower = sentence.lower()
            if any(v in s_lower for v in variants) and any(rk in s_lower for rk in RISK_KEYWORDS):
                matches.append(sentence.strip())
                if len(matches) >= RISK_SENTENCES_PER_REGION:
                    break
        return matches

    def _overall_risk_label(self, geographic_exposure: Dict[str, dict], risk_mentions: int) -> str:
        """Classify overall supply-chain risk from region exposure levels and risk-keyword density."""
        china_or_taiwan_high = (
            geographic_exposure["china"]["exposure_level"] == "High"
            or geographic_exposure["taiwan"]["exposure_level"] == "High"
        )
        any_high = any(r["exposure_level"] == "High" for r in geographic_exposure.values())
        any_medium = any(r["exposure_level"] == "Medium" for r in geographic_exposure.values())
        all_low_or_none = all(r["exposure_level"] in ("Low", "None") for r in geographic_exposure.values())

        if china_or_taiwan_high and risk_mentions > CRITICAL_RISK_MENTIONS_THRESHOLD:
            return "Critical"
        if any_high or risk_mentions > HIGH_RISK_MENTIONS_THRESHOLD:
            return "High"
        if any_medium or risk_mentions > MODERATE_RISK_MENTIONS_THRESHOLD:
            return "Moderate"
        if all_low_or_none and risk_mentions < MODERATE_RISK_MENTIONS_THRESHOLD:
            return "Low"
        return "Moderate"

    def analyze_supply_chain_text(self, text: str, ticker: str) -> Dict:
        """Analyze a 10-K risk factors section for geographic exposure and supply-chain risk."""
        text_lower = text.lower()
        word_count = max(len(text.split()), 1)
        sentences = self._split_sentences(text)

        geographic_exposure = {}
        for region in GEOGRAPHIC_KEYWORDS:
            mention_count = self._region_mention_count(text_lower, region)
            per_1000_words = mention_count / word_count * 1000
            geographic_exposure[region] = {
                "mention_count": mention_count,
                "exposure_level": self._exposure_level(per_1000_words),
                "risk_sentences": self._region_risk_sentences(sentences, region),
            }

        supply_chain_mentions = sum(text_lower.count(kw) for kw in SUPPLY_CHAIN_KEYWORDS)
        risk_mentions = sum(text_lower.count(kw) for kw in RISK_KEYWORDS)

        key_risk_statements = []
        for sentence in sentences:
            s_lower = sentence.lower()
            if any(rk in s_lower for rk in RISK_KEYWORDS):
                key_risk_statements.append(sentence.strip())
                if len(key_risk_statements) >= TOP_KEY_RISK_STATEMENTS:
                    break

        return {
            "geographic_exposure": geographic_exposure,
            "supply_chain_mentions": supply_chain_mentions,
            "risk_mentions": risk_mentions,
            "overall_supply_chain_risk": self._overall_risk_label(geographic_exposure, risk_mentions),
            "key_risk_statements": key_risk_statements,
            "data_source": "SEC 10-K filing",
            "filing_date": self._last_filing_date,
        }

    def _cache_path(self, ticker: str) -> Path:
        return CACHE_DIR / f"{ticker.upper()}_10k.json"

    def _read_cache(self, ticker: str) -> Optional[Dict]:
        path = self._cache_path(ticker)
        try:
            if not path.exists():
                return None
            if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
                return None
            return json.loads(path.read_text())
        except Exception:
            return None

    def _write_cache(self, ticker: str, result: Dict) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cache_path(ticker).write_text(json.dumps(result))
        except Exception:
            pass

    def get_supply_chain_analysis(self, ticker: str) -> Dict:
        """Full pipeline: find the 10-K, extract risk factors, analyze, and cache for 7 days."""
        cached = self._read_cache(ticker)
        if cached is not None:
            return cached

        try:
            filing_url = self.get_latest_10k_url(ticker)
            if filing_url is None:
                result = {"error": "10-K analysis unavailable", "source": "SEC EDGAR"}
            else:
                risk_text = self.get_10k_risk_section(filing_url)
                if risk_text is None:
                    result = {"error": "10-K analysis unavailable", "source": "SEC EDGAR"}
                else:
                    result = self.analyze_supply_chain_text(risk_text, ticker)
        except Exception:
            result = {"error": "10-K analysis unavailable", "source": "SEC EDGAR"}

        self._write_cache(ticker, result)
        return result
