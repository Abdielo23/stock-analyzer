"""Macro & supply-chain analysis: yield curve, credit markets, commodities,
supply-chain exposure, global liquidity, and sector rotation, rolled up
into one combined macro signal. Uses yfinance for price history and FRED
for series yfinance doesn't cover.
"""

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from utils.fred_utils import fetch_fred_series
from utils.supply_chain_edgar import SupplyChainAnalyzer

# Maps SupplyChainAnalyzer's risk label onto this module's label format.
EDGAR_RISK_LABEL_MAP = {
    "Critical": "Critical Supply Chain Risk",
    "High": "High Supply Chain Risk",
    "Moderate": "Moderate Supply Chain Risk",
    "Low": "Low Supply Chain Risk",
}

TREASURY_YF_TICKERS = {"3M": "^IRX", "5Y": "^FVX", "10Y": "^TNX", "30Y": "^TYX"}
# FRED covers maturities yfinance has no ticker for (1-month, 1-year, 2-year).
TREASURY_FRED_SERIES = {"1M": "DGS1MO", "1Y": "DGS1", "2Y": "DGS2"}
FRED_REQUEST_DELAY_SECONDS = 0.3
FULL_ANALYSIS_STEP_DELAY_SECONDS = 0.3

COMMODITY_TICKERS = {
    "GC=F": "Gold", "CL=F": "WTI Crude Oil", "NG=F": "Natural Gas",
    "SI=F": "Silver", "HG=F": "Copper", "ZW=F": "Wheat", "ZC=F": "Corn",
}

SECTOR_ETFS = {
    "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financial Services",
    "XLY": "Consumer Cyclical", "XLE": "Energy", "XLI": "Industrials",
    "XLB": "Basic Materials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLP": "Consumer Defensive", "XLC": "Communication Services",
}

CYCLE_PHASE_DEFINITIONS = {
    "Early Bull / Risk On": {"Technology", "Consumer Cyclical"},
    "Mid Cycle Expansion": {"Industrials", "Basic Materials"},
    "Late Cycle": {"Energy", "Financial Services"},
    "Defensive / Risk Off": {"Utilities", "Consumer Defensive", "Healthcare"},
}
CYCLE_PHASE_MIN_OVERLAP = 2
SECTOR_ROTATION_LEADING_LAGGING_COUNT = 3

# yfinance's sector strings differ from our friendly category names, so map them here.
SUPPLY_CHAIN_SECTOR_KEY = {
    "Technology": "Technology",
    "Energy": "Energy",
    "Healthcare": "Healthcare",
    "Financial Services": "Financial",
    "Consumer Cyclical": "Consumer Discretionary",
    "Industrials": "Industrials",
}

SUPPLY_CHAIN_EXPOSURE_MAP = {
    "Technology": {
        "china_manufacturing": 85, "taiwan_semiconductor": 90, "rare_earth_dependency": 75,
        "key_risks": [
            "Taiwan Strait tensions could disrupt semiconductor supply",
            "China tariffs affect manufacturing costs",
            "Rare earth export controls from China",
            "TSMC concentration risk for chip supply",
        ],
        "critical_suppliers": ["TSMC", "Foxconn", "Samsung"],
        "geographic_concentration": "Very High",
    },
    "Energy": {
        "china_manufacturing": 20, "taiwan_semiconductor": 15, "rare_earth_dependency": 30,
        "key_risks": [
            "Middle East conflict affects oil prices",
            "Russia sanctions impact natural gas supply",
            "OPEC+ production decisions",
        ],
        "critical_suppliers": ["OPEC nations", "Russia", "Canada"],
        "geographic_concentration": "High",
    },
    "Healthcare": {
        "china_manufacturing": 60, "taiwan_semiconductor": 25, "rare_earth_dependency": 20,
        "key_risks": [
            "API (active pharmaceutical ingredients) from China/India",
            "Medical device semiconductor dependency",
            "FDA approval supply chain requirements",
        ],
        "critical_suppliers": ["China API manufacturers", "India generics"],
        "geographic_concentration": "Moderate",
    },
    "Financial": {
        "china_manufacturing": 5, "taiwan_semiconductor": 10, "rare_earth_dependency": 5,
        "key_risks": [
            "Cybersecurity supply chain risks",
            "Data center hardware dependency",
            "Cloud provider concentration",
        ],
        "critical_suppliers": ["AWS", "Azure", "Google Cloud"],
        "geographic_concentration": "Low",
    },
    "Consumer Discretionary": {
        "china_manufacturing": 75, "taiwan_semiconductor": 40, "rare_earth_dependency": 45,
        "key_risks": [
            "China manufacturing tariff exposure",
            "Shipping cost volatility",
            "Consumer electronics chip shortage risk",
        ],
        "critical_suppliers": ["Chinese manufacturers", "Vietnam factories"],
        "geographic_concentration": "High",
    },
    "Industrials": {
        "china_manufacturing": 50, "taiwan_semiconductor": 35, "rare_earth_dependency": 55,
        "key_risks": [
            "Steel and aluminum tariff exposure",
            "Industrial automation chip dependency",
            "Rare earth for motors and batteries",
        ],
        "critical_suppliers": ["China steel", "German components"],
        "geographic_concentration": "Moderate",
    },
    "Default": {
        "china_manufacturing": 40, "taiwan_semiconductor": 30, "rare_earth_dependency": 30,
        "key_risks": ["General supply chain disruption risk"],
        "critical_suppliers": ["Various global suppliers"],
        "geographic_concentration": "Moderate",
    },
}

