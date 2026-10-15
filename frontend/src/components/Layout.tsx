import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";

import { tokenStore } from "../api/token";

export default function Layout() {
  const queryClient = useQueryClient();

  function logOut() {
    tokenStore.clear();
    queryClient.clear();
  }

  return (
    <>
      <header className="container-fluid">
        <nav>
          <ul>
            <li>
              <strong>Trading Platform</strong>
            </li>
          </ul>
          <ul>
            <li>
              <NavLink to="/trades">Trades</NavLink>
            </li>
            <li>
              <NavLink to="/journal">Journal</NavLink>
            </li>
            <li>
              <NavLink to="/strategies">Strategies</NavLink>
            </li>
            <li>
              <button type="button" className="secondary outline" onClick={logOut}>
                Log out
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main className="container-fluid">
        <Outlet />
      </main>
    </>
  );
}
