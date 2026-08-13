export default function ChartTooltip({ active, payload, label, valuePrefix = "$" }) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "10px 14px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
      }}
    >
      <p style={{ color: "var(--text-secondary)", fontSize: 11, fontWeight: 600, marginBottom: 8 }}>{label}</p>
      {payload.map((entry, i) => (
        <div
          key={entry.dataKey ?? i}
          style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: i === payload.length - 1 ? 0 : 4 }}
        >
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: entry.color }} />
          <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{entry.name}:</span>
          <span style={{ color: "var(--text)", fontWeight: 700 }}>
            {entry.value != null ? `${valuePrefix}${Number(entry.value).toFixed(2)}` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
