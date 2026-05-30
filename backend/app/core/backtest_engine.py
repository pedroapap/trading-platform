"""Backtest Execution Engine"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import MarketData, Strategy, StrategyVersion
from app.core.indicators import Indicators
from app.core.metrics import Metrics


class BacktestEngine:
    """Simulates strategy execution on historical data"""

    def __init__(self, db: Session, strategy: Strategy, strategy_version: int):
        self.db = db
        self.strategy = strategy
        self.strategy_version = strategy_version
        self.trades: List[Dict] = []
        self.entry_prices: List[Decimal] = []
        self.equity_curve: List[Decimal] = []

    def run(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: Decimal,
        position_size_pct: Decimal = Decimal(2),
        slippage_pct: Decimal = Decimal(0.1),
        commission_pct: Decimal = Decimal(0.1),
        max_leverage: Decimal = Decimal(1.0),
    ) -> Dict:
        """Execute backtest"""
        # Fetch market data
        market_data = (
            self.db.query(MarketData)
            .filter(
                MarketData.symbol == symbol,
                MarketData.timestamp >= start_date,
                MarketData.timestamp <= end_date,
            )
            .order_by(MarketData.timestamp.asc())
            .all()
        )

        if not market_data:
            return {"error": "No market data found for date range", "trades": []}

        # Initialize
        capital = initial_capital
        position = None
        entry_num = 0

        # Extract OHLCV data
        closes = [float(bar.close) for bar in market_data]
        highs = [float(bar.high) for bar in market_data]
        lows = [float(bar.low) for bar in market_data]

        # Get strategy rules from version
        strategy_version_obj = (
            self.db.query(StrategyVersion)
            .filter(
                StrategyVersion.strategy_id == self.strategy.id,
                StrategyVersion.version_number == self.strategy_version,
            )
            .first()
        )
        if not strategy_version_obj:
            return {"error": "Strategy version not found", "trades": []}

        entry_rules = strategy_version_obj.entry_rules
        exit_rules = strategy_version_obj.exit_rules

        # Backtest loop
        for i in range(len(market_data)):
            current_bar = market_data[i]
            current_close = closes[i]
            current_high = highs[i]
            current_low = lows[i]

            # Check exit conditions
            if position:
                should_exit = self._check_rules(exit_rules, closes[:i+1], i, current_bar)
                if should_exit:
                    # Execute exit
                    exit_price = Decimal(str(current_low))
                    if position["direction"] == "long":
                        if current_low < position["entry_price"]:
                            exit_price = Decimal(str(current_low))
                        else:
                            exit_price = position["entry_price"]
                    # Calculate P&L
                    pnl = self._calculate_pnl(
                        position, exit_price, commission_pct
                    )
                    capital += pnl

                    # Log trade
                    self.trades.append({
                        "trade_num": len(self.trades) + 1,
                        "entry_time": position["entry_time"],
                        "exit_time": current_bar.timestamp,
                        "entry_price": float(position["entry_price"]),
                        "exit_price": float(exit_price),
                        "size": float(position["size"]),
                        "pnl": float(pnl),
                        "pnl_pct": float((pnl / (position["entry_price"] * position["size"])) * 100),
                    })

                    position = None

            # Check entry conditions
            if not position:
                should_enter = self._check_rules(entry_rules, closes[:i+1], i, current_bar)
                if should_enter and capital > 0:
                    # Calculate position size
                    position_size = (capital * position_size_pct) / Decimal(100)
                    position = {
                        "direction": "long",
                        "entry_time": current_bar.timestamp,
                        "entry_price": Decimal(str(current_close)),
                        "size": position_size / Decimal(str(current_close)),
                    }

            # Track equity
            if position:
                unrealized = self._calculate_unrealized(
                    position, Decimal(str(current_close))
                )
                self.equity_curve.append(capital + unrealized)
            else:
                self.equity_curve.append(capital)

        # Calculate metrics
        if not self.trades:
            return {
                "status": "completed",
                "total_pnl": 0,
                "total_return_pct": 0,
                "sharpe_ratio": 0,
                "max_drawdown_pct": 0,
                "win_rate": 0,
                "num_trades": 0,
                "trades": [],
            }

        trade_pnls = [Decimal(str(t["pnl"])) for t in self.trades]
        total_pnl, total_return_pct = Metrics.calculate_returns(
            trade_pnls, initial_capital
        )

        daily_returns = Metrics.calculate_daily_returns(self.equity_curve)
        sharpe_ratio = Metrics.calculate_sharpe_ratio(daily_returns) if daily_returns else 0

        max_dd, max_dd_pct = Metrics.calculate_drawdown(self.equity_curve)
        win_rate = Metrics.calculate_win_rate(self.trades)

        return {
            "status": "completed",
            "total_pnl": float(total_pnl),
            "total_return_pct": float(total_return_pct),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown_pct": float(max_dd_pct),
            "win_rate": win_rate,
            "num_trades": len(self.trades),
            "trades": self.trades,
        }

    def _check_rules(
        self, rules: List[Dict], prices: List[float], current_idx: int, current_bar
    ) -> bool:
        """Check if rules are met (simplified logic)"""
        if not rules:
            return False

        # For MVP, assume simple AND logic across rules
        for rule in rules:
            if rule.get("indicator") == "RSI":
                rsi_values = Indicators.rsi(prices, rule.get("period", 14))
                if rsi_values[current_idx] is None:
                    return False

                threshold = rule.get("threshold", 30)
                condition = rule.get("condition", "<")

                if condition == "<" and rsi_values[current_idx] < threshold:
                    continue
                elif condition == ">" and rsi_values[current_idx] > threshold:
                    continue
                else:
                    return False

        return True

    def _calculate_pnl(
        self, position: Dict, exit_price: Decimal, commission_pct: Decimal
    ) -> Decimal:
        """Calculate P&L for a closed position"""
        if position["direction"] == "long":
            gross_pnl = (exit_price - position["entry_price"]) * position["size"]
        else:
            gross_pnl = (position["entry_price"] - exit_price) * position["size"]

        commission = (exit_price * position["size"]) * (commission_pct / Decimal(100))
        return gross_pnl - commission

    def _calculate_unrealized(
        self, position: Dict, current_price: Decimal
    ) -> Decimal:
        """Calculate unrealized P&L"""
        if position["direction"] == "long":
            return (current_price - position["entry_price"]) * position["size"]
        else:
            return (position["entry_price"] - current_price) * position["size"]
