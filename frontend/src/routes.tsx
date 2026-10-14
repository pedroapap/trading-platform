import type { RouteObject } from "react-router";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "*", element: <p>Page not found.</p> },
        ],
      },
    ],
  },
];
