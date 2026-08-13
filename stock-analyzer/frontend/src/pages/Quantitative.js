import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from "recharts";
import { Star } from "lucide-react";
import useFetch from "../hooks/useFetch";
import { fetchQuantitative } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import DataTable from "../components/DataTable";
import { fmtNum } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

const STRATEGY_LABELS = { buy_and_hold: "Buy & Hold", sma_crossover: "SMA Crossover", rsi_mean_reversion: "RSI Mean Reversion" };

export default function Quantitative({ ticker }) {
  const { data, loading, error } = useFetch(fetchQuantitative, ticker);

  if (loading) return <LoadingSpinner label={`Loading quantitative analysis for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No quantitative data available.</p>;

  const { factors = {}, monte_carlo = {}, backtesting = {}, statistics = {}, quant_signal } = data;

  const radarData = [
    { factor: "Momentum", score: factors.momentum?.score ?? 0 },
    { factor: "Quality", score: factors.quality?.score ?? 0 },
    { factor: "Value", score: factors.value?.score ?? 0 },
    { factor: "Growth", score: factors.growth?.score ?? 0 },
    { factor: "Low Vol", score: factors.low_volatility?.score ?? 0 },
  ];

  const samplePaths = monte_carlo.sample_paths || [];
  const numSteps = samplePaths[0]?.length || 0;
  const mcChartData = Array.from({ length: numSteps }, (_, step) => {
    const point = { step };
    samplePaths.forEach((path, i) => {
      point[`p${i}`] = path[step];
    });
    return point;
  });

  const strategyRows = Object.entries(STRATEGY_LABELS)
    .map(([key, label]) => ({ id: key, strategy: label, ...(backtesting[key] || {}), isBest: backtesting.best_strategy === key }));

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Quantitative Analysis — {ticker}</h1>

      <SectionCard title="Quant Signal">
        <SignalBadge signal={quant_signal} size="lg" />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Factor Scores">
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="factor" tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "var(--text-secondary)" }} />
              <Radar dataKey="score" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.4} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
            </RadarChart>
          </ResponsiveContainer>
        </SectionCard>

        <SectionCard title="Composite Score">
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: "16px 0" }}>
            <div>
              <span style={{ fontSize: 40, fontWeight: 700, color: "var(--accent)" }}>{fmtNum(factors.composite_score, 0)}</span>
              <span style={{ fontSize: 24, fontWeight: 700, color: "var(--accent)", opacity: 0.5 }}>/100</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <SignalBadge signal={factors.factor_rating} />
            </div>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Monte Carlo Simulation (20 sample paths)">
        {mcChartData.length > 0 && (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={mcChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="step" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)" }} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              {samplePaths.map((_, i) => (
                <Line key={i} type="monotone" dataKey={`p${i}`} stroke="var(--accent)" strokeOpacity={0.35} dot={false} strokeWidth={1} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginTop: 16 }}>
          <StatRow label="Prob. of Gain" value={monte_carlo.probability_of_gain != null ? `${fmtNum(monte_carlo.probability_of_gain, 0)}%` : "—"} />
          <StatRow label="Bull Case" value={monte_carlo.bull_case != null ? `$${fmtNum(monte_carlo.bull_case)}` : "—"} />
          <StatRow label="Base Case" value={monte_carlo.base_case != null ? `$${fmtNum(monte_carlo.base_case)}` : "—"} />
          <StatRow label="Bear Case" value={monte_carlo.bear_case != null ? `$${fmtNum(monte_carlo.bear_case)}` : "—"} />
        </div>
      </SectionCard>

      <SectionCard title="Backtesting Comparison">
        <DataTable
          columns={[
            {
              key: "strategy",
              label: "Strategy",
              render: (v, row) => (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  {row.isBest && <Star size={14} color="var(--yellow)" fill="var(--yellow)" />}
                  {v}
                </span>
              ),
            },
            { key: "total_return", label: "Total Return %", render: (v) => (v != null ? `${fmtNum(v)}%` : "—") },
            { key: "annualized_return", label: "Ann. Return %", render: (v) => (v != null ? `${fmtNum(v)}%` : "—") },
            { key: "max_drawdown", label: "Max Drawdown %", render: (v) => (v != null ? `${fmtNum(v)}%` : "—") },
            { key: "sharpe", label: "Sharpe", render: (v) => fmtNum(v) },
          ]}
          rows={strategyRows}
          rowStyle={(row) => (row.isBest ? { background: "rgba(234,179,8,0.08)" } : null)}
        />
      </SectionCard>

      <SectionCard title="Statistical Analysis">
        <StatRow label="Skewness" value={fmtNum(statistics.skewness, 3)} />
        <StatRow label="Kurtosis" value={fmtNum(statistics.kurtosis, 3)} />
        <StatRow label="Hurst Exponent" value={fmtNum(statistics.hurst_exponent, 3)} />
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 8 }}>{statistics.hurst_interpretation || "No interpretation available."}</p>
      </SectionCard>
    </div>
  );
}
