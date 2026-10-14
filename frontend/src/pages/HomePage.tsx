import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";

export default function HomePage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/api/auth/me")) });

  return (
    <>
      <h1>Welcome</h1>
      {me.data && <p>Signed in as {me.data.email}.</p>}
    </>
  );
}
