import { Navigate, Outlet, useLocation } from "react-router";

import { useToken } from "../auth";

/** Renders its child routes only after login; otherwise asks to log in, remembering where
 * the user was going. */
export default function RequireAuth() {
  const token = useToken();
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location }} />;
  return <Outlet />;
}
