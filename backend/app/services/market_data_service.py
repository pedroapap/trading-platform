"""Market Data Service - CSV import and queries"""

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import List, Tuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import MarketData


class MarketDataService:
    @staticmethod
    def import_csv(
        db: Session,
        csv_content: str,
        symbol: str,
    ) -> Tuple[UUID, int]:
        """Import market data from CSV file"""
        import_batch_id = uuid4()
        rows_imported = 0

        try:
            # Parse CSV
            reader = csv.DictReader(io.StringIO(csv_content))
            
            for row in reader:
                try:
                    market_data = MarketData(
                        symbol=symbol,
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=Decimal(row["open"]),
                        high=Decimal(row["high"]),
                        low=Decimal(row["low"]),
                        close=Decimal(row["close"]),
                        volume=int(row["volume"]),
                        source="csv_import",
                        import_batch_id=import_batch_id,
                    )
                    db.add(market_data)
                    rows_imported += 1
                except (ValueError, KeyError) as e:
                    # Skip malformed rows
                    continue

            db.commit()
            return import_batch_id, rows_imported

        except Exception as e:
            db.rollback()
            raise ValueError(f"CSV import failed: {str(e)}")

    @staticmethod
    def get_market_data(
        db: Session,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[MarketData]:
        """Fetch market data for a date range"""
        return db.query(MarketData).filter(
            MarketData.symbol == symbol,
            MarketData.timestamp >= start_time,
            MarketData.timestamp <= end_time,
        ).order_by(MarketData.timestamp.asc()).all()
