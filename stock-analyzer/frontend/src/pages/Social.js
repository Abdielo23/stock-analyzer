import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import useFetch from "../hooks/useFetch";
import { fetchSocial } from "../api/stockApi";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionCard from "../components/SectionCard";
import DataTable from "../components/DataTable";
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

function NotConfigured({ ticker, instructions }) {
  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Social Sentiment — {ticker}</h1>
      <SectionCard title="REDDIT NOT CONNECTED">
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 10 }}>
          Reddit requires free API credentials to fetch live data. Reddit needs to verify who is making requests
          to protect their platform from abuse. Your credentials are private and only used to read public posts.
        </p>
        <ol style={{ paddingLeft: 20, lineHeight: 1.9, fontSize: 14 }}>
          {Object.values(instructions || {}).map((step, i) => <li key={i}>{step}</li>)}
        </ol>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 10 }}>
          Once connected, this page shows live mentions across r/wallstreetbets, r/investing, r/stocks and
          r/SecurityAnalysis with VADER sentiment scoring on every post.
        </p>
      </SectionCard>

      <SectionCard title="TWITTER/X">
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 10 }}>
          Real-time X/Twitter sentiment using cashtags. Requires X API v2 access (paid, starts at $100/month).
        </p>
        <ol style={{ paddingLeft: 20, lineHeight: 1.9, fontSize: 14 }}>
          <li>Go to developer.x.com and create a developer account</li>
          <li>Create a new project and app in the developer portal</li>
          <li>Apply for Basic tier access ($100/month) or higher</li>
          <li>Copy your API Key, API Secret, Bearer Token</li>
          <li>Add to backend/.env: TWITTER_API_KEY=your_key_here</li>
          <li>In backend/analysis/social.py implement get_twitter_mentions() using the tweepy library</li>
          <li>Add GET /stock/{"{ticker}"}/twitter endpoint to main.py</li>
          <li>Restart the backend server</li>
        </ol>
        <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)", marginTop: 10 }}>
          <li>Live cashtag feed via X API v2</li>
          <li>Sentiment analysis on tweets with VADER</li>
          <li>Key financial accounts monitoring</li>
          <li>Tweet volume trends over time</li>
        </ul>
      </SectionCard>

      <SectionCard title="YOUTUBE">
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 10 }}>
          YouTube financial video analysis for the ticker. Requires a free Google API key (10,000 requests/day free tier).
        </p>
        <ol style={{ paddingLeft: 20, lineHeight: 1.9, fontSize: 14 }}>
          <li>Go to console.cloud.google.com and sign in</li>
          <li>Create a new project (or use existing one)</li>
          <li>Click "Enable APIs and Services"</li>
          <li>Search for "YouTube Data API v3" and enable it</li>
          <li>Go to "Credentials" and click "Create Credentials"</li>
          <li>Select "API Key" and copy the generated key</li>
          <li>Add to backend/.env: YOUTUBE_API_KEY=your_key_here</li>
          <li>Restart the backend server — YouTube data will appear automatically on this page</li>
        </ol>
        <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)", marginTop: 10 }}>
          <li>Latest videos from top financial YouTubers</li>
          <li>View count and engagement metrics</li>
          <li>Title sentiment analysis via VADER</li>
          <li>Filtered by trusted channels: Graham Stephan, Meet Kevin, ZipTrader, Andrei Jikh, InvestAnswers</li>
        </ul>
      </SectionCard>
    </div>
  );
}

export default function Social({ ticker }) {
  const { data, loading, error } = useFetch(fetchSocial, ticker);

  if (loading) return <LoadingSpinner label={`Loading social sentiment for ${ticker}...`} />;
  if (error) return <p style={{ color: "var(--red)" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--red)" }}>No social data available.</p>;

  if (data.error) {
    return <NotConfigured ticker={ticker} instructions={data.instructions} />;
  }

  const { reddit = {}, wsb = {}, mention_trend: trend = {}, social_signal } = data;
  const mentions = reddit.mentions || {};
  const sentiment = reddit.sentiment || {};

  const subredditChart = Object.entries(mentions.mentions_by_subreddit || {}).map(([sub, count]) => ({ sub, count }));
  const dailyChart = Object.entries(trend.daily_mentions || {}).map(([date, count]) => ({ date, count }));

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Social Sentiment — {ticker}</h1>

      <SectionCard title="Social Signal">
        <SignalBadge signal={social_signal} size="lg" />
      </SectionCard>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
        <MetricCard label="Total Mentions" value={mentions.total_mentions ?? "—"} />
        <MetricCard label="Reddit Sentiment" value={sentiment.overall_reddit_sentiment || "—"} />
        <MetricCard label="Trending?" value={trend.is_trending ? "Yes" : "No"} sub={trend.trend_direction} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18 }}>
        <SectionCard title="Mentions by Subreddit">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={subredditChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="sub" tick={{ fontSize: 10, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)" }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        <SectionCard title="Daily Mentions (7d)">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dailyChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-secondary)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)" }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
              <Bar dataKey="count" fill="var(--yellow)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      <SectionCard title="WallStreetBets Signals">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
          <StatRow label="🚀 Rocket Mentions" value={wsb.wsb_signals?.rocket_count ?? "—"} />
          <StatRow label="YOLO Mentions" value={wsb.wsb_signals?.yolo_mentions ?? "—"} />
          <StatRow label="Loss Porn" value={wsb.wsb_signals?.loss_porn ?? "—"} />
          <StatRow label="DD Posts" value={wsb.dd_posts?.length ?? 0} />
        </div>
        <p style={{ marginTop: 12, fontSize: 13, color: "var(--text-secondary)" }}>
          WSB Sentiment: <SignalBadge signal={wsb.wsb_sentiment?.overall_sentiment} size="sm" />
        </p>
      </SectionCard>

      <SectionCard title="Recent Reddit Posts">
        <DataTable
          columns={[
            { key: "subreddit", label: "Subreddit" },
            { key: "title", label: "Title", render: (v, row) => (row.url ? <a href={row.url} target="_blank" rel="noreferrer" style={{ color: "var(--text)" }}>{v}</a> : v) },
            { key: "score", label: "Upvotes", render: (v) => fmtNum(v, 0) },
            { key: "sentiment_label", label: "Sentiment", render: (v) => (v ? <SignalBadge signal={v} size="sm" /> : "—") },
          ]}
          rows={sentiment.posts}
          emptyText="No Reddit posts found."
        />
      </SectionCard>
    </div>
  );
}
