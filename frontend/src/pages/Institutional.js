import useFetch from "../hooks/useFetch";
import { fetchInstitutional } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import DataTable from "../components/DataTable";
import SignalBadge from "../components/SignalBadge";
import { fmtLarge, fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export default function Institutional({ ticker }) {
  const { data, loading, error } = useFetch(fetchInstitutional, ticker);

  if (loading) return <LoadingSpinner label={`Loading institutional data for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No institutional data available.</p>;

  const { insider_trades = {}, institutional_holders = {}, sec_filings = [], finviz_ownership = {}, smart_money_signal } = data;

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Institutional & Insider — {ticker}</h1>

      <SectionCard title="Smart Money Signal">
        <SignalBadge signal={smart_money_signal} size="lg" />
      </SectionCard>

      <SectionCard title="Insider Activity" right={insider_trades.signal ? <SignalBadge signal={insider_trades.signal} size="sm" /> : null}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 16 }}>
          <StatRow label="Total Buys" value={insider_trades.total_buys ?? "—"} />
          <StatRow label="Total Sells" value={insider_trades.total_sells ?? "—"} />
          <StatRow label="Buy/Sell Ratio" value={typeof insider_trades.buy_sell_ratio === "string" ? insider_trades.buy_sell_ratio : fmtNum(insider_trades.buy_sell_ratio)} />
          <StatRow label="Net Shares" value={fmtNum(insider_trades.net_shares, 0)} />
        </div>
        <DataTable
          columns={[
            { key: "date", label: "Date" },
            { key: "name", label: "Insider" },
            { key: "title", label: "Title" },
            { key: "transaction_type", label: "Type" },
            { key: "shares", label: "Shares", render: (v) => fmtNum(v, 0) },
            { key: "value", label: "Value", render: (v) => fmtLarge(v) },
          ]}
          rows={insider_trades.recent_activity}
          emptyText="No recent insider transactions."
        />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Top Institutions">
          <DataTable
            columns={[
              { key: "name", label: "Institution" },
              { key: "shares", label: "Shares", render: (v) => fmtNum(v, 0) },
              { key: "value", label: "Value", render: (v) => fmtLarge(v) },
              { key: "pct_held", label: "% Held", render: (v) => (v != null ? `${fmtNum(v)}%` : "—") },
            ]}
            rows={institutional_holders.top_institutions}
            emptyText="No institutional holder data."
          />
        </SectionCard>

        <SectionCard title="Top Mutual Funds">
          <DataTable
            columns={[
              { key: "name", label: "Fund" },
              { key: "shares", label: "Shares", render: (v) => fmtNum(v, 0) },
              { key: "value", label: "Value", render: (v) => fmtLarge(v) },
              { key: "pct_held", label: "% Held", render: (v) => (v != null ? `${fmtNum(v)}%` : "—") },
            ]}
            rows={institutional_holders.top_funds}
            emptyText="No mutual fund holder data."
          />
        </SectionCard>
      </div>

      <SectionCard title="Finviz Ownership">
        <StatRow label="Insider Own %" value={finviz_ownership.insider_own_pct != null ? `${fmtNum(finviz_ownership.insider_own_pct)}%` : "—"} />
        <StatRow label="Institutional Own %" value={finviz_ownership.inst_own_pct != null ? `${fmtNum(finviz_ownership.inst_own_pct)}%` : "—"} />
        <StatRow label="Short Float %" value={finviz_ownership.short_float_pct != null ? `${fmtNum(finviz_ownership.short_float_pct)}%` : "—"} />
        <StatRow label="Short Ratio" value={fmtNum(finviz_ownership.short_ratio)} />
      </SectionCard>

      <SectionCard title="SEC Filings (Form 4)">
        <DataTable
          columns={[
            { key: "filed_date", label: "Filed" },
            { key: "filer_name", label: "Filer" },
            { key: "form_type", label: "Form" },
          ]}
          rows={sec_filings}
          emptyText="No recent SEC filings found."
        />
      </SectionCard>
    </div>
  );
}
