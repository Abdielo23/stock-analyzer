import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchEarnings } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import { fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export default function Earnings({ ticker }) {
  const { data, loading, error } = useFetch(fetchEarnings, ticker);

  if (loading) return <LoadingSpinner label={`Loading earnings for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No earnings data available.</p>;

  const { history = {}, next_earnings = {}, eps_trend = {}, revenue_trend = {}, guidance = {}, earnings_quality = {}, earnings_signal } = data;

  const epsChart = (history.quarters || []).slice().reverse().map((q) => ({
    date: q.date,
    Estimated: q.estimated_eps,
    Reported: q.reported_eps,
    beat: q.beat_eps,
  }));

  const revChart = (revenue_trend.quarters || []).map((q, i) => ({
    label: `Q${i + 1}`,
    Revenue: q.revenue != null ? q.revenue / 1e9 : null,
  }));

  const showEarningsAlert = next_earnings.days_until_earnings != null && next_earnings.days_until_earnings < 30;

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Earnings Analysis — {ticker}</h1>

      <SectionCard title="Earnings Signal">
        <SignalBadge signal={earnings_signal} size="lg" />
        {showEarningsAlert && (
          <p style={{ marginTop: 12, color: "var(--yellow)", fontSize: 13 }}>
            ⚠️ Next earnings in {next_earnings.days_until_earnings} days ({next_earnings.next_earnings_date}) — elevated volatility expected.
          </p>
        )}
      </SectionCard>

      <SectionCard title="EPS Beat Rate (last 8 quarters)">
        <div style={{ height: 18, borderRadius: 999, background: "var(--bg)", overflow: "hidden", marginBottom: 8 }}>
          <div style={{ width: `${history.eps_beat_rate || 0}%`, height: "100%", background: "var(--green)" }} />
        </div>
        <div style={{ fontSize: 24, fontWeight: 700 }}>{fmtNum(history.eps_beat_rate, 0)}%</div>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6 }}>Avg surprise: {fmtNum(history.avg_eps_surprise_pct)}%</p>
      </SectionCard>

      {epsChart.length > 0 && (
        <SectionCard title="EPS History (Reported vs Estimated)">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={epsChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Bar dataKey="Estimated" fill="var(--text-secondary)" />
              <Bar dataKey="Reported">
                {epsChart.map((d, i) => (
                  <Cell key={i} fill={d.beat ? "var(--green)" : "var(--red)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {revChart.length > 0 && (
        <SectionCard title="Quarterly Revenue Trend ($B)">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={revChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => `$${fmtNum(v)}B`} />
              <Line type="monotone" dataKey="Revenue" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 8 }}>Trend: {revenue_trend.revenue_trend || "—"}</p>
        </SectionCard>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Earnings Quality">
          <StatRow label="Accruals Ratio" value={fmtNum(earnings_quality.accruals_ratio, 3)} />
          <StatRow label="Quality Rating" value={earnings_quality.earnings_quality || "—"} />
          <StatRow label="Sloan Ratio" value={fmtNum(earnings_quality.sloan_ratio, 3)} />
          <StatRow label="Sloan Signal" value={earnings_quality.sloan_signal || "—"} />
          <StatRow label="Dilution Warning" value={earnings_quality.dilution_warning ? "Yes" : "No"} />
        </SectionCard>

        <SectionCard title="Guidance">
          <StatRow label="Forward EPS" value={fmtNum(guidance.forward_estimates?.forward_eps)} />
          <StatRow label="Forward P/E" value={fmtNum(guidance.forward_estimates?.forward_pe)} />
          <StatRow label="PEG Ratio" value={fmtNum(guidance.forward_estimates?.peg_ratio)} />
          <StatRow label="Implied Growth" value={guidance.implied_growth != null ? `${fmtNum(guidance.implied_growth)}%` : "—"} />
          <StatRow label="EPS Trend" value={eps_trend.eps_trend || "—"} />
        </SectionCard>
      </div>
    </div>
  );
}
