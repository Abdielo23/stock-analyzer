import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchMacro } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import MetricCard from "../components/MetricCard";
import { fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

const MATURITY_ORDER = ["1M", "3M", "1Y", "2Y", "5Y", "10Y", "30Y"];

export default function Macro({ ticker }) {
  const { data, loading, error } = useFetch(fetchMacro, ticker);

  if (loading) return <LoadingSpinner label={`Loading macro analysis for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No macro data available.</p>;

  const { yield_curve = {}, credit_markets = {}, commodities = {}, supply_chain = {}, liquidity = {}, sector_rotation = {}, macro_signal } = data;

  const curveData = MATURITY_ORDER
    .map((m) => ({ maturity: m, yield: yield_curve.yields_by_maturity?.[m] }))
    .filter((d) => d.yield != null);

  const curveColor = yield_curve.curve_shape === "inverted" ? "var(--red)" : "var(--green)";
  const commodityList = Object.entries(commodities.commodities || {});
  const rankings = sector_rotation.sector_rankings_1m || [];

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Macro & Supply Chain — {ticker}</h1>

      <SectionCard title="Macro Signal">
        <SignalBadge signal={macro_signal} size="lg" />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title={`Yield Curve — ${yield_curve.curve_shape || "—"}`}>
          {curveData.length > 0 && (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={curveData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="maturity" tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
                <YAxis tick={{ fontSize: 12, fill: "var(--text-secondary)" }} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => `${fmtNum(v)}%`} />
                <Line type="monotone" dataKey="yield" stroke={curveColor} strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
          <StatRow label="2s10s Spread" value={yield_curve.spreads?.["2s10s"] != null ? `${fmtNum(yield_curve.spreads["2s10s"])}%` : "—"} />
        </SectionCard>

        <SectionCard title="Recession Probability">
          <div style={{ fontSize: 40, fontWeight: 700, color: curveColor }}>{yield_curve.recession_probability || "—"}</div>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 8 }}>Based on 2s10s yield curve shape: {yield_curve.curve_shape || "—"}</p>
        </SectionCard>
      </div>

      <SectionCard title="Credit Markets" right={credit_markets.credit_signal ? <SignalBadge signal={credit_markets.credit_signal} size="sm" /> : null}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          <MetricCard label="HYG" value={fmtNum(credit_markets.hyg_performance?.price)} sub={credit_markets.hyg_performance?.change_30d_pct != null ? `${fmtNum(credit_markets.hyg_performance.change_30d_pct)}% (30d)` : "—"} />
          <MetricCard label="LQD" value={fmtNum(credit_markets.lqd_performance?.price)} sub={credit_markets.lqd_performance?.change_30d_pct != null ? `${fmtNum(credit_markets.lqd_performance.change_30d_pct)}% (30d)` : "—"} />
          <MetricCard label="TLT" value={fmtNum(credit_markets.tlt_performance?.price)} sub={credit_markets.tlt_performance?.change_30d_pct != null ? `${fmtNum(credit_markets.tlt_performance.change_30d_pct)}% (30d)` : "—"} />
        </div>
      </SectionCard>

      <SectionCard title="Commodities">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          {commodityList.map(([symbol, c]) => (
            <MetricCard
              key={symbol}
              label={c.name}
              value={c.current_price != null ? fmtNum(c.current_price) : "—"}
              sub={c.change_1m_pct != null ? `1M: ${c.change_1m_pct >= 0 ? "+" : ""}${fmtNum(c.change_1m_pct)}%` : "—"}
              color={c.change_1m_pct == null ? "neutral" : c.change_1m_pct >= 0 ? "green" : "red"}
            />
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Supply Chain" right={supply_chain.risk_label ? <SignalBadge signal={supply_chain.risk_label} size="sm" /> : null}>
        <StatRow label="Supply Chain Risk Score" value={`${fmtNum(supply_chain.supply_chain_risk_score, 0)}/100`} />
        <StatRow label="Shipping Proxy (BDRY)" value={supply_chain.shipping_proxy?.price != null ? fmtNum(supply_chain.shipping_proxy.price) : "—"} />
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 8 }}>{supply_chain.baltic_dry_note}</p>
      </SectionCard>

      <SectionCard title="Global Liquidity" right={liquidity.liquidity_signal ? <SignalBadge signal={liquidity.liquidity_signal} size="sm" /> : null}>
        <StatRow label="M2 YoY Growth" value={liquidity.m2_yoy_growth != null ? `${fmtNum(liquidity.m2_yoy_growth)}%` : "—"} />
        <StatRow label="Fed Balance Sheet Trend" value={liquidity.fed_balance_sheet_trend || "—"} />
        <StatRow label="Equity Market Impact" value={liquidity.equity_market_impact || "—"} />
      </SectionCard>

      <SectionCard title={`Sector Rotation — ${sector_rotation.market_cycle_phase || "—"}`}>
        {rankings.map((s) => (
          <div key={s.sector} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--row-border)", fontSize: 13 }}>
            <span>#{s.rank_1m} {s.sector}</span>
            <span style={{ color: s.return_1m >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{s.return_1m >= 0 ? "+" : ""}{fmtNum(s.return_1m)}%</span>
          </div>
        ))}
      </SectionCard>
    </div>
  );
}
