"""Backtest Metrics Calculation"""

from typing import List, Dict
from decimal import Decimal
import numpy as np


class Metrics:
    """Calculate backtest performance metrics"""

    @staticmethod
    def calculate_returns(trade_pnls: List[Decimal], initial_capital: Decimal) -> tuple:
        """Calculate total return and return percentage"""
        total_pnl = sum(trade_pnls)
        total_return_pct = (total_pnl / initial_capital) * 100
        return total_pnl, total_return_pct

    @staticmethod
    def calculate_sharpe_ratio(
        daily_returns: List[float], risk_free_rate: float = 0.02
    ) -> float:
        """Calculate Sharpe ratio (annualized)"""
        if not daily_returns or len(daily_returns) < 2:
            return 0.0

        returns_array = np.array(daily_returns)
        excess_returns = returns_array - (risk_free_rate / 252)

        if np.std(excess_returns) == 0:
            return 0.0

        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        return float(sharpe * np.sqrt(252))  # Annualize

    @staticmethod
    def calculate_drawdown(equity_curve: List[Decimal]) -> tuple:
        """Calculate max drawdown and drawdown percentage"""
        if not equity_curve or len(equity_curve) < 2:
            return Decimal(0), Decimal(0)

        peak = equity_curve[0]
        max_drawdown = Decimal(0)
        max_drawdown_pct = Decimal(0)

        for value in equity_curve[1:]:
            if value > peak:
                peak = value
            drawdown = peak - value
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else Decimal(0)

            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct

        return max_drawdown, max_drawdown_pct

    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> float:
        """Calculate win rate from trades"""
        if not trades:
            return 0.0

        winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
        return (winning_trades / len(trades)) * 100

    @staticmethod
    def calculate_daily_returns(
        equity_curve: List[Decimal],
    ) -> List[float]:
        """Calculate daily returns from equity curve"""
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                daily_return = float(
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                )
                returns.append(daily_return)

        return returns