# --- Yield curve shape / recession-probability bands (2s10s / 3m10y spreads) ---
CURVE_INVERTED_THRESHOLD = -0.1
CURVE_FLAT_MAX = 0.25
CURVE_NORMAL_MAX = 1.0
RECESSION_PROB_LOW_MIN_SPREAD = 0.5
RECESSION_PROB_ELEVATED_MIN_SPREAD = 0.0
RECESSION_PROB_HIGH_MIN_SPREAD = -0.5

# --- Supply chain risk score weighting and shipping-trend adjustment ---
SUPPLY_CHAIN_CHINA_WEIGHT = 0.4
SUPPLY_CHAIN_TAIWAN_WEIGHT = 0.35
SUPPLY_CHAIN_RARE_EARTH_WEIGHT = 0.25
SHIPPING_FALLING_BONUS = 15
SHIPPING_RISING_PENALTY = -10
SHIPPING_TREND_THRESHOLD_PCT = 5
SUPPLY_CHAIN_CRITICAL_THRESHOLD = 70
SUPPLY_CHAIN_HIGH_THRESHOLD = 50
SUPPLY_CHAIN_MODERATE_THRESHOLD = 30

# --- Commodity signal bands (1-month % change) ---
COPPER_SIGNAL_THRESHOLD_PCT = 2
GOLD_SIGNAL_THRESHOLD_PCT = 3
OIL_SIGNAL_THRESHOLD_PCT = 5
GRAIN_SIGNAL_THRESHOLD_PCT = 5

# --- Global liquidity bands ---
M2_EXPANDING_THRESHOLD_PCT = 5
FED_BALANCE_SHEET_EXPANDING_THRESHOLD_PCT = 1
FED_BALANCE_SHEET_CONTRACTING_THRESHOLD_PCT = -1
M2_YOY_LOOKBACK_PERIODS = 12
FED_BALANCE_SHEET_LOOKBACK_PERIODS = 13

# --- Combined macro-signal score bands ---
MACRO_SIGNAL_VERY_BULLISH_MIN = 3
MACRO_SIGNAL_BULLISH = 2
MACRO_SIGNAL_NEUTRAL_MIN = -1
MACRO_SIGNAL_NEUTRAL_MAX = 1
MACRO_SIGNAL_BEARISH = -2
MACRO_SCORE_SUPPLY_CHAIN_LOW_RISK_THRESHOLD = 40


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


def _yf_last_close(symbol: str, period: str = "5d") -> Optional[float]:
    """Most recent close price for a yfinance symbol, or None on any failure."""
    try:
        hist = yf.Ticker(symbol).history(period=period)["Close"].dropna()
        return _clean(hist.iloc[-1]) if len(hist) else None
    except Exception:
        return None


