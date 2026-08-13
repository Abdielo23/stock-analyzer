import { Scale, Target, Activity } from "lucide-react";
import useFetch from "../hooks/useFetch";
import { fetchValuation } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import DataTable from "../components/DataTable";
import SignalBadge from "../components/SignalBadge";
import { fmtPct, fmtPctFraction, fmtMoney, fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

const MULTIPLE_LABELS = {
  pe: "P/E", forward_pe: "Forward P/E", peg: "PEG",
  ev_ebitda: "EV/EBITDA", ev_sales: "EV/Sales", price_book: "Price/Book", price_fcf: "Price/FCF",
};

function PriceVsIntrinsicBar({ currentPrice, intrinsicValue }) {
  if (currentPrice == null || intrinsicValue == null) return null;
  const max = Math.max(currentPrice, intrinsicValue) * 1.15;
  const currentPct = (currentPrice / max) * 100;
  const intrinsicPct = (intrinsicValue / max) * 100;

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ position: "relative", height: 16, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 999, overflow: "hidden", marginBottom: 8 }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${intrinsicPct}%`, background: "var(--accent)", borderRadius: 999 }} />
        <div style={{ position: "absolute", left: `${currentPct}%`, top: 0, bottom: 0, width: 2, background: "var(--text)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontWeight: 500, color: "var(--text-secondary)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)" }}>
          <Target size={12} /> Intrinsic: {fmtMoney(intrinsicValue)}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--text)" }}>
          Current: {fmtMoney(currentPrice)} <Activity size={12} />
        </span>
      </div>
    </div>
  );
}

export default function Valuation({ ticker }) {
  const { data, loading, error } = useFetch(fetchValuation, ticker);

  if (loading) return <LoadingSpinner label={`Loading valuation for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No valuation data available.</p>;

  const { dcf = {}, multiples = {}, finviz_data = {}, historical_financials = [], verdict } = data;

  const multipleRows = Object.entries(MULTIPLE_LABELS).map(([key, label]) => {
    const m = multiples[key] || {};
    return { id: key, metric: label, value: m.value, sector_avg: m.sector_avg, signal: m.signal };
  });

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Valuation — {ticker}</h1>

      <SectionCard title="Overall Verdict">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Scale size={18} color="var(--text-secondary)" />
          <SignalBadge signal={verdict} size="lg" />
        </div>
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="DCF Analysis">
          <StatRow label="Intrinsic Value" value={fmtMoney(dcf.intrinsic_value)} />
          <StatRow label="Current Price" value={fmtMoney(dcf.current_price)} />
          <StatRow label="Upside / Downside" value={fmtPct(dcf.upside_pct)} />
          <StatRow label="Margin of Safety" value={fmtPct(dcf.margin_of_safety)} />
          <StatRow label="WACC" value={fmtPctFraction(dcf.wacc)} />
          <StatRow label="FCF Growth Rate" value={fmtPctFraction(dcf.fcf_growth_rate)} />
          <PriceVsIntrinsicBar currentPrice={dcf.current_price} intrinsicValue={dcf.intrinsic_value} />
        </SectionCard>

        <SectionCard title="Finviz Data">
          <StatRow label="Analyst Target" value={fmtMoney(finviz_data.price_target)} />
          <StatRow label="Recommendation" value={fmtNum(finviz_data.analyst_recommendation)} />
          <StatRow label="Short Float %" value={finviz_data.short_float_pct != null ? `${fmtNum(finviz_data.short_float_pct)}%` : "—"} />
          <StatRow label="Insider Own %" value={finviz_data.insider_own_pct != null ? `${fmtNum(finviz_data.insider_own_pct)}%` : "—"} />
          <StatRow label="Institutional Own %" value={finviz_data.inst_own_pct != null ? `${fmtNum(finviz_data.inst_own_pct)}%` : "—"} />
        </SectionCard>
      </div>

      <SectionCard title="Relative Multiples">
        <DataTable
          columns={[
            { key: "metric", label: "Metric" },
            { key: "value", label: "Value", render: (v) => fmtNum(v) },
            { key: "sector_avg", label: "Sector Avg", render: (v) => (v != null ? fmtNum(v) : "—") },
            { key: "signal", label: "Signal", render: (v) => (v ? <SignalBadge signal={v} size="sm" /> : "—") },
          ]}
          rows={multipleRows}
        />
      </SectionCard>

      <SectionCard title="Historical Financials (5Y)">
        <DataTable
          columns={[
            { key: "year", label: "Year" },
            { key: "revenue", label: "Revenue ($M)", render: (v) => fmtNum(v, 0) },
            { key: "net_income", label: "Net Income ($M)", render: (v) => fmtNum(v, 0) },
            { key: "eps", label: "EPS", render: (v) => fmtNum(v) },
            { key: "ebitda", label: "EBITDA ($M)", render: (v) => fmtNum(v, 0) },
          ]}
          rows={historical_financials}
          emptyText="No historical financials scraped."
        />
      </SectionCard>
    </div>
  );
}
