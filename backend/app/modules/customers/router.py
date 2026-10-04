from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_customer_session
from app.modules.auth_tenancy.models import CustomerSessionInfo
from app.modules.customers.models import CustomerContactCreate, CustomerContactResponse

router = APIRouter(prefix="/v1/customers", tags=["Customers & Marketing Consent"])


@router.post("", response_model=CustomerContactResponse)
async def register_customer_contact(
    data: CustomerContactCreate,
    session: CustomerSessionInfo = Depends(get_customer_session),
    db=Depends(get_database),
):
    """
    Captures optional customer name and phone number with explicit DPDP-compliant marketing consent.
    Called optionally at checkout or bill delivery.
    """
    cleaned_phone = data.phone.strip().replace(" ", "").replace("-", "")
    now = datetime.now(timezone.utc)

    # 1. Upsert customer in cafe-scoped customers collection
    customer_doc = await db.customers.find_one_and_update(
        {"cafe_id": session.cafe_id, "phone": cleaned_phone},
        {
            "$set": {
                "name": data.name,
                "updated_at": now,
            },
            "$setOnInsert": {
                "cafe_id": session.cafe_id,
                "phone": cleaned_phone,
                "created_at": now,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    # 2. Record explicit consent entry (audit trail)
    consent_record = {
        "cafe_id": session.cafe_id,
        "phone": cleaned_phone,
        "customer_id": str(customer_doc["_id"]),
        "session_id": session.session_id,
        "table_number": session.table_number,
        "marketing_consent": data.marketing_consent,
        "wording_version": data.consent_wording_version,
        "timestamp": now,
    }
    await db.consents.insert_one(consent_record)

    # 3. Associate name & phone with any active session orders
    await db.orders.update_many(
        {"cafe_id": session.cafe_id, "session_id": session.session_id},
        {"$set": {"customer_name": data.name, "customer_phone": cleaned_phone}},
    )

    return CustomerContactResponse(
        id=str(customer_doc["_id"]),
        cafe_id=session.cafe_id,
        name=customer_doc.get("name"),
        phone=cleaned_phone,
        marketing_consent=data.marketing_consent,
        created_at=customer_doc.get("created_at", now),
    )
