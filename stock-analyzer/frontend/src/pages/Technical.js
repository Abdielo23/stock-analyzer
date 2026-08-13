import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchTechnical } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import { fmtNum } from "../utils/format";

function IndicatorCard({ label, value, signal }) {
  return (
    <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>{value}</div>
      {signal && <SignalBadge signal={signal} size="sm" />}
    </div>
  );
}

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function cciSignal(cci) {
  if (cci == null) return null;
  if (cci > 100) return "overbought";
  if (cci < -100) return "oversold";
  return "neutral";
}

function williamsSignal(wr) {
  if (wr == null) return null;
  if (wr > -20) return "overbought";
  if (wr < -80) return "oversold";
  return "neutral";
}

export default function Technical({ ticker }) {
  const { data, loading, error } = useFetch(fetchTechnical, ticker);

  if (loading) return <LoadingSpinner label={`Loading technical analysis for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No technical data available.</p>;

  const { trend = {}, momentum = {}, support_resistance = {}, price_history = [], overall_signal } = data;
  const { rsi = {}, macd = {}, stochastic = {}, williams_r, cci, atr, bollinger_bands = {} } = momentum;

  const chartData = price_history.map((row) => ({
    date: row.date,
    Close: row.Close,
    SMA20: row.SMA20,
    SMA50: row.SMA50,
    EMA12: row.EMA12,
    BB_upper: row.BB_upper,
    BB_lower: row.BB_lower,
  }));

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Technical Analysis — {ticker}</h1>

      {chartData.length > 0 && (
        <SectionCard title="Price Chart (SMA20, SMA50, EMA12, Bollinger Bands)">
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Legend />
              <Line type="monotone" dataKey="Close" stroke="var(--accent)" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="SMA20" stroke="var(--green)" dot={false} strokeWidth={1.2} />
              <Line type="monotone" dataKey="SMA50" stroke="var(--yellow)" dot={false} strokeWidth={1.2} />
              <Line type="monotone" dataKey="EMA12" stroke="#a855f7" dot={false} strokeWidth={1.2} />
              <Line type="monotone" dataKey="BB_upper" stroke="var(--text-secondary)" dot={false} strokeWidth={1} strokeDasharray="4 4" />
              <Line type="monotone" dataKey="BB_lower" stroke="var(--text-secondary)" dot={false} strokeWidth={1} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      <SectionCard title="Indicators">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
          <IndicatorCard label="RSI (14)" value={fmtNum(rsi.value)} signal={rsi.signal} />
          <IndicatorCard label="MACD" value={fmtNum(macd.histogram, 3)} signal={macd.signal} />
          <IndicatorCard label="Stochastic %K" value={fmtNum(stochastic.percent_k)} signal={stochastic.signal} />
          <IndicatorCard label="Williams %R" value={fmtNum(williams_r)} signal={williamsSignal(williams_r)} />
          <IndicatorCard label="CCI" value={fmtNum(cci)} signal={cciSignal(cci)} />
          <IndicatorCard label="ATR" value={fmtNum(atr)} />
          <IndicatorCard label="ADX" value={fmtNum(trend.adx)} signal={trend.adx_trend} />
          <IndicatorCard label="Bollinger %B" value={fmtNum(bollinger_bands.percent_b)} signal={bollinger_bands.signal} />
        </div>
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Trend">
          <StatRow label="Price vs SMA20" value={trend.price_vs_sma20 || "—"} />
          <StatRow label="Price vs SMA50" value={trend.price_vs_sma50 || "—"} />
          <StatRow label="Price vs SMA200" value={trend.price_vs_sma200 || "—"} />
          <StatRow label="Golden Cross (5d)" value={trend.golden_cross ? "Yes" : "No"} />
          <StatRow label="Death Cross (5d)" value={trend.death_cross ? "Yes" : "No"} />
          <StatRow label="Ichimoku Signal" value={trend.ichimoku_signal || "—"} />
          <StatRow label="ADX Trend Strength" value={trend.adx_trend || "—"} />
        </SectionCard>

        <SectionCard title="Support & Resistance">
          <StatRow label="Pivot Point (PP)" value={fmtNum(support_resistance.pivot_point)} />
          <StatRow label="Resistance 1 (R1)" value={fmtNum(support_resistance.r1)} />
          <StatRow label="Resistance 2 (R2)" value={fmtNum(support_resistance.r2)} />
          <StatRow label="Resistance 3 (R3)" value={fmtNum(support_resistance.r3)} />
          <StatRow label="Support 1 (S1)" value={fmtNum(support_resistance.s1)} />
          <StatRow label="Support 2 (S2)" value={fmtNum(support_resistance.s2)} />
          <StatRow label="Support 3 (S3)" value={fmtNum(support_resistance.s3)} />
        </SectionCard>
      </div>

      <SectionCard title="Overall Technical Signal">
        <SignalBadge signal={overall_signal} size="lg" />
      </SectionCard>
    </div>
  );
}
