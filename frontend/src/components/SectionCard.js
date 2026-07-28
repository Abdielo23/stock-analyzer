export default function SectionCard({ title, children, right }) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        padding: "18px 20px",
        marginBottom: 20,
      }}
    >
      {title && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <h3
            style={{
              fontSize: 12,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: 0.8,
              color: "var(--text-secondary)",
              margin: 0,
            }}
          >
            {title}
          </h3>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}
