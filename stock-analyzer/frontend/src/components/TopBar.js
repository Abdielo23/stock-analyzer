import { useState, useEffect, useRef } from "react";
import { BarChart3, Search, Sun, Moon } from "lucide-react";

const QUICK_PICKS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "SPY"];

export default function TopBar({ ticker, onSearch, darkMode, onToggleDarkMode }) {
  const [input, setInput] = useState(ticker);
  const [searchShortcut, setSearchShortcut] = useState("Ctrl K");
  const inputRef = useRef(null);

  useEffect(() => {
    setInput(ticker);
  }, [ticker]);

  useEffect(() => {
    if (navigator.userAgent.includes("Mac")) {
      setSearchShortcut("⌘K");
    }
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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
        height: 64,
        minHeight: 64,
        background: "var(--topbar-bg)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        gap: 24,
        padding: "0 20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 18, color: "var(--text)", whiteSpace: "nowrap" }}>
        <BarChart3 size={20} color="var(--accent)" />
        <span>Stock Analyzer</span>
      </div>

      <form onSubmit={handleSubmit} style={{ position: "relative", width: 320 }}>
        <Search
          size={16}
          color="var(--text-secondary)"
          style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
        />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Search ticker or company..."
          className="topbar-search-input"
          style={{
            width: "100%",
            padding: "8px 44px 8px 36px",
            fontSize: 14,
          }}
        />
        <span
          style={{
            position: "absolute",
            right: 8,
            top: "50%",
            transform: "translateY(-50%)",
            fontSize: 10,
            fontWeight: 500,
            color: "var(--text-secondary)",
            background: "var(--topbar-bg)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: "2px 5px",
            pointerEvents: "none",
          }}
        >
          {searchShortcut}
        </span>
      </form>

      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {QUICK_PICKS.map((symbol) => (
          <button
            key={symbol}
            type="button"
            onClick={() => runSearch(symbol)}
            className={`topbar-pill${symbol === ticker ? " active" : ""}`}
            style={{
              borderRadius: 6,
              padding: "6px 12px",
              fontSize: 12,
              fontWeight: 600,
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
          className="topbar-toggle-btn"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderRadius: 8,
            padding: "8px 14px",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          {darkMode ? <Sun size={16} /> : <Moon size={16} />}
          <span>{darkMode ? "Light" : "Dark"}</span>
        </button>
      </div>
    </header>
  );
}
