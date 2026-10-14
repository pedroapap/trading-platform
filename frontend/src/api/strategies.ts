import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

export function useStrategies() {
  return useQuery({ queryKey: ["strategies"], queryFn: () => unwrap(api.GET("/api/strategies")) });
}
