# Stock Analyzer 

> Professional-grade stock analysis tool combining fundamental analysis,
> technical indicators, quantitative models, and social sentiment —
> built for retail investors who want hedge-fund-level insights.

## Features

### Implemented
- **Module 1** — Data Layer (yfinance + web scraping)
- **Module 2** — Fundamental Analysis (margins, ROE, ROIC, FCF, health score)
- **Module 3** — Valuation (DCF with WACC, relative multiples, Finviz scraping)
- **Module 4** — Technical Analysis (RSI, MACD, Ichimoku, ADX, Bollinger, VWAP)
- **Module 5** — Volume & Flow (OBV, Accumulation/Distribution, CMF, Volume Profile)
- **Module 6** — Risk Analysis (Sharpe, Sortino, VaR, CVaR, Max Drawdown, Monte Carlo)
- **Module 7** — Insider & Institutional (SEC EDGAR, 13F, Finviz ownership)
- **Module 8** — Sentiment & Macro (Fear & Greed, VIX, FRED macro data, analyst ratings)
- **Module 9** — Earnings Analysis (beat rates, EPS trends, earnings quality, guidance)
- **Module 10** — Quantitative (factor scores, Monte Carlo, backtesting, Hurst exponent)
- **Module 11** — Social Sentiment (Reddit/WSB mentions, VADER sentiment)
- **Module 12** — Global News & Geopolitical Risk (Google News, MarketWatch, CNBC, Seeking Alpha, Benzinga, GDELT)
- **Module 13** — Policy & Political Risk (Congress.gov, Fed speeches, Executive Orders, historical events)
- **Module 14** — Advanced Macro & Supply Chain (Yield curve, credit markets, commodities, supply chain, M2 liquidity)
- **Module 15** — Economic Calendar & Fed Events (FOMC dates, Powell speeches, economic releases, market holidays)
- **Module 16** — Investment Summary (Full statement, score breakdown, AI prompt for ChatGPT/Claude/Gemini)

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /stock/{ticker}/price | Historical OHLCV data |
| GET /stock/{ticker}/fundamentals | Key financial metrics |
| GET /stock/{ticker}/fundamental | Full fundamental analysis |
| GET /stock/{ticker}/valuation | DCF + relative valuation |
| GET /stock/{ticker}/technical | Technical indicators |
| GET /stock/{ticker}/volume | Volume & flow analysis |
| GET /stock/{ticker}/risk | Risk metrics & VaR |
| GET /stock/{ticker}/institutional | Insider & institutional data |
| GET /stock/{ticker}/sentiment | Macro & market sentiment |
| GET /stock/{ticker}/earnings | Earnings history & analysis |
| GET /stock/{ticker}/quantitative | Quant factors & backtesting |
| GET /stock/{ticker}/social | Reddit/WSB sentiment |
| GET /stock/{ticker}/geopolitical | Global news & geopolitical risk |
| GET /stock/{ticker}/political | Policy & political risk |
| GET /stock/{ticker}/macro | Macro environment & supply chain |
| GET /stock/{ticker}/calendar | Ticker-specific economic calendar |
| GET /stock/{ticker}/summary | Full AI investment summary |
| GET /calendar | General economic calendar |

## Quick Start

### Requirements
- Python 3.9+
- pip

### Installation
```bash
git clone https://github.com/YOUR_USERNAME/stock-analyzer.git
cd stock-analyzer/backend
pip install -r requirements.txt
```

### Configuration
```bash
cp .env.example .env
# Add your Reddit API credentials (free)
# Optional: Add YouTube API key (free tier)
```

### Run
```bash
uvicorn main:app --reload --port 8000
```

Open: http://localhost:8000/stock/AAPL/fundamental

## Frontend
React app on localhost:3000
- 16 pages with dark theme
- Interactive charts (recharts)
- AI Summary with copy-to-clipboard prompt
- Links to ChatGPT, Claude.ai, Gemini for AI analysis

## Data Sources
- **yfinance** — price history, financials, options
- **Finviz** — screener data, ownership, analyst ratings
- **StockAnalysis.com** — historical financials
- **SEC EDGAR** — insider trades, 13F filings (official)
- **FRED** — macroeconomic indicators
- **CNN** — Fear & Greed Index
- **Reddit API** — social sentiment (WSB, investing, stocks)

## License
MIT License — free to use, modify, and distribute.
See [LICENSE](LICENSE) for full details.

## Open Source
This project is fully open source.
Fork it, modify it, build on it — no restrictions.

## Disclaimer
This tool is for educational and research purposes only.
Nothing here constitutes financial advice.
