"""Market Data Routes - API endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import MarketDataImportResponse
from app.services.market_data_service import MarketDataService
from uuid import UUID

router = APIRouter()


def get_current_user_id(request: Request) -> UUID:
    """Extract user_id from request state"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return UUID(user_id)


@router.post("/import", response_model=MarketDataImportResponse)
async def import_market_data(
    file: UploadFile = File(...),
    symbol: str = "BTC",
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Import market data from CSV file"""
    try:
        # Read CSV content
        content = await file.read()
        csv_content = content.decode("utf-8")
        
        # Import to database
        batch_id, rows_imported = MarketDataService.import_csv(
            db, csv_content, symbol
        )
        
        return MarketDataImportResponse(
            import_batch_id=str(batch_id),
            rows_imported=rows_imported,
            symbol=symbol,
            date_range={"first_import": "check database"}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}"
        )
