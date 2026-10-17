import { expect, test } from "vitest";

import { formatExactMoney, formatMoney } from "./format";

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

test.each([
  // Grouped, and padded to the currency's smallest unit.
  { amount: "1215.09", currency: "USDT", shown: "1,215.09" },
  { amount: "180.7", currency: "USDT", shown: "180.70" },
  { amount: "87", currency: "USD", shown: "87.00" },
  { amount: "6200", currency: "JPY", shown: "6,200" },
  { amount: "-144.67", currency: "USDT", shown: "-144.67" },
  // Never rounded: every digit the API sent stays.
  { amount: "6200.5", currency: "JPY", shown: "6,200.5" },
  { amount: "1234567.123456789012", currency: "USDT", shown: "1,234,567.123456789012" },
  { amount: "0.00126458", currency: "BTC", shown: "0.00126458" },
  { amount: "-25", currency: null, shown: "-25" },
])("the exact amount $amount $currency is shown as $shown", ({ amount, currency, shown }) => {
  expect(formatExactMoney(amount, currency)).toBe(shown);
});
