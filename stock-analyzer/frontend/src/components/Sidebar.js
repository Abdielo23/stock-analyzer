import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FileSpreadsheet,
  DollarSign,
  TrendingUp,
  BarChart2,
  AlertTriangle,
  Landmark,
  Gauge,
  Briefcase,
  Calculator,
  MessageSquare,
  Globe2,
  Building2,
  Map,
  CalendarDays,
  Sparkles,
} from "lucide-react";

const GROUPS = [
  {
    label: "Main",
    items: [{ to: "/", label: "Overview", icon: LayoutDashboard }],
  },
  {
    label: "Core Analysis",
    items: [
      { to: "/fundamental", label: "Fundamental", icon: FileSpreadsheet },
      { to: "/valuation", label: "Valuation", icon: DollarSign },
      { to: "/technical", label: "Technical", icon: TrendingUp },
      { to: "/volume", label: "Volume", icon: BarChart2 },
      { to: "/risk", label: "Risk", icon: AlertTriangle },
    ],
  },
  {
    label: "Market Intelligence",
    items: [
      { to: "/institutional", label: "Institutional", icon: Landmark },
      { to: "/sentiment", label: "Sentiment", icon: Gauge },
      { to: "/earnings", label: "Earnings", icon: Briefcase },
      { to: "/quantitative", label: "Quantitative", icon: Calculator },
    ],
  },
  {
    label: "External Factors",
    items: [
      { to: "/social", label: "Social", icon: MessageSquare },
      { to: "/geopolitical", label: "Geopolitical", icon: Globe2 },
      { to: "/political", label: "Political", icon: Building2 },
      { to: "/macro", label: "Macro", icon: Map },
    ],
  },
  {
    label: "Tools & Insights",
    items: [
      { to: "/calendar", label: "Calendar", icon: CalendarDays },
      { to: "/summary", label: "AI Summary", icon: Sparkles },
    ],
  },
];

export default function Sidebar() {
  return (
    <nav
      style={{
        width: 210,
        minWidth: 210,
        background: "var(--sidebar-bg)",
        borderRight: "1px solid var(--border)",
        padding: "16px 8px",
        display: "flex",
        flexDirection: "column",
        gap: 18,
        overflowY: "auto",
      }}
    >
      {GROUPS.map((group) => (
        <div key={group.label}>
          <div className="sidebar-group-label">{group.label}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `sidebar-link${isActive ? " active" : ""}`
                }
              >
                <item.icon size={17} strokeWidth={2} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}
