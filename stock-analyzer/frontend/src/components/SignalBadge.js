function colorForSignal(signal) {
  if (!signal) return "neutral";
  const s = String(signal).toLowerCase();

  if (s.includes("strong sell") || s.includes("strong_sell") || s.includes("high risk") || s.includes("miss")) return "red";
  if (s.includes("strong buy") || s.includes("strong_buy") || s.includes("low risk") || s.includes("beat")) return "green";
  if (s.includes("undervalued") || s.includes("cheap")) return "green";
  if (s.includes("overvalued") || s.includes("expensive")) return "red";
  if (s.includes("excellent") || s.includes("good")) return "green";
  if (s.includes("below average") || s.includes("poor")) return "red";
  if (s.includes("fair") || s.includes("average")) return "yellow";
  if (s.includes("bearish") || s.includes("sell") || s.includes("negative")) return "red";
  if (s.includes("bullish") || s.includes("buy") || s.includes("strong") || s.includes("positive")) return "green";
  if (s.includes("neutral") || s.includes("hold") || s.includes("moderate")) return "yellow";
  return "neutral";
}

const COLORS = {
  green: { bg: "rgba(34,197,94,0.15)", fg: "var(--green)", border: "rgba(34,197,94,0.4)" },
  red: { bg: "rgba(239,68,68,0.15)", fg: "var(--red)", border: "rgba(239,68,68,0.4)" },
  yellow: { bg: "rgba(234,179,8,0.15)", fg: "var(--yellow)", border: "rgba(234,179,8,0.4)" },
  neutral: { bg: "rgba(136,136,170,0.15)", fg: "var(--text-secondary)", border: "rgba(136,136,170,0.4)" },
};

export default function SignalBadge({ signal, size = "md" }) {
  const label = signal == null || signal === "" ? "N/A" : String(signal).replace(/_/g, " ");
  const c = COLORS[colorForSignal(signal)];
  const padding = size === "lg" ? "8px 20px" : size === "sm" ? "2px 8px" : "4px 12px";
  const fontSize = size === "lg" ? "18px" : size === "sm" ? "11px" : "13px";

  return (
    <span
      style={{
        display: "inline-block",
        padding,
        fontSize,
        fontWeight: 600,
        borderRadius: 999,
        background: c.bg,
        color: c.fg,
        border: `1px solid ${c.border}`,
        textTransform: "capitalize",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
