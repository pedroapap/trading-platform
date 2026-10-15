import type { RouteObject } from "react-router";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import BacktestPage from "./pages/BacktestPage";
import BacktestsPage from "./pages/BacktestsPage";
import HomePage from "./pages/HomePage";
import InstrumentsPage from "./pages/InstrumentsPage";
import JournalEntryPage from "./pages/JournalEntryPage";
import JournalPage from "./pages/JournalPage";
import LoginPage from "./pages/LoginPage";
import MarketDataPage from "./pages/MarketDataPage";
import NewBacktestPage from "./pages/NewBacktestPage";
import NewJournalEntryPage from "./pages/NewJournalEntryPage";
import NewStrategyPage from "./pages/NewStrategyPage";
import NewTradePage from "./pages/NewTradePage";
import StrategiesPage from "./pages/StrategiesPage";
import StrategyPage from "./pages/StrategyPage";
import TradeDetailPage from "./pages/TradeDetailPage";
import TradesPage from "./pages/TradesPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "trades", element: <TradesPage /> },
          { path: "trades/new", element: <NewTradePage /> },
          { path: "trades/:tradeId", element: <TradeDetailPage /> },
          { path: "journal", element: <JournalPage /> },
          { path: "journal/new", element: <NewJournalEntryPage /> },
          { path: "journal/:entryId", element: <JournalEntryPage /> },
          { path: "strategies", element: <StrategiesPage /> },
          { path: "strategies/new", element: <NewStrategyPage /> },
          { path: "strategies/:strategyId", element: <StrategyPage /> },
          { path: "backtests", element: <BacktestsPage /> },
          { path: "backtests/new", element: <NewBacktestPage /> },
          { path: "backtests/:backtestId", element: <BacktestPage /> },
          { path: "market-data", element: <MarketDataPage /> },
          { path: "instruments", element: <InstrumentsPage /> },
          { path: "*", element: <p>Page not found.</p> },
        ],
      },
    ],
  },
];
