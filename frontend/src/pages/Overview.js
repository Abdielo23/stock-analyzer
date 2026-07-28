import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { fetchPrice, fetchFundamental, fetchTechnical, fetchCalendar, fetchFundamentals } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import MetricCard from "../components/MetricCard";
import SignalBadge from "../components/SignalBadge";
import SectionCard from "../components/SectionCard";
import { fmtLarge, fmtNum } from "../utils/format";

export default function Overview({ ticker }) {
  const [state, setState] = useState({ loading: true, error: null, price: null, fundamental: null, technical: null, calendar: null, quote: null });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    Promise.allSettled([
      fetchPrice(ticker, "1y"),
      fetchFundamental(ticker),
      fetchTechnical(ticker, "1y"),
      fetchCalendar(ticker),
      fetchFundamentals(ticker),
    ]).then(([priceRes, fundamentalRes, technicalRes, calendarRes, quoteRes]) => {
      if (cancelled) return;
      const allFailed = [priceRes, fundamentalRes, technicalRes, calendarRes, quoteRes].every((r) => r.status === "rejected");
      setState({
        loading: false,
        error: allFailed ? "Could not reach the backend. Is it running on localhost:8000?" : null,
        price: priceRes.status === "fulfilled" ? priceRes.value : null,
        fundamental: fundamentalRes.status === "fulfilled" ? fundamentalRes.value : null,
        technical: technicalRes.status === "fulfilled" ? technicalRes.value : null,
        calendar: calendarRes.status === "fulfilled" ? calendarRes.value : null,
        quote: quoteRes.status === "fulfilled" ? quoteRes.value : null,
      });
    });

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const { loading, error, price, fundamental, technical, calendar, quote } = state;

  if (loading) return <LoadingSpinner label={`Loading ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>{error}</p>;

  const closes = (price || []).map((row) => row.Close).filter((v) => v != null);
  const currentPrice = closes.length ? closes[closes.length - 1] : null;
  const previousClose = closes.length > 1 ? closes[closes.length - 2] : null;
  const change = currentPrice != null && previousClose != null ? currentPrice - previousClose : null;
  const changePct = change != null && previousClose ? (change / previousClose) * 100 : null;
  const week52High = closes.length ? Math.max(...closes) : null;
  const week52Low = closes.length ? Math.min(...closes) : null;
  const changeColor = change == null ? "neutral" : change >= 0 ? "green" : "red";

  const techPriceHistory = technical?.price_history || [];
  const smaByDate = {};
  techPriceHistory.forEach((row) => {
    smaByDate[row.date] = { sma20: row.SMA20, sma50: row.SMA50 };
  });

  const last100 = (price || []).slice(-100);
  const chartData = last100.map((row) => {
    const date = row.date ? String(row.date).slice(0, 10) : "";
    return {
      date,
      Close: row.Close,
      SMA20: smaByDate[date]?.sma20 ?? null,
      SMA50: smaByDate[date]?.sma50 ?? null,
    };
  });

  const healthScore = fundamental?.health_score;
  const healthColor = healthScore == null ? "neutral" : healthScore >= 70 ? "green" : healthScore >= 50 ? "yellow" : "red";
  const overallSignal = technical?.overall_signal;
  const nextAlert = calendar?.alerts?.[0] || null;

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* Stock header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
        <h1 style={{ fontSize: 26, margin: 0 }}>{quote?.name || ticker}</h1>
        <span style={{ color: "var(--text-secondary)", fontSize: 16 }}>{ticker}</span>
        <span style={{ fontSize: 26, fontWeight: 700 }}>{currentPrice != null ? `$${currentPrice.toFixed(2)}` : "—"}</span>
        {change != null && (
          <span style={{ fontSize: 16, fontWeight: 600, color: change >= 0 ? "var(--green)" : "var(--red)" }}>
            {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
          </span>
        )}
      </div>

      {/* Metrics row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
        <MetricCard label="Market Cap" value={fmtLarge(quote?.market_cap)} />
        <MetricCard label="P/E (trailing)" value={fmtNum(quote?.pe?.trailing)} />
        <MetricCard label="EPS (trailing)" value={fmtNum(quote?.eps?.trailing)} />
        <MetricCard label="Beta" value={fmtNum(quote?.beta)} />
        <MetricCard label="52W High" value={week52High != null ? `$${week52High.toFixed(2)}` : "—"} />
        <MetricCard label="52W Low" value={week52Low != null ? `$${week52Low.toFixed(2)}` : "—"} />
      </div>

      {/* Price chart */}
      {chartData.length > 0 && (
        <SectionCard title="Price History (Close, SMA20, SMA50)">
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Legend />
              <Line type="monotone" dataKey="Close" stroke="var(--accent)" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="SMA20" stroke="var(--green)" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="SMA50" stroke="var(--yellow)" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        <SectionCard title="Fundamental Health">
          <div style={{ fontSize: 28, fontWeight: 700, color: healthColor === "green" ? "var(--green)" : healthColor === "yellow" ? "var(--yellow)" : healthColor === "red" ? "var(--red)" : "var(--text)" }}>
            {healthScore != null ? `${healthScore}/100` : "—"}
          </div>
          <Link to="/fundamental" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>View details →</Link>
        </SectionCard>

        <SectionCard title="Technical Signal">
          <div style={{ marginBottom: 8 }}>
            <SignalBadge signal={overallSignal} size="lg" />
          </div>
          <Link to="/technical" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>View details →</Link>
        </SectionCard>

        <SectionCard title="Next Event">
          <div style={{ fontSize: 14, color: nextAlert ? "var(--text)" : "var(--text-secondary)", marginBottom: 8 }}>
            {nextAlert || "No urgent events flagged"}
          </div>
          <Link to="/calendar" style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none" }}>View calendar →</Link>
        </SectionCard>
      </div>
    </div>
  );
}
