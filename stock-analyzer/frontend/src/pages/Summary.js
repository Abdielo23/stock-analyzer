import { useEffect, useRef, useState } from "react";
import { fetchSummary } from "../api/stockApi";
import SectionCard from "../components/SectionCard";
import { fmtNum, fmtSigned } from "../utils/format";

const PROGRESS_MESSAGES = [
  "Analyzing fundamentals...",
  "Running DCF valuation...",
  "Calculating technical indicators...",
  "Assessing risk metrics...",
  "Checking institutional activity...",
  "Analyzing geopolitical risk...",
  "Running Monte Carlo simulation...",
  "Generating investment statement...",
];

const WHAT_GETS_ANALYZED = [
  "Fundamental health & profitability", "DCF & relative valuation", "Technical indicators & trend",
  "Volume & money flow", "Risk, volatility & drawdown", "Institutional & insider activity",
  "Market sentiment & analyst ratings", "Earnings history & quality", "Quantitative factor scores",
  "Social sentiment (Reddit/WSB)", "Geopolitical risk", "Political & policy risk",
  "Macro environment & supply chain", "Economic calendar & catalysts", "Cross-module investment verdict",
];

const VERDICT_STYLES = {
  "STRONG BUY": { bg: "rgba(22,163,74,0.18)", fg: "#16a34a", border: "#16a34a" },
  "BUY": { bg: "rgba(34,197,94,0.15)", fg: "var(--green)", border: "var(--green)" },
  "WEAK BUY": { bg: "rgba(74,222,128,0.15)", fg: "#4ade80", border: "#4ade80" },
  "LEAN BUY": { bg: "rgba(74,222,128,0.15)", fg: "#4ade80", border: "#4ade80" },
  "HOLD": { bg: "rgba(234,179,8,0.15)", fg: "var(--yellow)", border: "var(--yellow)" },
  "LEAN SELL": { bg: "rgba(249,115,22,0.15)", fg: "#f97316", border: "#f97316" },
  "WEAK SELL": { bg: "rgba(249,115,22,0.15)", fg: "#f97316", border: "#f97316" },
  "SELL": { bg: "rgba(239,68,68,0.15)", fg: "var(--red)", border: "var(--red)" },
  "STRONG SELL": { bg: "rgba(185,28,28,0.18)", fg: "#b91c1c", border: "#b91c1c" },
};

const COMPONENT_LABELS = {
  fundamental: "Fundamental Health", valuation: "Valuation (DCF)", technical: "Technical Signal",
  volume: "Volume & Flow", risk: "Risk Profile", earnings: "Earnings Trend",
  institutional: "Smart Money", sentiment: "Market Sentiment", geopolitical: "Geopolitical Risk",
  political: "Political Risk", macro: "Macro Environment", quantitative: "Quant Signal",
};

const DATA_SUMMARY_LABELS = {
  health_score: "Health Score", dcf_upside_pct: "DCF Upside %", technical_signal: "Technical",
  volume_signal: "Volume", risk_label: "Risk", earnings_signal: "Earnings",
  smart_money_signal: "Smart Money", sentiment_signal: "Sentiment", geopolitical_signal: "Geopolitical",
  political_signal: "Political", macro_signal: "Macro", quant_signal: "Quant",
  composite_factor_score: "Composite Factor Score", monte_carlo_prob_gain: "Monte Carlo Prob. Gain",
};

