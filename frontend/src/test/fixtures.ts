import type { components } from "../api/schema";

type Schemas = components["schemas"];

export const USER: Schemas["UserRead"] = {
  id: "0b4a6a4e-1c2d-4a1f-9e1b-2f6f1e0c9d11",
  email: "trader@example.com",
  is_active: true,
  created_at: "2026-01-05T14:30:00Z",
};
