import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, TrendingUp, TrendingDown } from "lucide-react";
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchPrice, fetchFundamental, fetchTechnical, fetchCalendar, fetchFundamentals } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import MetricCard from "../components/MetricCard";
import SignalBadge from "../components/SignalBadge";
import SectionCard from "../components/SectionCard";
import ChartTooltip from "../components/ChartTooltip";
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
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 16, fontWeight: 600, color: change >= 0 ? "var(--green)" : "var(--red)" }}>
            {change >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
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
        <SectionCard
          title="Price History (Close, SMA20, SMA50)"
          right={
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                <span style={{ width: 9, height: 9, borderRadius: 2, background: "var(--accent)" }} /> Close
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                <span style={{ width: 9, height: 2, background: "var(--green)" }} /> SMA20
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                <span style={{ width: 9, height: 2, background: "var(--yellow)" }} /> SMA50
              </span>
            </div>
          }
        >
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="closeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
              <XAxis dataKey="date" minTickGap={40} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} dy={8} />
              <YAxis domain={["auto", "auto"]} axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} dx={-8} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--text-secondary)", strokeWidth: 1, strokeDasharray: "4 4" }} />
              <Area type="monotone" dataKey="Close" name="Close" stroke="var(--accent)" strokeWidth={2.5} fill="url(#closeGradient)" activeDot={{ r: 5, strokeWidth: 0 }} />
              <Line type="monotone" dataKey="SMA20" name="SMA20" stroke="var(--green)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
              <Line type="monotone" dataKey="SMA50" name="SMA50" stroke="var(--yellow)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </SectionCard>
      )}

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        <SectionCard title="Fundamental Health">
          <div style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: healthColor === "green" ? "var(--green)" : healthColor === "yellow" ? "var(--yellow)" : healthColor === "red" ? "var(--red)" : "var(--text)" }}>
              {healthScore != null ? healthScore : "—"}
            </span>
            {healthScore != null && (
              <span style={{ fontSize: 18, fontWeight: 700, opacity: 0.5, color: healthColor === "green" ? "var(--green)" : healthColor === "yellow" ? "var(--yellow)" : healthColor === "red" ? "var(--red)" : "var(--text)" }}>
                /100
              </span>
            )}
          </div>
          <Link to="/fundamental" className="detail-link">View details <ArrowRight size={16} /></Link>
        </SectionCard>

        <SectionCard title="Technical Signal">
          <div style={{ marginBottom: 8 }}>
            <SignalBadge signal={overallSignal} size="lg" />
          </div>
          <Link to="/technical" className="detail-link">View details <ArrowRight size={16} /></Link>
        </SectionCard>

        <SectionCard title="Next Event">
          <div style={{ fontSize: 14, color: nextAlert ? "var(--text)" : "var(--text-secondary)", marginBottom: 8 }}>
            {nextAlert || "No urgent events flagged"}
          </div>
          <Link to="/calendar" className="detail-link">View calendar <ArrowRight size={16} /></Link>
        </SectionCard>
      </div>
    </div>
  );
}
