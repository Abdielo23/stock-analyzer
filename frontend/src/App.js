import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "./App.css";
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import Overview from "./pages/Overview";
import Fundamental from "./pages/Fundamental";
import Valuation from "./pages/Valuation";
import Technical from "./pages/Technical";
import Volume from "./pages/Volume";
import Risk from "./pages/Risk";
import Institutional from "./pages/Institutional";
import Sentiment from "./pages/Sentiment";
import Earnings from "./pages/Earnings";
import Quantitative from "./pages/Quantitative";
import Social from "./pages/Social";
import Geopolitical from "./pages/Geopolitical";
import Political from "./pages/Political";
import Macro from "./pages/Macro";
import Calendar from "./pages/Calendar";
import Summary from "./pages/Summary";

export default function App() {
  const [ticker, setTicker] = useState("AAPL");
  const [darkMode, setDarkMode] = useState(true);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  return (
    <div className="app">
      <TopBar
        ticker={ticker}
        onSearch={setTicker}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((d) => !d)}
      />
      <div className="main-layout">
        <Sidebar />
        <main className="content">
          <Routes>
            <Route path="/" element={<Overview ticker={ticker} />} />
            <Route path="/fundamental" element={<Fundamental ticker={ticker} />} />
            <Route path="/valuation" element={<Valuation ticker={ticker} />} />
            <Route path="/technical" element={<Technical ticker={ticker} />} />
            <Route path="/volume" element={<Volume ticker={ticker} />} />
            <Route path="/risk" element={<Risk ticker={ticker} />} />
            <Route path="/institutional" element={<Institutional ticker={ticker} />} />
            <Route path="/sentiment" element={<Sentiment ticker={ticker} />} />
            <Route path="/earnings" element={<Earnings ticker={ticker} />} />
            <Route path="/quantitative" element={<Quantitative ticker={ticker} />} />
            <Route path="/social" element={<Social ticker={ticker} />} />
            <Route path="/geopolitical" element={<Geopolitical ticker={ticker} />} />
            <Route path="/political" element={<Political ticker={ticker} />} />
            <Route path="/macro" element={<Macro ticker={ticker} />} />
            <Route path="/calendar" element={<Calendar ticker={ticker} />} />
            <Route path="/summary" element={<Summary ticker={ticker} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
