import type { RouteObject } from "react-router";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import HomePage from "./pages/HomePage";
import JournalPage from "./pages/JournalPage";
import LoginPage from "./pages/LoginPage";
import NewTradePage from "./pages/NewTradePage";
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
          { path: "*", element: <p>Page not found.</p> },
        ],
      },
    ],
  },
];
