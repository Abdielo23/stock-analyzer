import { useState, useEffect } from "react";
import useFetch from "../hooks/useFetch";
import { fetchGeopolitical, fetchMacro } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import MetricCard from "../components/MetricCard";
import { fmtNum, clamp } from "../utils/format";

const SOURCE_TABS = [
  { key: "google_news", label: "Google News" },
  { key: "marketwatch", label: "MarketWatch" },
  { key: "cnbc", label: "CNBC" },
  { key: "seeking_alpha", label: "Seeking Alpha" },
  { key: "benzinga", label: "Benzinga" },
];

function RiskGauge({ score }) {
  const pct = clamp(score ?? 0, 0, 100);
  const color = pct >= 65 ? "var(--red)" : pct >= 35 ? "var(--yellow)" : "var(--green)";
  return (
    <div>
      <div style={{ height: 18, borderRadius: 999, background: "var(--bg)", overflow: "hidden", marginBottom: 8 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color }} />
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{score != null ? `${fmtNum(score, 0)}/100` : "—"}</div>
    </div>
  );
}

export default function Geopolitical({ ticker }) {
  const { data, loading, error } = useFetch(fetchGeopolitical, ticker);
  const [activeSource, setActiveSource] = useState("google_news");
  const [macro, setMacro] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchMacro(ticker).then((res) => {
      if (!cancelled) setMacro(res);
    }).catch(() => {
      if (!cancelled) setMacro(null);
    });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (loading) return <LoadingSpinner label={`Loading geopolitical risk for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No geopolitical data available.</p>;

  const { geopolitical_risk = {}, multi_source_news = {}, global_market_context = {}, gdelt_events = {}, geopolitical_signal } = data;
  const supplyChain = macro?.supply_chain;

  const bySource = multi_source_news.by_source || {};
  const activeArticles = activeSource === "google_news"
    ? (multi_source_news.ticker_specific || multi_source_news.all_articles || [])
    : (bySource[activeSource]?.articles || []);

  const markets = global_market_context.markets || {};

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Geopolitical Risk — {ticker}</h1>

      <SectionCard title="Geopolitical Signal">
        <SignalBadge signal={geopolitical_signal} size="lg" />
      </SectionCard>

      <SectionCard title="Risk Score">
        <RiskGauge score={geopolitical_risk.overall_geopolitical_risk} />
        <ul style={{ marginTop: 14, paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)" }}>
          {(geopolitical_risk.risk_factors || []).map((r, i) => <li key={i}>{r}</li>)}
        </ul>
        {(!geopolitical_risk.risk_factors || geopolitical_risk.risk_factors.length === 0) && (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>No specific risk factors flagged.</p>
        )}
      </SectionCard>

      <SectionCard title="News by Source">
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {SOURCE_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveSource(tab.key)}
              style={{
                background: activeSource === tab.key ? "var(--accent)" : "var(--bg)",
                color: activeSource === tab.key ? "#fff" : "var(--text-secondary)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "6px 14px",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {tab.label} {bySource[tab.key] ? `(${bySource[tab.key].count})` : ""}
            </button>
          ))}
        </div>
        {activeArticles.slice(0, 10).map((a, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--row-border)" }}>
            <a href={a.url || a.link} target="_blank" rel="noreferrer" style={{ color: "var(--text)", fontSize: 13, textDecoration: "none", flex: 1 }}>{a.title}</a>
            <SignalBadge signal={a.sentiment_compound > 0.1 ? "positive" : a.sentiment_compound < -0.1 ? "negative" : "neutral"} size="sm" />
          </div>
        ))}
        {activeArticles.length === 0 && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No articles found for this source.</p>}
      </SectionCard>

      <SectionCard title="Global Market Context (5-day change)">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
          {Object.entries(markets).map(([symbol, m]) => (
            <MetricCard
              key={symbol}
              label={m.name}
              value={m.current_price != null ? fmtNum(m.current_price) : "—"}
              sub={m.change_5d_pct != null ? `${m.change_5d_pct >= 0 ? "+" : ""}${fmtNum(m.change_5d_pct)}%` : "—"}
              color={m.change_5d_pct == null ? "neutral" : m.change_5d_pct >= 0 ? "green" : "red"}
            />
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Supply Chain Risk" right={supplyChain?.risk_label ? <SignalBadge signal={supplyChain.risk_label} size="sm" /> : null}>
        {supplyChain ? (
          <>
            <p style={{ fontSize: 14, marginBottom: 8 }}>Risk Score: {fmtNum(supplyChain.supply_chain_risk_score, 0)}/100</p>
            <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)" }}>
              {(supplyChain.supply_chain_profile?.key_risks || []).map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </>
        ) : (
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No supply chain profile available.</p>
        )}
      </SectionCard>

      <SectionCard title="GDELT Global Events">
        {(gdelt_events.events || []).slice(0, 10).map((e, i) => (
          <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--row-border)", fontSize: 13 }}>
            <a href={e.url} target="_blank" rel="noreferrer" style={{ color: "var(--text)", textDecoration: "none" }}>{e.title}</a>
            <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 2 }}>{e.domain} · {e.date}</div>
          </div>
        ))}
        {(!gdelt_events.events || gdelt_events.events.length === 0) && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No GDELT events found.</p>}
      </SectionCard>
    </div>
  );
}
