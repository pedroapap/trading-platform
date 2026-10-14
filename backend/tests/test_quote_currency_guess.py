import pytest

from app.services.instruments import guess_quote_currency


@pytest.mark.parametrize(
    ("symbol", "quote"),
    [
        # A known currency after a separator.
        ("BTC/USDT", "USDT"),
        ("BTC-USD", "USD"),
        ("ETH_BTC", "BTC"),
        ("EUR/USD", "USD"),
        ("ETH-USD-PERP", "USD"),
        # ccxt names a swap's settlement currency after its pair.
        ("BTC/USDT:USDT", "USDT"),
        # An exchange prefix is ignored.
        ("BINANCE:BTCUSDT", "USDT"),
        ("COINBASE:BTC-USD", "USD"),
        # Otherwise the currency the symbol ends with...
        ("BTCUSDT", "USDT"),
        ("ETHBTC", "BTC"),
        ("BNBETH", "ETH"),
        ("EURUSD", "USD"),
        ("USDJPY", "JPY"),
        ("SOLEUR", "EUR"),
        ("SUSDT", "USDT"),
        # ...the longest one...
        ("BTCFDUSD", "FDUSD"),
        ("ETHBUSD", "BUSD"),
        ("BTCUSDC", "USDC"),
        # ...before a derivative suffix.
        ("BTCUSDT.P", "USDT"),
        ("BTCUSD_PERP", "USD"),
    ],
)
def test_the_quote_currency_is_read_from_the_symbol(symbol, quote):
    assert guess_quote_currency(symbol) == quote


@pytest.mark.parametrize(
    "symbol",
    [
        "AAPL",
        "BRK.B",
        # A currency on its own, or with nothing before it but a suffix, is no pair.
        "USDT",
        "BTC-PERP",
        # Tokens and funds named after a crypto currency.
        "WBTC",
        "GBTC",
        "WETH",
    ],
)
def test_a_symbol_that_names_no_quote_currency_has_no_guess(symbol):
    assert guess_quote_currency(symbol) is None
