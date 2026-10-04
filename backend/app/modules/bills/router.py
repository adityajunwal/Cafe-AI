from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_customer_session
from app.modules.auth_tenancy.models import CustomerSessionInfo
from app.modules.bills.models import BillResponse
from app.modules.bills.service import BillService
from app.modules.cafes.repository import CafeRepository
from app.modules.orders.repository import OrderRepository

router = APIRouter(prefix="/v1/bills", tags=["Bills"])


def get_bill_service(db=Depends(get_database)) -> BillService:
    return BillService(
        db=db,
        order_repo=OrderRepository(db),
        cafe_repo=CafeRepository(db),
    )


@router.get("/{order_id}", response_model=BillResponse)
async def get_bill(
    order_id: str,
    session: CustomerSessionInfo = Depends(get_customer_session),
    bill_service: BillService = Depends(get_bill_service),
):
    try:
        bill = await bill_service.get_or_generate_bill(session.cafe_id, order_id)
        bill["id"] = str(bill["_id"])
        return BillResponse(**bill)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{order_id}/print")
async def get_printable_bill(
    order_id: str,
    session: CustomerSessionInfo = Depends(get_customer_session),
    bill_service: BillService = Depends(get_bill_service),
):
    """Renders print-friendly HTML for browser or thermal printing."""
    bill = await bill_service.get_or_generate_bill(session.cafe_id, order_id)

    items_html = "".join([
        f"<tr><td>{i['name']} x{i['quantity']}</td><td style='text-align:right'>₹{i['line_total_paise']/100:.2f}</td></tr>"
        for i in bill.get("items", [])
    ])

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Bill #{bill['bill_number']}</title>
    <style>
        body {{ font-family: monospace; max-width: 320px; margin: 20px auto; padding: 10px; border: 1px solid #ccc; }}
        h2, h3 {{ text-align: center; margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        td {{ padding: 4px 0; }}
        .divider {{ border-top: 1px dashed #333; margin: 10px 0; }}
        .total {{ font-weight: bold; font-size: 1.1em; }}
    </style>
</head>
<body onload="window.print()">
    <h2>{bill['cafe_name']}</h2>
    <h3>Table #{bill['table_number']}</h3>
    <p>Bill: {bill['bill_number']}<br>Date: {bill['created_at'].strftime('%Y-%m-%d %H:%M')}</p>
    <div class="divider"></div>
    <table>
        {items_html}
    </table>
    <div class="divider"></div>
    <table>
        <tr><td>Subtotal</td><td style="text-align:right">₹{bill['subtotal_paise']/100:.2f}</td></tr>
        <tr><td>Taxes & Charges</td><td style="text-align:right">₹{bill['tax_breakdown']['total_tax_paise']/100:.2f}</td></tr>
        <tr class="total"><td>Total</td><td style="text-align:right">₹{bill['total_paise']/100:.2f}</td></tr>
    </table>
    <div class="divider"></div>
    <p style="text-align:center">Thank you for dining with us!</p>
</body>
</html>
"""
    return Response(content=html, media_type="text/html")
