import { useEffect, useState } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { fetchVolume, fetchPrice } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import MetricCard from "../components/MetricCard";
import { fmtNum, fmtCompactNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export default function Volume({ ticker }) {
  const [state, setState] = useState({ loading: true, error: null, volume: null, price: null });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    Promise.allSettled([fetchVolume(ticker, "1y"), fetchPrice(ticker, "1y")]).then(([volRes, priceRes]) => {
      if (cancelled) return;
      setState({
        loading: false,
        error: volRes.status === "rejected" ? (volRes.reason?.message || "Failed to load volume data") : null,
        volume: volRes.status === "fulfilled" ? volRes.value : null,
        price: priceRes.status === "fulfilled" ? priceRes.value : null,
      });
    });

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const { loading, error, volume, price } = state;

  if (loading) return <LoadingSpinner label={`Loading volume analysis for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!volume) return <p style={{ color: "var(--red)" }}>No volume data available.</p>;

  const { obv = {}, chaikin_money_flow = {}, volume_profile = {}, vwap = {}, relative_volume = {}, overall_flow_signal } = volume;

  const volumeChartData = (price || []).slice(-100).map((row) => ({
    date: row.date ? String(row.date).slice(0, 10) : "",
    Volume: row.Volume,
  }));

  const obvChartData = (obv.obv_history || []).map((row) => ({
    date: row.date,
    OBV: row.OBV,
  }));

  const profileBuckets = (volume_profile.volume_buckets || []).map((b) => ({
    price: b.price_level != null ? b.price_level.toFixed(2) : "—",
    volume: b.volume,
    isPoc: b.is_poc,
  }));

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Volume & Flow — {ticker}</h1>

      {volumeChartData.length > 0 && (
        <SectionCard title="Volume (last 100 days)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={volumeChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis tickFormatter={fmtCompactNum} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => fmtCompactNum(v)} />
              <Bar dataKey="Volume" fill="var(--accent)" />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {obvChartData.length > 0 && (
        <SectionCard title="On Balance Volume (OBV)" right={obv.obv_signal ? <SignalBadge signal={obv.obv_signal} size="sm" /> : null}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={obvChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis tickFormatter={fmtCompactNum} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => fmtCompactNum(v)} />
              <Line type="monotone" dataKey="OBV" stroke="var(--green)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
        <MetricCard label="Chaikin Money Flow" value={fmtNum(chaikin_money_flow.cmf_value, 3)} sub={chaikin_money_flow.cmf_signal} />
        <MetricCard label="Relative Volume" value={relative_volume.rvol != null ? `${fmtNum(relative_volume.rvol)}x` : "—"} sub={relative_volume.signal} />
        <MetricCard label="VWAP Distance" value={vwap.distance_pct != null ? `${fmtNum(vwap.distance_pct)}%` : "—"} sub={vwap.signal} />
      </div>

      {profileBuckets.length > 0 && (
        <SectionCard title="Volume Profile (POC highlighted)">
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={profileBuckets} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis type="number" tickFormatter={fmtCompactNum} tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
              <YAxis type="category" dataKey="price" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} width={70} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => fmtCompactNum(v)} />
              <Bar dataKey="volume">
                {profileBuckets.map((entry, i) => (
                  <Cell key={i} fill={entry.isPoc ? "var(--yellow)" : "var(--accent)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <StatRow label="Point of Control (POC)" value={fmtNum(volume_profile.poc_price)} />
          <StatRow label="Value Area High (VAH)" value={fmtNum(volume_profile.vah)} />
          <StatRow label="Value Area Low (VAL)" value={fmtNum(volume_profile.val)} />
        </SectionCard>
      )}

      <SectionCard title="Overall Flow Signal">
        <SignalBadge signal={overall_flow_signal} size="lg" />
      </SectionCard>
    </div>
  );
}
