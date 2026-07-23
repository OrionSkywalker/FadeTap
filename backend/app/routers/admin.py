from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Appointment, BarberProfile, BarberShop, CheckoutAttempt, ClientNote, PaymentDispute, PaymentRefund, PlatformSettings, Service, User
from ..security import get_current_user, is_platform_admin

router = APIRouter(prefix="/api/admin", tags=["platform admin"])

def admin_user(user: User = Depends(get_current_user)) -> User:
    if not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform administrator access is required")
    return user

class ShopMessage(BaseModel):
    message: str | None = Field(default=None, max_length=2000)


class PlatformPolicyUpdate(BaseModel):
    allowed_shop_state: str | None = Field(default="CA", max_length=2)
    allowed_shop_county: str | None = Field(default="Kern County", max_length=120)


class PaymentAccessOverride(BaseModel):
    enabled: bool


def platform_settings(db: Session) -> PlatformSettings:
    settings = db.get(PlatformSettings, 1)
    if settings is None:
        settings = PlatformSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings")
def get_settings(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    settings = platform_settings(db)
    return {
        "allowed_shop_country_code": settings.allowed_shop_country_code,
        "allowed_shop_state": settings.allowed_shop_state,
        "allowed_shop_county": settings.allowed_shop_county,
    }


@router.put("/settings")
def update_settings(payload: PlatformPolicyUpdate, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    settings = platform_settings(db)
    settings.allowed_shop_country_code = "US"
    settings.allowed_shop_state = payload.allowed_shop_state.strip().upper() if payload.allowed_shop_state else None
    settings.allowed_shop_county = payload.allowed_shop_county.strip() if payload.allowed_shop_county else None
    db.commit()
    return {
        "allowed_shop_country_code": settings.allowed_shop_country_code,
        "allowed_shop_state": settings.allowed_shop_state,
        "allowed_shop_county": settings.allowed_shop_county,
    }

@router.get("/shops")
def shops(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    net_platform_fee = Appointment.platform_fee_cents - Appointment.stripe_processing_fee_cents
    rows = db.execute(select(BarberShop, func.count(Appointment.id), func.coalesce(func.sum(net_platform_fee), 0))
        .outerjoin(Appointment, (Appointment.shop_id == BarberShop.id) & (Appointment.status == "confirmed"))
        .group_by(BarberShop.id).order_by(BarberShop.created_at.desc())).all()
    issues_by_shop: dict[int, list[dict]] = {}
    for item in db.scalars(select(PaymentRefund).join(Appointment)).all():
        issues_by_shop.setdefault(item.appointment.shop_id, []).append({"kind": "refund", "id": item.stripe_refund_id, "amount_cents": item.amount_cents, "status": item.status, "reason": item.reason})
    for item in db.scalars(select(PaymentDispute).join(Appointment)).all():
        issues_by_shop.setdefault(item.appointment.shop_id, []).append({"kind": "dispute", "id": item.stripe_dispute_id, "amount_cents": item.amount_cents, "status": item.status, "reason": item.reason, "due_by": item.due_by.isoformat() if item.due_by else None})
    return [{"id": shop.id, "name": shop.name, "slug": shop.slug, "owner_email": shop.owner_email,
             "owner_google_subject": shop.owner.google_subject,
             "owner_last_login_at": shop.owner.last_login_at.isoformat() if shop.owner.last_login_at else None,
             "appointments": count, "platform_fees_cents": fees, "admin_message": shop.admin_message,
             "access_suspended": shop.access_suspended,
             "payment_access_override": shop.payment_access_override,
             "location_verified": shop.location_verified,
             "location_country_code": shop.location_country_code,
             "location_county": shop.location_county,
             "payment_issues": issues_by_shop.get(shop.id, []),
             "barbers": [{"id": barber.id, "display_name": barber.display_name, "is_owner": barber.is_owner, "is_active": barber.is_active}
                         for barber in db.scalars(select(BarberProfile).where(BarberProfile.shop_id == shop.id).order_by(BarberProfile.display_name)).all()]}
            for shop, count, fees in rows]

@router.put("/shops/{shop_id}/message")
def set_shop_message(shop_id: int, payload: ShopMessage, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    shop = db.get(BarberShop, shop_id)
    if shop is None: raise HTTPException(status_code=404, detail="Shop not found")
    shop.admin_message = payload.message
    db.commit()
    return {"status": "ok"}


@router.put("/shops/{shop_id}/payment-access")
def set_payment_access_override(shop_id: int, payload: PaymentAccessOverride, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    shop = db.get(BarberShop, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop.payment_access_override = payload.enabled
    if payload.enabled:
        shop.access_warning_month, shop.access_suspended = None, False
    db.commit()
    return {"status": "ok", "payment_access_override": shop.payment_access_override}


@router.delete("/shops/{shop_id}/barbers/{barber_id}")
def remove_barber(shop_id: int, barber_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    barber = db.scalar(select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == shop_id))
    if barber is None: raise HTTPException(status_code=404, detail="Barber not found")
    if barber.is_owner: raise HTTPException(status_code=400, detail="Remove the entire shop to remove its owner")
    barber.is_active = False
    for service in db.scalars(select(Service).where(Service.shop_id == shop_id, Service.barber_id == barber_id)):
        service.is_active = False
    db.commit()
    return {"status": "ok"}


@router.delete("/shops/{shop_id}")
def remove_shop(shop_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    shop = db.get(BarberShop, shop_id)
    if shop is None: raise HTTPException(status_code=404, detail="Shop not found")
    db.query(ClientNote).filter(ClientNote.shop_id == shop_id).delete(synchronize_session=False)
    db.query(CheckoutAttempt).filter(CheckoutAttempt.shop_id == shop_id).delete(synchronize_session=False)
    db.delete(shop)
    db.commit()
    return {"status": "ok"}