export default function Summary({ ticker }) {
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [progressIdx, setProgressIdx] = useState(0);
  const [copied, setCopied] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    setStatus("idle");
    setResult(null);
    setErrorMsg(null);
  }, [ticker]);

  useEffect(() => () => clearInterval(intervalRef.current), []);

  const runAnalysis = () => {
    setStatus("loading");
    setErrorMsg(null);
    setProgressIdx(0);
    intervalRef.current = setInterval(() => {
      setProgressIdx((i) => (i + 1) % PROGRESS_MESSAGES.length);
    }, 10000);

    fetchSummary(ticker)
      .then((data) => {
        clearInterval(intervalRef.current);
        setResult(data);
        setStatus("done");
      })
      .catch((err) => {
        clearInterval(intervalRef.current);
        setErrorMsg(err?.response?.data?.detail || err?.message || "Failed to generate summary");
        setStatus("error");
      });
  };

  const copyPrompt = () => {
    navigator.clipboard.writeText(result?.ai_prompt || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (status === "idle" || status === "error") {
    return (
      <div style={{ maxWidth: 800 }}>
        <h1 style={{ fontSize: 22, marginBottom: 20 }}>AI Investment Summary — {ticker}</h1>
        <SectionCard title="What this does">
          <p style={{ fontSize: 14, color: "var(--text)", marginBottom: 12 }}>
            Generates a professional, cross-module investment statement for {ticker} plus a ready-to-use
            prompt you can paste into ChatGPT, Claude, or Gemini for further AI analysis.
          </p>
          <p style={{ fontSize: 13, color: "var(--yellow)", marginBottom: 16 }}>
            ⏱️ This analysis calls all 15 backend modules and takes <strong>2-3 minutes</strong> to complete.
          </p>
          <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)", marginBottom: 20, lineHeight: 1.8 }}>
            {WHAT_GETS_ANALYZED.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
          {errorMsg && <p style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }}>Error: {errorMsg}</p>}
          <button
            onClick={runAnalysis}
            style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "14px 28px", fontSize: 15, fontWeight: 700, cursor: "pointer" }}
          >
            🤖 Generate Full Analysis
          </button>
        </SectionCard>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div style={{ maxWidth: 800, display: "flex", flexDirection: "column", alignItems: "center", padding: "60px 0", gap: 20 }}>
        <div style={{ width: 40, height: 40, borderRadius: "50%", border: "3px solid var(--border)", borderTopColor: "var(--accent)", animation: "spin 0.8s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p style={{ fontSize: 16, color: "var(--text)" }}>{PROGRESS_MESSAGES[progressIdx]}</p>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>This typically takes 2-3 minutes — please don't navigate away.</p>
      </div>
    );
  }

  // status === "done"
  const { verdict, score, score_breakdown = {}, data_summary = {}, statement, ai_prompt } = result;
  const vStyle = VERDICT_STYLES[verdict] || VERDICT_STYLES.HOLD;
  const statementSections = (statement || "").split("\n\n");

  return (
    <div style={{ maxWidth: 900 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>AI Investment Summary — {ticker}</h1>

      <div style={{ background: vStyle.bg, border: `2px solid ${vStyle.border}`, borderRadius: 12, padding: "24px", textAlign: "center", marginBottom: 20 }}>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 6 }}>OVERALL VERDICT</div>
        <div style={{ fontSize: 36, fontWeight: 800, color: vStyle.fg }}>{verdict}</div>
        <div style={{ fontSize: 14, color: "var(--text-secondary)", marginTop: 6 }}>Score: {score}/12</div>
      </div>

      <SectionCard title="Score Breakdown">
        {Object.entries(score_breakdown).map(([key, value]) => (
          <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--row-border)" }}>
            <span style={{ fontSize: 14 }}>{COMPONENT_LABELS[key] || key}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: value > 0 ? "var(--green)" : value < 0 ? "var(--red)" : "var(--text-secondary)" }}>
              {fmtSigned(value)}
            </span>
          </div>
        ))}
      </SectionCard>

      <SectionCard title="Data Summary">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          {Object.entries(DATA_SUMMARY_LABELS).map(([key, label]) => (
            <div key={key} style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {typeof data_summary[key] === "number" ? fmtNum(data_summary[key]) : (data_summary[key] || "—")}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Investment Statement">
        {statementSections.map((section, i) => {
          const lines = section.split("\n");
          return (
            <div key={i} style={{ padding: "12px 0", borderBottom: i < statementSections.length - 1 ? "1px solid var(--row-border)" : "none" }}>
              {lines.map((line, j) => (
                <p key={j} style={{ fontSize: 14, lineHeight: 1.6, margin: j === 0 ? "0 0 4px 0" : "4px 0", fontWeight: j === 0 && line.startsWith("OVERALL VERDICT") ? 700 : 400 }}>
                  {line}
                </p>
              ))}
            </div>
          );
        })}
      </SectionCard>

      <SectionCard title="AI Prompt">
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
          Copy this prompt and paste it into ChatGPT, Claude, or Gemini for a deeper independent analysis.
        </p>
        <textarea
          readOnly
          value={ai_prompt}
          style={{ width: "100%", height: 300, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", fontSize: 12, fontFamily: "monospace", padding: 12, resize: "vertical" }}
        />
        <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <button
            onClick={copyPrompt}
            style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "10px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
          >
            {copied ? "✓ Copied!" : "📋 Copy to Clipboard"}
          </button>
          <a href="https://chat.openai.com" target="_blank" rel="noreferrer" style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 18px", fontSize: 13, color: "var(--text)", textDecoration: "none" }}>ChatGPT →</a>
          <a href="https://claude.ai" target="_blank" rel="noreferrer" style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 18px", fontSize: 13, color: "var(--text)", textDecoration: "none" }}>Claude.ai →</a>
          <a href="https://gemini.google.com" target="_blank" rel="noreferrer" style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 18px", fontSize: 13, color: "var(--text)", textDecoration: "none" }}>Gemini →</a>
        </div>
      </SectionCard>

      <button
        onClick={runAnalysis}
        style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 18px", fontSize: 13, color: "var(--text-secondary)", cursor: "pointer", marginTop: 8 }}
      >
        ↻ Re-run Analysis
      </button>
    </div>
  );
}
