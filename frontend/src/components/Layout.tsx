import { useQueryClient } from "@tanstack/react-query";
import { Outlet } from "react-router";

import { tokenStore } from "../api/token";

export default function Layout() {
  const queryClient = useQueryClient();

  function logOut() {
    tokenStore.clear();
    queryClient.clear();
  }

  return (
    <>
      <header className="container">
        <nav>
          <ul>
            <li>
              <strong>Trading Platform</strong>
            </li>
          </ul>
          <ul>
            <li>
              <button type="button" className="secondary outline" onClick={logOut}>
                Log out
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
