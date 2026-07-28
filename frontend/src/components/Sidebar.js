import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview", icon: "🏠" },
  { to: "/fundamental", label: "Fundamental", icon: "📊" },
  { to: "/valuation", label: "Valuation", icon: "💰" },
  { to: "/technical", label: "Technical", icon: "📈" },
  { to: "/volume", label: "Volume", icon: "📦" },
  { to: "/risk", label: "Risk", icon: "⚠️" },
  { to: "/institutional", label: "Institutional", icon: "🏦" },
  { to: "/sentiment", label: "Sentiment", icon: "🧭" },
  { to: "/earnings", label: "Earnings", icon: "📋" },
  { to: "/quantitative", label: "Quantitative", icon: "🔢" },
  { to: "/social", label: "Social", icon: "💬" },
  { to: "/geopolitical", label: "Geopolitical", icon: "🌍" },
  { to: "/political", label: "Political", icon: "🏛️" },
  { to: "/macro", label: "Macro", icon: "🌐" },
  { to: "/calendar", label: "Calendar", icon: "📅" },
  { to: "/summary", label: "AI Summary", icon: "🤖" },
];

export default function Sidebar() {
  return (
    <nav
      style={{
        width: 200,
        minWidth: 200,
        background: "var(--sidebar-bg)",
        borderRight: "1px solid var(--border)",
        padding: "16px 8px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        overflowY: "auto",
      }}
    >
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.to === "/"}
          style={({ isActive }) => ({
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "9px 12px",
            borderRadius: 8,
            fontSize: 14,
            textDecoration: "none",
            color: isActive ? "#ffffff" : "var(--text-secondary)",
            background: isActive ? "var(--accent)" : "transparent",
            fontWeight: isActive ? 600 : 400,
            transition: "background 0.15s, color 0.15s",
          })}
        >
          <span style={{ fontSize: 16 }}>{link.icon}</span>
          <span>{link.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
