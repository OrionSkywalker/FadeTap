from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Appointment, BarberProfile, BarberShop, CheckoutAttempt, ClientNote, Service, User
from ..security import get_current_user, is_platform_admin

router = APIRouter(prefix="/api/admin", tags=["platform admin"])

def admin_user(user: User = Depends(get_current_user)) -> User:
    if not is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform administrator access is required")
    return user

class ShopMessage(BaseModel):
    message: str | None = Field(default=None, max_length=2000)

@router.get("/shops")
def shops(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    net_platform_fee = Appointment.platform_fee_cents - Appointment.stripe_processing_fee_cents
    rows = db.execute(select(BarberShop, func.count(Appointment.id), func.coalesce(func.sum(net_platform_fee), 0))
        .outerjoin(Appointment, (Appointment.shop_id == BarberShop.id) & (Appointment.status == "confirmed"))
        .group_by(BarberShop.id).order_by(BarberShop.created_at.desc())).all()
    return [{"id": shop.id, "name": shop.name, "slug": shop.slug, "owner_email": shop.owner_email,
             "owner_google_subject": shop.owner.google_subject,
             "owner_last_login_at": shop.owner.last_login_at.isoformat() if shop.owner.last_login_at else None,
             "appointments": count, "platform_fees_cents": fees, "admin_message": shop.admin_message,
             "access_suspended": shop.access_suspended,
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
