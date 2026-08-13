import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchSentiment } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import SignalBadge from "../components/SignalBadge";
import MetricCard from "../components/MetricCard";
import { fmtNum, clamp } from "../utils/format";

function StatRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--row-border)", fontSize: 14 }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function FearGreedGauge({ score, rating }) {
  const pct = clamp(score ?? 50, 0, 100);
  const color = pct >= 55 ? "var(--green)" : pct <= 45 ? "var(--red)" : "var(--yellow)";
  return (
    <div>
      <div style={{ height: 18, borderRadius: 999, background: "var(--bg)", overflow: "hidden", marginBottom: 8 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color }} />
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{score != null ? fmtNum(score, 0) : "—"} {rating && <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>({rating})</span>}</div>
    </div>
  );
}

const RATING_COLORS = { strong_buy: "#16a34a", buy: "var(--green)", hold: "var(--yellow)", underperform: "#f97316", sell: "var(--red)" };

export default function Sentiment({ ticker }) {
  const { data, loading, error } = useFetch(fetchSentiment, ticker);

  if (loading) return <LoadingSpinner label={`Loading sentiment for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No sentiment data available.</p>;

  const { fear_greed = {}, vix = {}, analyst_ratings = {}, news_sentiment = {}, sector_performance = {}, macro = {}, overall_sentiment_signal } = data;

  const donutData = Object.entries(analyst_ratings.ratings_breakdown || {}).map(([key, value]) => ({
    name: key.replace(/_/g, " "),
    key,
    value,
  })).filter((d) => d.value > 0);

  const sectorData = (sector_performance.sector_returns || []).map((s) => ({
    sector: s.sector,
    return: s.one_month_return,
  }));

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Market Sentiment — {ticker}</h1>

      <SectionCard title="Overall Sentiment Signal">
        <SignalBadge signal={overall_sentiment_signal} size="lg" />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Fear & Greed Index">
          <FearGreedGauge score={fear_greed.score} rating={fear_greed.rating} />
        </SectionCard>

        <SectionCard title="VIX Analysis">
          <StatRow label="Current VIX" value={fmtNum(vix.current_vix)} />
          <StatRow label="20d Average" value={fmtNum(vix.vix_avg_20d)} />
          <StatRow label="Regime" value={vix.vix_regime || "—"} />
          <StatRow label="Term Structure" value={vix.term_structure || "—"} />
        </SectionCard>
      </div>

      <SectionCard title="Analyst Ratings">
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
          {donutData.length > 0 && (
            <ResponsiveContainer width={220} height={220}>
              <PieChart>
                <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={90} paddingAngle={2}>
                  {donutData.map((d) => (
                    <Cell key={d.key} fill={RATING_COLORS[d.key] || "var(--text-secondary)"} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
          <div>
            <StatRow label="Consensus" value={analyst_ratings.consensus_label || "—"} />
            <StatRow label="Consensus Score" value={fmtNum(analyst_ratings.consensus_score)} />
            <StatRow label="Mean Target" value={analyst_ratings.price_targets?.mean_target != null ? `$${fmtNum(analyst_ratings.price_targets.mean_target)}` : "—"} />
            <StatRow label="Upside from Current" value={analyst_ratings.price_targets?.upside_from_current != null ? `${fmtNum(analyst_ratings.price_targets.upside_from_current)}%` : "—"} />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="News Sentiment" right={news_sentiment.sentiment_label ? <SignalBadge signal={news_sentiment.sentiment_label} size="sm" /> : null}>
        {(news_sentiment.articles || []).slice(0, 8).map((a, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--row-border)" }}>
            <a href={a.link} target="_blank" rel="noreferrer" style={{ color: "var(--text)", fontSize: 13, textDecoration: "none", flex: 1 }}>{a.title}</a>
            <SignalBadge signal={a.sentiment_score > 0.1 ? "positive" : a.sentiment_score < -0.1 ? "negative" : "neutral"} size="sm" />
          </div>
        ))}
        {(!news_sentiment.articles || news_sentiment.articles.length === 0) && <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>No recent news articles.</p>}
      </SectionCard>

      {sectorData.length > 0 && (
        <SectionCard title="Sector Performance (1M return %, ranked)">
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={sectorData} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis type="number" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
              <YAxis type="category" dataKey="sector" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} width={140} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} formatter={(v) => `${fmtNum(v)}%`} />
              <Bar dataKey="return">
                {sectorData.map((d, i) => (
                  <Cell key={i} fill={d.return >= 0 ? "var(--green)" : "var(--red)"} />
                ))}
                <LabelList dataKey="return" position="right" formatter={(v) => `${fmtNum(v)}%`} fill="var(--text-secondary)" fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      <SectionCard title="Macro Indicators">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          <MetricCard label="Yield Curve" value={macro.yield_curve_signal || "—"} />
          <MetricCard label="Inflation" value={macro.inflation_signal || "—"} />
          <MetricCard label="Fed Policy" value={macro.fed_signal || "—"} />
        </div>
      </SectionCard>
    </div>
  );
}
