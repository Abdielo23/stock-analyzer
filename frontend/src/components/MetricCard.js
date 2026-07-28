const COLORS = {
  green: "var(--green)",
  red: "var(--red)",
  yellow: "var(--yellow)",
  neutral: "var(--text)",
};

export default function MetricCard({ label, value, sub, color = "neutral" }) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        minWidth: 140,
      }}
    >
      <span style={{ fontSize: 12, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 }}>
        {label}
      </span>
      <span style={{ fontSize: 24, fontWeight: 700, color: COLORS[color] || COLORS.neutral }}>
        {value ?? "—"}
      </span>
      {sub && <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{sub}</span>}
    </div>
  );
}
