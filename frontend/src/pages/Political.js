import useFetch from "../hooks/useFetch";
import { fetchPolitical } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import DataTable from "../components/DataTable";
import { fmtNum, clamp } from "../utils/format";

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

export default function Political({ ticker }) {
  const { data, loading, error } = useFetch(fetchPolitical, ticker);

  if (loading) return <LoadingSpinner label={`Loading political risk for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No political data available.</p>;

  const { truth_social = {}, congress = {}, fed_policy = {}, executive_orders = {}, policy_risk = {}, historical_events = {}, political_signal } = data;

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Political & Policy Risk — {ticker}</h1>

      <SectionCard title="Political Signal">
        <SignalBadge signal={political_signal} size="lg" />
      </SectionCard>

      <SectionCard title="Policy Risk Score" right={policy_risk.risk_label ? <SignalBadge signal={policy_risk.risk_label} size="sm" /> : null}>
        <RiskGauge score={policy_risk.overall_policy_risk} />
        <ul style={{ marginTop: 14, paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)" }}>
          {(policy_risk.key_policy_risks || []).map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      </SectionCard>

      <SectionCard title="Truth Social">
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {truth_social.note || "Truth Social's RSS feed is currently unavailable (serves an HTML app shell, not a parseable feed) — no live post data to show."}
        </p>
        {truth_social.market_impact_summary && (
          <p style={{ fontSize: 13, marginTop: 8 }}>{truth_social.market_impact_summary}</p>
        )}
      </SectionCard>

      <SectionCard title="Congress Activity">
        <DataTable
          columns={[
            { key: "bill_number", label: "Bill" },
            { key: "title", label: "Title" },
            { key: "introduced_date", label: "Introduced" },
            { key: "status", label: "Status" },
            { key: "sponsor", label: "Sponsor" },
          ]}
          rows={congress.recent_bills}
          emptyText="No relevant bills found for this sector."
        />
        {congress.sector_legislative_risk && (
          <p style={{ marginTop: 10, fontSize: 13 }}>Legislative Risk: <SignalBadge signal={congress.sector_legislative_risk} size="sm" /></p>
        )}
      </SectionCard>

      <SectionCard title="Fed Policy" right={fed_policy.sector_fed_impact ? <SignalBadge signal={fed_policy.sector_fed_impact} size="sm" /> : null}>
        <DataTable
          columns={[
            { key: "title", label: "Title" },
            { key: "date", label: "Date" },
          ]}
          rows={fed_policy.recent_announcements}
          emptyText="No recent Fed announcements found."
        />
      </SectionCard>

      <SectionCard title="Executive Orders">
        <DataTable
          columns={[
            { key: "date", label: "Date" },
            { key: "title", label: "Title" },
          ]}
          rows={executive_orders.relevant_orders}
          emptyText="No sector-relevant executive orders found."
        />
      </SectionCard>

      <SectionCard title="Historical Policy Events">
        {(historical_events.relevant_historical_events || []).map((e, i) => (
          <div key={i} style={{ padding: "10px 0", borderBottom: "1px solid var(--row-border)" }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{e.event}</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>{e.impact}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>Market move: {e.market_move}</div>
          </div>
        ))}
        {(!historical_events.relevant_historical_events || historical_events.relevant_historical_events.length === 0) && (
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No historical events on record.</p>
        )}
      </SectionCard>
    </div>
  );
}
