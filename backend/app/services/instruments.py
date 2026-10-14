"""Instruments: the currency each symbol is quoted in, which is the currency of its prices,
fees and P&L."""

import re

STABLECOINS = frozenset({"USDT", "USDC", "FDUSD", "BUSD", "TUSD"})
FIAT = frozenset({"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY", "BRL"})
# A symbol needs two or more characters before these to be read as a pair, so that tokens
# and funds named after them (WBTC, GBTC, WETH) are not taken for one.
CRYPTO_QUOTES = frozenset({"BTC", "ETH", "BNB"})
QUOTE_CURRENCIES = STABLECOINS | FIAT | CRYPTO_QUOTES

# Longest first, so that BTCFDUSD is quoted in FDUSD rather than USD.
_LONGEST_FIRST = sorted(QUOTE_CURRENCIES, key=lambda quote: (-len(quote), quote))
_SEPARATOR = re.compile(r"[/:_.-]")


def guess_quote_currency(symbol: str) -> str | None:
    """The quote currency a normalized symbol's name implies, or None when it tells nothing.

    A known currency after a separator is the quote (BTC/USDT, BTC-USD, ETH_BTC, ccxt's
    BTC/USDT:USDT); otherwise it is the longest known currency the symbol ends with (BTCUSDT,
    ETHBTC, EURUSD). An exchange prefix (BINANCE:BTCUSDT) and a derivative suffix (BTCUSDT.P,
    BTCUSD_PERP) are ignored. AAPL tells nothing, and neither does USDT on its own.
    """
    if "/" not in symbol:
        symbol = symbol.rpartition(":")[2]
    base, *rest = _SEPARATOR.split(symbol)
    if base and rest and rest[0] in QUOTE_CURRENCIES:
        return rest[0]
    for quote in _LONGEST_FIRST:
        shortest_base = 2 if quote in CRYPTO_QUOTES else 1
        if base.endswith(quote) and len(base) - len(quote) >= shortest_base:
            return quote
    return None
