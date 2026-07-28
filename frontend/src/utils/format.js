export function fmtNum(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(decimals);
}

export function fmtPct(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number(value).toFixed(decimals)}%`;
}

// For fields stored as a 0-1 fraction (e.g. 0.0643 = 6.43%). Guards against
// `null * 100 === 0` silently rendering missing data as "0.00%".
export function fmtPctFraction(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(Number(value) * 100).toFixed(decimals)}%`;
}

export function fmtMoney(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return `$${Number(value).toFixed(decimals)}`;
}

export function fmtLarge(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
  return `$${Number(value).toFixed(2)}`;
}

export function fmtCompactNum(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return `${Number(value).toFixed(0)}`;
}

export function fmtDate(value) {
  if (!value) return "—";
  return String(value).slice(0, 10);
}

export function titleCase(value) {
  if (!value) return "—";
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Exact match only, to avoid collisions like "low_quality" matching "low".
// Context-dependent words (high/low/extreme) are classified per call site instead.
const POSITIVE_SIGNALS = new Set([
  "bullish", "very bullish", "buy", "strong buy", "undervalued", "accumulation",
  "strong_buying", "buying", "above", "above_vwap", "cheap", "fair", "high_quality",
  "trending", "increasing", "excellent", "good", "acceptable", "positive",
  "contango", "accommodative", "complacent", "strong_beat_trend", "beat_trend",
]);

const NEGATIVE_SIGNALS = new Set([
  "bearish", "very bearish", "sell", "strong sell", "overvalued", "distribution",
  "strong_selling", "selling", "below", "below_vwap", "expensive", "low_quality",
  "decreasing", "poor", "speculative", "extreme_fear", "high_fear",
  "inverted", "restrictive", "negative", "backwardation", "aggressive",
  "overbought", "oversold", "mixed", "strong_miss_trend", "miss_trend",
]);

export function signalTone(value) {
  if (value == null) return "neutral";
  const v = String(value).toLowerCase().trim();
  if (POSITIVE_SIGNALS.has(v)) return "positive";
  if (NEGATIVE_SIGNALS.has(v)) return "negative";
  return "neutral";
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function fmtSigned(value, decimals = 0) {
  if (value == null || Number.isNaN(value)) return "—";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(decimals)}`;
}
