import useFetch from "../hooks/useFetch";
import { fetchFundamental } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import { fmtPctFraction, fmtLarge, fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function healthColor(score) {
  if (score == null) return "var(--text-secondary)";
  if (score >= 70) return "var(--green)";
  if (score >= 50) return "var(--yellow)";
  return "var(--red)";
}

export default function Fundamental({ ticker }) {
  const { data, loading, error } = useFetch(fetchFundamental, ticker);

  if (loading) return <LoadingSpinner label={`Loading fundamentals for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No fundamental data available.</p>;

  const { income = {}, balance = {}, cashflow = {}, profitability = {}, health_score } = data;

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Fundamental Analysis — {ticker}</h1>

      <SectionCard title="Health Score">
        <div style={{ fontSize: 40, fontWeight: 700, color: healthColor(health_score) }}>
          {health_score != null ? `${health_score}/100` : "—"}
        </div>
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Income Metrics">
          <StatRow label="Revenue" value={fmtLarge(income.revenue)} />
          <StatRow label="Revenue Growth (YoY)" value={fmtPctFraction(income.revenue_growth)} />
          <StatRow label="Gross Margin" value={fmtPctFraction(income.gross_margin)} />
          <StatRow label="Operating Margin" value={fmtPctFraction(income.operating_margin)} />
          <StatRow label="Net Margin" value={fmtPctFraction(income.net_margin)} />
          <StatRow label="EBITDA" value={fmtLarge(income.ebitda)} />
          <StatRow label="EPS" value={fmtNum(income.eps)} />
          <StatRow label="EPS Growth (YoY)" value={fmtPctFraction(income.eps_growth)} />
        </SectionCard>

        <SectionCard title="Balance Sheet">
          <StatRow label="Current Ratio" value={fmtNum(balance.current_ratio)} />
          <StatRow label="Quick Ratio" value={fmtNum(balance.quick_ratio)} />
          <StatRow label="Debt / Equity" value={fmtNum(balance.debt_to_equity)} />
          <StatRow label="Total Debt" value={fmtLarge(balance.total_debt)} />
          <StatRow label="Total Equity" value={fmtLarge(balance.total_equity)} />
          <StatRow label="Cash" value={fmtLarge(balance.cash)} />
          <StatRow label="Total Assets" value={fmtLarge(balance.total_assets)} />
        </SectionCard>

        <SectionCard title="Cash Flow">
          <StatRow label="Free Cash Flow" value={fmtLarge(cashflow.free_cashflow)} />
          <StatRow label="FCF Margin" value={fmtPctFraction(cashflow.fcf_margin)} />
          <StatRow label="FCF Growth (YoY)" value={fmtPctFraction(cashflow.fcf_growth)} />
          <StatRow label="Operating Cash Flow" value={fmtLarge(cashflow.operating_cashflow)} />
          <StatRow label="CapEx" value={fmtLarge(cashflow.capex)} />
        </SectionCard>

        <SectionCard title="Profitability">
          <StatRow label="ROE" value={fmtPctFraction(profitability.roe)} />
          <StatRow label="ROA" value={fmtPctFraction(profitability.roa)} />
          <StatRow label="ROIC" value={fmtPctFraction(profitability.roic)} />
        </SectionCard>
      </div>
    </div>
  );
}
