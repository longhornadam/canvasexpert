"""Read-only local receipt projections and PRIVATE detail."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.operation_ledger import receipts


router = APIRouter(tags=["receipts"])


@router.get("/api/receipts")
def list_receipts():
    return JSONResponse({"ok": True, "receipts": receipts.list_receipts()})


@router.get("/api/receipts/{receipt_id}")
def receipt_detail(receipt_id: str):
    receipt = receipts.get_receipt(receipt_id)
    if receipt is None:
        return JSONResponse({"ok": False, "error": "Receipt not found."}, status_code=404)
    return JSONResponse({"ok": True, "receipt": receipt})
