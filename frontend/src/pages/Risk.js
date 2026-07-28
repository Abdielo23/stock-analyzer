import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchRisk } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import { fmtNum, clamp } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function RiskGauge({ score }) {
  const pct = clamp(score ?? 0, 0, 100);
  const color = pct >= 70 ? "var(--red)" : pct >= 40 ? "var(--yellow)" : "var(--green)";
  return (
    <div>
      <div style={{ height: 18, borderRadius: 999, background: "var(--bg)", overflow: "hidden", marginBottom: 8 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, transition: "width 0.3s" }} />
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{score != null ? `${fmtNum(score, 0)}/100` : "—"}</div>
    </div>
  );
}

const CORR_ASSETS = ["SPY", "QQQ", "GLD", "TLT", "BTC-USD"];

export default function Risk({ ticker }) {
  const { data, loading, error } = useFetch(fetchRisk, ticker);

  if (loading) return <LoadingSpinner label={`Loading risk analysis for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No risk data available.</p>;

  const { ratios = {}, drawdown = {}, var: varData = {}, volatility = {}, correlations = {}, risk_score, risk_label } = data;

  const drawdownChart = (drawdown.drawdown_series || []).map((row) => ({
    date: row.date,
    Drawdown: row.drawdown,
  }));

  const vol20 = volatility.rolling_vol_20 || [];
  const vol60 = volatility.rolling_vol_60 || [];
  const volChart = vol20.map((row, i) => ({
    date: row.date,
    Vol20: row.volatility,
    Vol60: vol60[i]?.volatility,
  }));

  const matrix = correlations.matrix || {};
  const rowKey = ticker.toUpperCase();

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Risk Analysis — {ticker}</h1>

      <SectionCard title={`Risk Score${risk_label ? ` — ${risk_label}` : ""}`}>
        <RiskGauge score={risk_score} />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Key Ratios">
          <StatRow label="Sharpe Ratio" value={fmtNum(ratios.sharpe_ratio)} />
          <StatRow label="Sortino Ratio" value={fmtNum(ratios.sortino_ratio)} />
          <StatRow label="Beta" value={fmtNum(ratios.beta)} />
          <StatRow label="Alpha" value={ratios.alpha != null ? `${fmtNum(ratios.alpha)}%` : "—"} />
          <StatRow label="Treynor Ratio" value={fmtNum(ratios.treynor_ratio)} />
          <StatRow label="Calmar Ratio" value={fmtNum(ratios.calmar_ratio)} />
        </SectionCard>

        <SectionCard title="VaR / CVaR Analysis">
          <StatRow label="Historical VaR (95%)" value={varData.historical_var_95 != null ? `${fmtNum(varData.historical_var_95)}%` : "—"} />
          <StatRow label="Historical VaR (99%)" value={varData.historical_var_99 != null ? `${fmtNum(varData.historical_var_99)}%` : "—"} />
          <StatRow label="CVaR (95%)" value={varData.cvar_95 != null ? `${fmtNum(varData.cvar_95)}%` : "—"} />
          <StatRow label="CVaR (99%)" value={varData.cvar_99 != null ? `${fmtNum(varData.cvar_99)}%` : "—"} />
          {varData.interpretation && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--text-secondary)" }}>{varData.interpretation}</p>
          )}
        </SectionCard>
      </div>

      {drawdownChart.length > 0 && (
        <SectionCard title={`Drawdown (max: ${fmtNum(drawdown.max_drawdown)}%)`}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={drawdownChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Line type="monotone" dataKey="Drawdown" stroke="var(--red)" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {volChart.length > 0 && (
        <SectionCard title="Rolling Volatility (20d / 60d, annualized %)">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={volChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Legend />
              <Line type="monotone" dataKey="Vol20" stroke="var(--accent)" dot={false} strokeWidth={1.5} name="20d Vol" />
              <Line type="monotone" dataKey="Vol60" stroke="var(--yellow)" dot={false} strokeWidth={1.5} name="60d Vol" />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      <SectionCard title="Correlation Matrix">
        {matrix[rowKey] ? (
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {CORR_ASSETS.map((asset) => (
              <div key={asset} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>{ticker} vs {asset}</div>
                <div style={{ fontSize: 20, fontWeight: 700 }}>{fmtNum(matrix[rowKey]?.[asset])}</div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No correlation data available.</p>
        )}
      </SectionCard>
    </div>
  );
}
