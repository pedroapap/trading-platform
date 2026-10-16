import { expect, test } from "vitest";

import { formatMoney } from "./format";

test.each([
  // A dollar stablecoin or a fiat currency shows to its smallest unit.
  { value: -0.42290331, currency: "USDT", shown: "-0.42" },
  { value: 1234.567, currency: "EUR", shown: "1,234.57" },
  { value: "0.004", currency: "USD", shown: "0.00" },
  { value: -0.004, currency: "USDC", shown: "0.00" },
  { value: 1234.5, currency: "JPY", shown: "1,235" },
  // A coin, or an unset currency: cents from 1 up, 8 significant digits below.
  { value: 0.00012345, currency: "BTC", shown: "0.00012345" },
  { value: 12.3, currency: "BTC", shown: "12.30" },
  { value: -0.42290331, currency: null, shown: "-0.42290331" },
  { value: "1234.567", currency: null, shown: "1,234.57" },
])("$value $currency is shown as $shown", ({ value, currency, shown }) => {
  expect(formatMoney(value, currency)).toBe(shown);
});
