// columns: [{ key, label, render? }]
// rowStyle: optional (row) => style object, merged onto each <tr>
export default function DataTable({ columns, rows, emptyText = "No data available", rowStyle }) {
  if (!rows || rows.length === 0) {
    return <p style={{ color: "var(--text-secondary)", fontSize: 13, padding: "8px 0" }}>{emptyText}</p>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  color: "var(--text-secondary)",
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  borderBottom: "1px solid var(--border)",
                  whiteSpace: "nowrap",
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.id ?? i} style={{ borderBottom: "1px solid var(--row-border)", ...(rowStyle ? rowStyle(row) : null) }}>
              {columns.map((col) => (
                <td key={col.key} style={{ padding: "8px 12px", color: "var(--text)", whiteSpace: "nowrap" }}>
                  {col.render ? col.render(row[col.key], row) : row[col.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
