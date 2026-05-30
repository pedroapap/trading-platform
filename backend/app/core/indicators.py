"""Technical Indicators - Wrapper around TA-Lib"""

from typing import List
from decimal import Decimal
import numpy as np


class Indicators:
    """Technical indicator calculations"""

    @staticmethod
    def sma(prices: List[float], period: int) -> List[float]:
        """Simple Moving Average"""
        if len(prices) < period:
            return [None] * len(prices)

        sma_values = []
        for i in range(len(prices)):
            if i < period - 1:
                sma_values.append(None)
            else:
                sma_values.append(np.mean(prices[i - period + 1 : i + 1]))
        return sma_values

    @staticmethod
    def ema(prices: List[float], period: int) -> List[float]:
        """Exponential Moving Average"""
        if len(prices) < period:
            return [None] * len(prices)

        ema_values = []
        multiplier = 2.0 / (period + 1)

        # First EMA is SMA
        ema = np.mean(prices[:period])
        ema_values.extend([None] * (period - 1))
        ema_values.append(ema)

        # Subsequent EMAs
        for i in range(period, len(prices)):
            ema = (prices[i] - ema) * multiplier + ema
            ema_values.append(ema)

        return ema_values

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> List[float]:
        """Relative Strength Index"""
        if len(prices) < period + 1:
            return [None] * len(prices)

        deltas = np.diff(prices)
        gains = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        rsi_values = [None] * (period + 1)

        for i in range(period + 1, len(prices)):
            if avg_loss == 0:
                rsi_values.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                rsi_values.append(rsi)

            # Smooth averages
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        return rsi_values

    @staticmethod
    def macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """MACD (Moving Average Convergence Divergence)"""
        fast_ema = Indicators.ema(prices, fast)
        slow_ema = Indicators.ema(prices, slow)

        # MACD line
        macd_line = [
            f - s if f is not None and s is not None else None
            for f, s in zip(fast_ema, slow_ema)
        ]

        # Signal line
        signal_line = Indicators.ema(macd_line, signal)

        # Histogram
        histogram = [
            m - sig if m is not None and sig is not None else None
            for m, sig in zip(macd_line, signal_line)
        ]

        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(
        prices: List[float], period: int = 20, num_std: float = 2.0
    ) -> tuple:
        """Bollinger Bands"""
        sma_values = Indicators.sma(prices, period)

        upper_band = []
        lower_band = []

        for i in range(len(prices)):
            if sma_values[i] is None:
                upper_band.append(None)
                lower_band.append(None)
            else:
                std = np.std(prices[max(0, i - period + 1) : i + 1])
                upper = sma_values[i] + (num_std * std)
                lower = sma_values[i] - (num_std * std)
                upper_band.append(upper)
                lower_band.append(lower)

        return upper_band, sma_values, lower_band
