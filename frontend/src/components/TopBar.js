import { useState, useEffect } from "react";

const QUICK_PICKS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "SPY"];

export default function TopBar({ ticker, onSearch, darkMode, onToggleDarkMode }) {
  const [input, setInput] = useState(ticker);

  useEffect(() => {
    setInput(ticker);
  }, [ticker]);

  const runSearch = (symbol) => {
    const clean = String(symbol).trim().toUpperCase();
    if (!clean) return;
    onSearch(clean);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    runSearch(input);
  };

  return (
    <header
      style={{
        height: 60,
        minHeight: 60,
        background: "var(--topbar-bg)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: 24,
        padding: "0 20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 18, color: "var(--text)", whiteSpace: "nowrap" }}>
        <span>📊</span>
        <span>Stock Analyzer</span>
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter ticker (e.g. AAPL)"
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "8px 12px",
            color: "var(--text)",
            fontSize: 14,
            width: 160,
          }}
        />
        <button
          type="submit"
          style={{
            background: "var(--accent)",
            border: "none",
            borderRadius: 8,
            padding: "8px 16px",
            color: "#fff",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Search
        </button>
      </form>

      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {QUICK_PICKS.map((symbol) => (
          <button
            key={symbol}
            type="button"
            onClick={() => runSearch(symbol)}
            style={{
              background: symbol === ticker ? "var(--accent)" : "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 999,
              padding: "5px 12px",
              color: symbol === ticker ? "#fff" : "var(--text-secondary)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {symbol}
          </button>
        ))}
      </div>

      <div style={{ marginLeft: "auto" }}>
        <button
          type="button"
          onClick={onToggleDarkMode}
          style={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "8px 14px",
            color: "var(--text)",
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          {darkMode ? "☀️ Light" : "🌙 Dark"}
        </button>
      </div>
    </header>
  );
}
