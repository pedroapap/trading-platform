import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

/** Every symbol in use and its quote currency, alphabetically. */
export function useInstruments() {
  return useQuery({
    queryKey: ["instruments"],
    queryFn: () => unwrap(api.GET("/api/instruments")),
  });
}