def _yf_price_and_change(symbol: str, period: str = "1mo") -> Tuple[Optional[float], Optional[float]]:
    """Current price and % change over `period` for a yfinance symbol."""
    try:
        hist = yf.Ticker(symbol).history(period=period)["Close"].dropna()
        if len(hist) < 2:
            return None, None
        current = _clean(hist.iloc[-1])
        change_pct = _clean((hist.iloc[-1] / hist.iloc[0] - 1) * 100)
        return current, change_pct
    except Exception:
        return None, None


def _fred_value_and_change(df: Optional[pd.DataFrame], series_id: str, periods_back: int) -> Tuple[Optional[float], Optional[float]]:
    """Current value and % change vs. `periods_back` observations ago, from a FRED series DataFrame."""
    if df is None or len(df) <= periods_back:
        return None, None
    current = _clean(df[series_id].iloc[-1])
    prior = _clean(df[series_id].iloc[-(periods_back + 1)])
    if current is None or prior is None or prior == 0:
        return current, None
    return current, (current - prior) / abs(prior) * 100


class MacroAnalyzer:
    """Computes macro-environment and supply-chain risk context for one ticker's sector."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._stock = yf.Ticker(self.ticker)
        info = {}
        try:
            info = self._stock.info or {}
        except Exception:
            pass
        self.sector = info.get("sector")
        self.company_name = info.get("longName") or info.get("shortName") or self.ticker

    # ------------------------------------------------------------------
    # 1. Yield curve
    # ------------------------------------------------------------------

    def _fetch_yields_by_maturity(self) -> Dict[str, Optional[float]]:
        """1M/3M/1Y/2Y/5Y/10Y/30Y Treasury yields, from yfinance where available and FRED otherwise."""
        yields = {}
        for maturity, symbol in TREASURY_YF_TICKERS.items():
            yields[maturity] = _yf_last_close(symbol)

        for i, (maturity, series_id) in enumerate(TREASURY_FRED_SERIES.items()):
            df = fetch_fred_series(series_id)
            yields[maturity] = _clean(df[series_id].iloc[-1]) if df is not None and len(df) else None
            if i < len(TREASURY_FRED_SERIES) - 1:
                time.sleep(FRED_REQUEST_DELAY_SECONDS)

        return {m: yields.get(m) for m in ["1M", "3M", "1Y", "2Y", "5Y", "10Y", "30Y"]}

    def _curve_shape(self, spread_2s10s: Optional[float]) -> Optional[str]:
        """Classify the 2s10s spread as inverted/flat/normal/steep."""
        if spread_2s10s is None:
            return None
        if spread_2s10s < CURVE_INVERTED_THRESHOLD:
            return "inverted"
        if spread_2s10s <= CURVE_FLAT_MAX:
            return "flat"
        if spread_2s10s <= CURVE_NORMAL_MAX:
            return "normal"
        return "steep"

    def _recession_probability(self, spread_3m10y: Optional[float]) -> Optional[str]:
        """Recession-probability range proxy from the 3-month/10-year spread."""
        if spread_3m10y is None:
            return None
        if spread_3m10y > RECESSION_PROB_LOW_MIN_SPREAD:
            return "5-10%"
        if spread_3m10y >= RECESSION_PROB_ELEVATED_MIN_SPREAD:
            return "15-25%"
        if spread_3m10y >= RECESSION_PROB_HIGH_MIN_SPREAD:
            return "35-50%"
        return "60-80%"

    def _yield_curve_sector_impact(self, curve_shape: Optional[str]) -> str:
        """How the current yield curve shape affects this ticker's sector."""
        if curve_shape in ("inverted", "flat"):
            if self.sector in ("Financial Services", "Industrials"):
                return "negative"
            if self.sector in ("Utilities", "Consumer Defensive"):
                return "positive"
        elif curve_shape == "steep":
            if self.sector == "Financial Services":
                return "positive"
            if self.sector in ("Utilities", "Real Estate"):
                return "negative"
        return "neutral"

    def get_yield_curve(self) -> Dict:
        """Treasury yields across 7 maturities, key spreads, curve shape, and recession probability."""
        yields_by_maturity = self._fetch_yields_by_maturity()

        y2, y3m, y5, y10, y30 = (
            yields_by_maturity["2Y"], yields_by_maturity["3M"],
            yields_by_maturity["5Y"], yields_by_maturity["10Y"], yields_by_maturity["30Y"],
        )

        spread_2s10s = _clean(y10 - y2) if y10 is not None and y2 is not None else None
        spread_3m10y = _clean(y10 - y3m) if y10 is not None and y3m is not None else None
        spread_5s30s = _clean(y30 - y5) if y30 is not None and y5 is not None else None

        curve_shape = self._curve_shape(spread_2s10s)

        return {
            "yields_by_maturity": yields_by_maturity,
            "spreads": {"2s10s": spread_2s10s, "3m10y": spread_3m10y, "5s30s": spread_5s30s},
            "curve_shape": curve_shape,
            "recession_probability": self._recession_probability(spread_3m10y),
            "sector_impact": self._yield_curve_sector_impact(curve_shape),
        }

    # ------------------------------------------------------------------
    # 2. Credit markets
    # ------------------------------------------------------------------

    def get_credit_markets(self) -> Dict:
        """HYG/LQD/TLT performance, VIX-HYG correlation, and a risk-on/risk-off credit signal."""
        hyg_price, hyg_change = _yf_price_and_change("HYG")
        lqd_price, lqd_change = _yf_price_and_change("LQD")
        tlt_price, tlt_change = _yf_price_and_change("TLT")
        tnx_current = _yf_last_close("^TNX")

        hy_spread_proxy = _clean(hyg_change - tnx_current) if hyg_change is not None and tnx_current is not None else None
        ig_spread_proxy = _clean(lqd_change - tnx_current) if lqd_change is not None and tnx_current is not None else None

        credit_signal = "neutral"
        if hyg_change is not None and tlt_change is not None:
            if hyg_change < 0 and tlt_change > 0:
                credit_signal = "risk_off"
            elif hyg_change > 0 and tlt_change < 0:
                credit_signal = "risk_on"

        # Separate try/except since this is just supplementary context, not the main signal.
        correlation = None
        try:
            vix_hist = yf.Ticker("^VIX").history(period="1mo")["Close"].dropna()
            hyg_hist = yf.Ticker("HYG").history(period="1mo")["Close"].dropna()
            vix_hist.index = vix_hist.index.tz_localize(None).normalize()
            hyg_hist.index = hyg_hist.index.tz_localize(None).normalize()
            aligned = pd.concat([vix_hist.rename("vix"), hyg_hist.rename("hyg")], axis=1, join="inner").dropna()
            if len(aligned) > 2:
                vix_ret = aligned["vix"].pct_change().dropna()
                hyg_ret = aligned["hyg"].pct_change().dropna()
                correlation = _clean(vix_ret.corr(hyg_ret))
        except Exception:
            correlation = None

        if credit_signal == "risk_off":
            risk_appetite = "risk_averse"
        elif credit_signal == "risk_on":
            risk_appetite = "risk_seeking"
        else:
            risk_appetite = "neutral"

        return {
            "hyg_performance": {"price": hyg_price, "change_30d_pct": hyg_change},
            "lqd_performance": {"price": lqd_price, "change_30d_pct": lqd_change},
            "tlt_performance": {"price": tlt_price, "change_30d_pct": tlt_change},
            "hy_spread_proxy": hy_spread_proxy,
            "ig_spread_proxy": ig_spread_proxy,
            "vix_hyg_correlation": correlation,
            "credit_signal": credit_signal,
            "risk_appetite": risk_appetite,
        }

    # ------------------------------------------------------------------
    # 3. Commodities
    # ------------------------------------------------------------------

    def _fetch_commodity_prices(self) -> Dict[str, dict]:
        """Current price and 1-week/1-month % change for every `COMMODITY_TICKERS` symbol."""
        commodities = {}
        for symbol, name in COMMODITY_TICKERS.items():
            try:
                hist = yf.Ticker(symbol).history(period="1mo")["Close"].dropna()
                if len(hist) >= 2:
                    current = _clean(hist.iloc[-1])
                    change_1m = _clean((hist.iloc[-1] / hist.iloc[0] - 1) * 100)
                    week_slice = hist.tail(6)
                    change_1w = (
                        _clean((week_slice.iloc[-1] / week_slice.iloc[0] - 1) * 100)
                        if len(week_slice) > 1 else None
                    )
                else:
                    current, change_1w, change_1m = None, None, None
            except Exception:
                current, change_1w, change_1m = None, None, None

            commodities[symbol] = {
                "name": name, "current_price": current,
                "change_1w_pct": change_1w, "change_1m_pct": change_1m,
            }
        return commodities

    def _commodity_signals(self, commodities: Dict[str, dict]) -> Dict[str, str]:
        """Copper/gold/oil directional signals from their 1-month % change."""
        copper_change = commodities["HG=F"]["change_1m_pct"]
        if copper_change is not None and copper_change > COPPER_SIGNAL_THRESHOLD_PCT:
            copper_signal = "economic_expansion"
        elif copper_change is not None and copper_change < -COPPER_SIGNAL_THRESHOLD_PCT:
            copper_signal = "economic_contraction"
        else:
            copper_signal = "neutral"

        gold_change = commodities["GC=F"]["change_1m_pct"]
        if gold_change is not None and gold_change > GOLD_SIGNAL_THRESHOLD_PCT:
            gold_signal = "inflation_hedge_or_risk_off"
        elif gold_change is not None and gold_change < -GOLD_SIGNAL_THRESHOLD_PCT:
            gold_signal = "risk_on_or_deflation"
        else:
            gold_signal = "neutral"

        oil_change = commodities["CL=F"]["change_1m_pct"]
        if oil_change is not None and oil_change > OIL_SIGNAL_THRESHOLD_PCT:
            oil_signal = "inflationary_pressure"
        elif oil_change is not None and oil_change < -OIL_SIGNAL_THRESHOLD_PCT:
            oil_signal = "demand_concern"
        else:
            oil_signal = "neutral"

        return {"copper_signal": copper_signal, "gold_signal": gold_signal, "oil_signal": oil_signal}

    def _sector_commodity_impact(self, commodities: Dict[str, dict], signals: Dict[str, str]) -> List[str]:
        """Human-readable commodity-driven impact sentences relevant to this ticker's sector."""
        oil_signal, copper_signal, gold_signal = signals["oil_signal"], signals["copper_signal"], signals["gold_signal"]
        sector_commodity_impact = []

        if oil_signal == "inflationary_pressure" and self.sector == "Energy":
            sector_commodity_impact.append("Rising oil prices are a tailwind for Energy sector revenue")
        elif oil_signal == "demand_concern" and self.sector == "Energy":
            sector_commodity_impact.append("Falling oil prices pressure Energy sector revenue")
        if oil_signal == "inflationary_pressure" and self.sector == "Consumer Cyclical":
            sector_commodity_impact.append("Rising oil prices pressure input/transport costs for Consumer Discretionary")
        if copper_signal == "economic_expansion" and self.sector in ("Basic Materials", "Industrials"):
            sector_commodity_impact.append("Rising copper prices ('Dr. Copper') signal favorable demand for Materials/Industrials")
        if copper_signal == "economic_contraction" and self.sector in ("Basic Materials", "Industrials"):
            sector_commodity_impact.append("Falling copper prices signal softening industrial demand")
        if gold_signal == "inflation_hedge_or_risk_off" and self.sector == "Technology":
            sector_commodity_impact.append("Rising gold (risk-off signal) is typically a headwind for high-growth Technology valuations")

        wheat_change = commodities["ZW=F"]["change_1m_pct"] or 0
        corn_change = commodities["ZC=F"]["change_1m_pct"] or 0
        if (wheat_change > GRAIN_SIGNAL_THRESHOLD_PCT or corn_change > GRAIN_SIGNAL_THRESHOLD_PCT) and self.sector == "Consumer Defensive":
            sector_commodity_impact.append("Rising wheat/corn prices pressure margins for Consumer Staples food companies")

        if not sector_commodity_impact:
            sector_commodity_impact.append("No significant commodity-driven sector impact identified from current price moves")
        return sector_commodity_impact

    def get_commodity_indicators(self) -> Dict:
        """Price/change for 7 commodities, directional signals, and sector-specific impact notes."""
        commodities = self._fetch_commodity_prices()
        signals = self._commodity_signals(commodities)
        return {
            "commodities": commodities,
            "signals": signals,
            "sector_commodity_impact": self._sector_commodity_impact(commodities, signals),
        }

    # ------------------------------------------------------------------
    # 4. Supply chain risk
    # ------------------------------------------------------------------

    def _fallback_risk_label(self, score: float) -> str:
        """Classify the hardcoded-sector-profile score into a risk label (used when EDGAR data is unavailable)."""
        if score > SUPPLY_CHAIN_CRITICAL_THRESHOLD:
            return "Critical Supply Chain Risk"
        if score >= SUPPLY_CHAIN_HIGH_THRESHOLD:
            return "High Supply Chain Risk"
        if score >= SUPPLY_CHAIN_MODERATE_THRESHOLD:
            return "Moderate Supply Chain Risk"
        return "Low Supply Chain Risk"

    def get_supply_chain_risk(self) -> Dict:
        """Real 10-K-derived supply-chain risk when available, falling back to the hardcoded sector profile otherwise."""
        profile_key = SUPPLY_CHAIN_SECTOR_KEY.get(self.sector, "Default")
        profile = SUPPLY_CHAIN_EXPOSURE_MAP[profile_key]

        base_score = (
            profile["china_manufacturing"] * SUPPLY_CHAIN_CHINA_WEIGHT
            + profile["taiwan_semiconductor"] * SUPPLY_CHAIN_TAIWAN_WEIGHT
            + profile["rare_earth_dependency"] * SUPPLY_CHAIN_RARE_EARTH_WEIGHT
        )

        # No free source has the actual Baltic Dry Index, so use BDRY ETF price trend as a stand-in.
        baltic_dry_note = (
            "FRED does not host the Baltic Dry Index (BDIY is a Bloomberg "
            "ticker, not a FRED series). Using BDRY (Breakwave Dry Bulk "
            "Shipping ETF) price trend as a real-time shipping-conditions "
            "proxy instead."
        )
        shipping_price, shipping_change = _yf_price_and_change("BDRY")
        shipping_signal = None
        if shipping_change is not None:
            if shipping_change > SHIPPING_TREND_THRESHOLD_PCT:
                shipping_signal = "shipping_rates_rising"
            elif shipping_change < -SHIPPING_TREND_THRESHOLD_PCT:
                shipping_signal = "shipping_rates_falling"
            else:
                shipping_signal = "shipping_rates_stable"

        score = base_score
        if shipping_signal == "shipping_rates_falling":
            score += SHIPPING_FALLING_BONUS
        elif shipping_signal == "shipping_rates_rising":
            score += SHIPPING_RISING_PENALTY
        score = min(100, max(0, score))
        fallback_risk_label = self._fallback_risk_label(score)

        try:
            edgar_analysis = SupplyChainAnalyzer().get_supply_chain_analysis(self.ticker)
        except Exception:
            edgar_analysis = {"error": "10-K analysis unavailable", "source": "SEC EDGAR"}

        edgar_available = "error" not in edgar_analysis
        if edgar_available:
            risk_label = EDGAR_RISK_LABEL_MAP.get(edgar_analysis["overall_supply_chain_risk"], fallback_risk_label)
            data_source = "SEC 10-K filing (primary) + sector profile (supplementary)"
        else:
            risk_label = fallback_risk_label
            data_source = "Hardcoded sector profile (SEC EDGAR unavailable)"

        return {
            "baltic_dry_index": None,
            "baltic_dry_note": baltic_dry_note,
            "shipping_proxy": {
                "etf": "BDRY", "price": shipping_price,
                "change_1m_pct": shipping_change, "signal": shipping_signal,
            },
            "bdi_signal": shipping_signal,
            "supply_chain_profile": profile,
            "supply_chain_risk_score": _clean(score),
            "risk_label": risk_label,
            "edgar_analysis": edgar_analysis if edgar_available else None,
            "data_source": data_source,
        }

    # ------------------------------------------------------------------
    # 5. Global liquidity
    # ------------------------------------------------------------------

    def get_global_liquidity(self) -> Dict:
        """M2 money supply growth, Fed balance sheet trend, and reserve balances."""
        m2_df = fetch_fred_series("M2SL")
        time.sleep(FRED_REQUEST_DELAY_SECONDS)
        walcl_df = fetch_fred_series("WALCL")
        time.sleep(FRED_REQUEST_DELAY_SECONDS)
        wresbal_df = fetch_fred_series("WRESBAL")

        m2_current, m2_yoy_growth = _fred_value_and_change(m2_df, "M2SL", M2_YOY_LOOKBACK_PERIODS)
        fed_balance_sheet, fed_change_pct = _fred_value_and_change(walcl_df, "WALCL", FED_BALANCE_SHEET_LOOKBACK_PERIODS)
        reserve_balances = (
            _clean(wresbal_df["WRESBAL"].iloc[-1]) if wresbal_df is not None and len(wresbal_df) else None
        )

        fed_balance_sheet_trend = None
        if fed_change_pct is not None:
            if fed_change_pct > FED_BALANCE_SHEET_EXPANDING_THRESHOLD_PCT:
                fed_balance_sheet_trend = "expanding"
            elif fed_change_pct < FED_BALANCE_SHEET_CONTRACTING_THRESHOLD_PCT:
                fed_balance_sheet_trend = "contracting"
            else:
                fed_balance_sheet_trend = "stable"

        liquidity_signal = None
        if m2_yoy_growth is not None:
            if m2_yoy_growth > M2_EXPANDING_THRESHOLD_PCT:
                liquidity_signal = "expanding_liquidity"
            elif m2_yoy_growth >= 0:
                liquidity_signal = "stable_liquidity"
            else:
                liquidity_signal = "contracting_liquidity"

        equity_market_impact = {
            "expanding_liquidity": "bullish for stocks",
            "stable_liquidity": "neutral for stocks",
            "contracting_liquidity": "bearish for stocks",
        }.get(liquidity_signal)

        return {
            "m2_current": m2_current,
            "m2_yoy_growth": m2_yoy_growth,
            "fed_balance_sheet": fed_balance_sheet,
            "fed_balance_sheet_trend": fed_balance_sheet_trend,
            "reserve_balances": reserve_balances,
            "liquidity_signal": liquidity_signal,
            "equity_market_impact": equity_market_impact,
        }

    # ------------------------------------------------------------------
    # 6. Sector rotation
    # ------------------------------------------------------------------

    def get_sector_rotation(self) -> Dict:
        """1-month/3-month sector ETF performance rankings and a market-cycle-phase guess."""
        performances = []
        for etf, sector_name in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period="3mo")["Close"].dropna()
                if len(hist) < 2:
                    continue
                return_3m = _clean((hist.iloc[-1] / hist.iloc[0] - 1) * 100)
                month_slice = hist.tail(22)
                return_1m = (
                    _clean((month_slice.iloc[-1] / month_slice.iloc[0] - 1) * 100)
                    if len(month_slice) > 1 else None
                )
                performances.append({"etf": etf, "sector": sector_name, "return_1m": return_1m, "return_3m": return_3m})
            except Exception:
                continue

        rankings_1m = sorted(performances, key=lambda p: p["return_1m"] if p["return_1m"] is not None else -999, reverse=True)
        rankings_3m = sorted(performances, key=lambda p: p["return_3m"] if p["return_3m"] is not None else -999, reverse=True)
        for i, p in enumerate(rankings_1m, start=1):
            p["rank_1m"] = i
        for i, p in enumerate(rankings_3m, start=1):
            p["rank_3m"] = i

        leading_sectors = [p["sector"] for p in rankings_3m[:SECTOR_ROTATION_LEADING_LAGGING_COUNT]]
        lagging_sectors = [p["sector"] for p in rankings_3m[-SECTOR_ROTATION_LEADING_LAGGING_COUNT:]]
        leading_set = set(leading_sectors)

        best_phase, best_overlap = None, 0
        for phase, sectors in CYCLE_PHASE_DEFINITIONS.items():
            overlap = len(sectors & leading_set)
            if overlap > best_overlap:
                best_overlap, best_phase = overlap, phase
        market_cycle_phase = best_phase if best_overlap >= CYCLE_PHASE_MIN_OVERLAP else "Mixed / Transitional"

        ticker_sector_rank = next((p["rank_3m"] for p in rankings_3m if p["sector"] == self.sector), None)

        return {
            "sector_rankings_1m": rankings_1m,
            "sector_rankings_3m": rankings_3m,
            "leading_sectors": leading_sectors,
            "lagging_sectors": lagging_sectors,
            "market_cycle_phase": market_cycle_phase,
            "ticker_sector_rank": ticker_sector_rank,
        }

    # ------------------------------------------------------------------
    # 7. Full analysis
    # ------------------------------------------------------------------

    def _compute_macro_score(
        self, yield_curve: Optional[Dict], credit_markets: Optional[Dict],
        commodities: Optional[Dict], liquidity: Optional[Dict], supply_chain: Optional[Dict],
    ) -> int:
        """Tally +1/-1 votes across curve shape, credit signal, copper, liquidity, and supply chain."""
        score = 0

        curve_shape = yield_curve.get("curve_shape") if yield_curve else None
        if curve_shape in ("normal", "steep"):
            score += 1
        elif curve_shape == "inverted":
            score -= 1

        credit_signal = credit_markets.get("credit_signal") if credit_markets else None
        if credit_signal == "risk_on":
            score += 1
        elif credit_signal == "risk_off":
            score -= 1

        copper_signal = commodities.get("signals", {}).get("copper_signal") if commodities else None
        if copper_signal == "economic_expansion":
            score += 1
        elif copper_signal == "economic_contraction":
            score -= 1

        liquidity_signal = liquidity.get("liquidity_signal") if liquidity else None
        if liquidity_signal == "expanding_liquidity":
            score += 1
        elif liquidity_signal == "contracting_liquidity":
            score -= 1

        supply_chain_score = supply_chain.get("supply_chain_risk_score") if supply_chain else None
        if supply_chain_score is not None and supply_chain_score < MACRO_SCORE_SUPPLY_CHAIN_LOW_RISK_THRESHOLD:
            score += 1
        elif supply_chain_score is not None and supply_chain_score > SUPPLY_CHAIN_CRITICAL_THRESHOLD:
            score -= 1

        return score

    def _macro_signal_from_score(self, score: int) -> str:
        """Classify the combined macro score into Very Bullish..Very Bearish."""
        if score >= MACRO_SIGNAL_VERY_BULLISH_MIN:
            return "Very Bullish"
        if score == MACRO_SIGNAL_BULLISH:
            return "Bullish"
        if MACRO_SIGNAL_NEUTRAL_MIN <= score <= MACRO_SIGNAL_NEUTRAL_MAX:
            return "Neutral"
        if score == MACRO_SIGNAL_BEARISH:
            return "Bearish"
        return "Very Bearish"

    def get_full_macro_analysis(self) -> Dict:
        """Aggregate yield curve, credit, commodities, supply chain, liquidity, sector rotation, and a signal.

        Each sub-call is wrapped in its own try/except so one failing data source doesn't break the rest.
        """
        try:
            yield_curve = self.get_yield_curve()
        except Exception:
            yield_curve = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            credit_markets = self.get_credit_markets()
        except Exception:
            credit_markets = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            commodities = self.get_commodity_indicators()
        except Exception:
            commodities = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            supply_chain = self.get_supply_chain_risk()
        except Exception:
            supply_chain = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            liquidity = self.get_global_liquidity()
        except Exception:
            liquidity = None

        try:
            time.sleep(FULL_ANALYSIS_STEP_DELAY_SECONDS)
            sector_rotation = self.get_sector_rotation()
        except Exception:
            sector_rotation = None

        score = self._compute_macro_score(yield_curve, credit_markets, commodities, liquidity, supply_chain)

        return {
            "ticker": self.ticker,
            "yield_curve": yield_curve,
            "credit_markets": credit_markets,
            "commodities": commodities,
            "supply_chain": supply_chain,
            "liquidity": liquidity,
            "sector_rotation": sector_rotation,
            "macro_signal": self._macro_signal_from_score(score),
        }
