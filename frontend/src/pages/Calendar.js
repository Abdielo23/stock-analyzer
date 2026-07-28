import useFetch from "../hooks/useFetch";
import { fetchCalendar } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import DataTable from "../components/DataTable";
import SignalBadge from "../components/SignalBadge";

const EVENT_ICONS = {
  fomc: "🏛️",
  fed_speech: "🎤",
  economic_release: "📊",
  earnings: "📋",
  market_holiday: "🏖️",
};

export default function Calendar({ ticker }) {
  const { data, loading, error } = useFetch(fetchCalendar, ticker);

  if (loading) return <LoadingSpinner label={`Loading economic calendar for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No calendar data available.</p>;

  const { fomc = {}, fed_speeches = {}, economic_releases = {}, earnings_calendar = {}, market_holidays = {}, unified_timeline = [], alerts = [] } = data;

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Economic Calendar — {ticker}</h1>

      {alerts.length > 0 && (
        <SectionCard title="Alerts">
          {alerts.map((a, i) => (
            <div key={i} style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.35)", borderRadius: 8, padding: "10px 14px", marginBottom: 8, fontSize: 14, color: "var(--text)" }}>
              {a}
            </div>
          ))}
        </SectionCard>
      )}

      <SectionCard title="Unified Timeline">
        {unified_timeline.slice(0, 20).map((e, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--row-border)" }}>
            <span style={{ fontSize: 18 }}>{EVENT_ICONS[e.event_type] || "📌"}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{e.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{e.date} · {e.days_until}d away · {e.sector_relevance}</div>
            </div>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{e.impact_level}</span>
          </div>
        ))}
        {unified_timeline.length === 0 && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No upcoming events.</p>}
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="FOMC Dates">
          {fomc.next_fomc && (
            <p style={{ fontSize: 13, color: "var(--yellow)", marginBottom: 10 }}>
              Next: {fomc.next_fomc} ({fomc.days_until_next_fomc} days) — {fomc.sector_sensitivity}
            </p>
          )}
          {(fomc.upcoming_meetings || []).map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--row-border)", fontSize: 13 }}>
              <span>{m.decision_date}</span>
              <span style={{ color: "var(--text-secondary)" }}>{m.days_until}d</span>
            </div>
          ))}
          {(!fomc.upcoming_meetings || fomc.upcoming_meetings.length === 0) && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No upcoming meetings scheduled.</p>}
        </SectionCard>

        <SectionCard title="Fed Speeches">
          {(fed_speeches.upcoming_speeches || []).map((s, i) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--row-border)", background: s.is_chair_speech ? "rgba(37,99,235,0.08)" : "transparent" }}>
              <div style={{ fontSize: 13, fontWeight: s.is_chair_speech ? 700 : 400 }}>{s.is_chair_speech ? "🎙️ " : ""}{s.speaker}: {s.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{s.date} · {s.days_until}d away</div>
            </div>
          ))}
          {(!fed_speeches.upcoming_speeches || fed_speeches.upcoming_speeches.length === 0) && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No upcoming Fed speeches scheduled (RSS feed only lists past speeches).</p>}
        </SectionCard>
      </div>

      <SectionCard title="Economic Releases (next 60 days)">
        <DataTable
          columns={[
            { key: "expected_date", label: "Date" },
            { key: "name", label: "Event" },
            { key: "impact", label: "Impact" },
            { key: "what_to_watch", label: "What to Watch" },
          ]}
          rows={economic_releases.next_60_days}
          emptyText="No releases scheduled."
        />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title={`${ticker} Earnings`}>
          {earnings_calendar.ticker_next_earnings?.next_earnings_date ? (
            <p style={{ fontSize: 14 }}>
              Next: {earnings_calendar.ticker_next_earnings.next_earnings_date} ({earnings_calendar.ticker_next_earnings.days_until_earnings} days)
            </p>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No confirmed earnings date yet.</p>
          )}
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 8 }}>Season phase: {earnings_calendar.earnings_season_phase}</p>
        </SectionCard>

        <SectionCard title="Major Movers Earnings This Month">
          {(earnings_calendar.major_earnings_this_month || []).slice(0, 8).map((e, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--row-border)", fontSize: 13 }}>
              <span>{e.ticker}</span>
              <span style={{ color: "var(--text-secondary)" }}>{e.next_earnings_date || "—"} {e.days_until_earnings != null ? `(${e.days_until_earnings}d)` : ""}</span>
            </div>
          ))}
        </SectionCard>
      </div>

      <SectionCard title="Market Holidays">
        {(market_holidays.upcoming_holidays || []).map((h, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--row-border)", fontSize: 13 }}>
            <span>{h.name}</span>
            <span style={{ color: "var(--text-secondary)" }}>{h.date} ({h.days_until}d)</span>
          </div>
        ))}
        {(!market_holidays.upcoming_holidays || market_holidays.upcoming_holidays.length === 0) && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No remaining holidays this year.</p>}
      </SectionCard>
    </div>
  );
}
