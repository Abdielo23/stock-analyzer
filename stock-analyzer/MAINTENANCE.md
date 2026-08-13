# Maintenance Guide

This document explains what updates automatically, what needs
manual attention, and when.

---

## What Updates Automatically (no action needed)

Every time the app is used these pull live data:
- Stock prices, volume, daily changes
- RSI, MACD, all technical indicators
- Fear & Greed Index
- VIX and volatility data
- News (MarketWatch, CNBC, Seeking Alpha, Benzinga, Google News)
- Reddit mentions and sentiment
- FRED macro data (CPI, rates, GDP, M2, yield curve)
- Analyst ratings and price targets
- Institutional and insider data from SEC EDGAR
- Sector ETF performance and rotation
- Commodities (Gold, Oil, Copper, etc.)
- Sector benchmarks (PE, EV/EBITDA) — live from sector ETFs
- Supply chain risk — live from SEC 10-K filings (cached 7 days)
- Peer comparison — live from sector ETF holdings
- FOMC meeting dates — scraped from federalreserve.gov
- Fed speeches — scraped from federalreserve.gov RSS
- Economic release dates — calculated automatically by date math

---

## What Needs Manual Attention

### Every January

**1. NYSE Market Holidays**
File: `backend/analysis/calendar.py`
Function: `get_market_holidays()`

NYSE publishes next year's schedule every fall.
Source: https://www.nyse.com/markets/hours-calendars

Update the holiday dates list for the new year:
- New Year's Day
- MLK Day
- Presidents Day
- Good Friday (changes every year — use Easter algorithm)
- Memorial Day
- Juneteenth
- Independence Day
- Labor Day
- Thanksgiving
- Christmas

**2. Verify FOMC Scraper**
File: `backend/analysis/calendar.py`
Function: `get_fomc_dates()`

The scraper pulls dates automatically from:
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

Every January verify it picks up the new year correctly.
If it breaks (Fed changed their HTML):
- Open the URL in browser
- Inspect the table structure
- Update the BeautifulSoup parser accordingly

**3. Verify Economic Release Date Math**
File: `backend/analysis/calendar.py`
Function: `get_economic_releases()`

Uses date formulas (first Friday of month, etc.)
that work across years automatically.
Just verify in January the dates look correct.

---

### When Major Events Happen

**Add New Historical Policy Events**
File: `backend/analysis/political.py`
Function: `get_historical_policy_events()`

Historical events are intentionally static — they happened
and don't change. But add new ones when they occur.

When to add:
- Major legislation passes (like CHIPS Act, IRA)
- Major tariff announcement with clear market impact
- Fed policy regime change (like 2022 rate hike cycle)
- Major regulatory action affecting a whole sector

How to add — find the right sector list and append:
```python
{
  "event": "Event name and year",
  "impact": "Which direction and why",
  "market_move": "Approximate % move on affected stocks"
}
```

---

### Every 6 Months

**Update Python Dependencies**
```bash
cd backend
pip install -r requirements.txt --upgrade
pip freeze > requirements.txt
```

Test after upgrading:
```bash
uvicorn main:app --reload --port 8000
```
Then verify: http://localhost:8000/stock/AAPL/fundamental

---

## Annual Checklist (run every January)

- [ ] Update NYSE holidays in `calendar.py`
- [ ] Verify FOMC scraper picks up new year dates
- [ ] Verify economic release dates look correct
- [ ] Run `pip install -r requirements.txt --upgrade`
- [ ] Test all endpoints with AAPL — confirm HTTP 200
- [ ] Add any major policy events from past year to `political.py`
- [ ] Check Reddit API credentials still valid
- [ ] Check if any data sources changed their format

---

## If Something Breaks

| Source | Symptom | Fix |
|--------|---------|-----|
| yfinance | Most modules return null | `pip install yfinance --upgrade` |
| Finviz | Valuation/Institutional null | Finviz changed HTML — update BeautifulSoup parser |
| FRED | Macro data null | Verify series IDs at https://fred.stlouisfed.org |
| SEC EDGAR | Institutional/Supply chain null | Check User-Agent header still accepted |
| CNN Fear & Greed | Sentiment null | URL or headers changed — check network tab in browser |
| Reddit | Social module null | Check praw version: `pip install praw --upgrade` |
| Google News | Geopolitical news null | Google changed RSS — update feedparser logic |
| MarketWatch | News null | Check feed URL still active |
| CNBC | News null | Check feed URL still active |
| Seeking Alpha | News null | Check feed URL still active |

**General fix pattern for any broken scraper:**
1. Open the URL directly in browser — is the page still there?
2. Check if HTML structure changed (right click → Inspect)
3. Update the BeautifulSoup parser in the relevant file
4. Test with AAPL before restarting the full server

---

## License
MIT — free to use, modify, and distribute.
