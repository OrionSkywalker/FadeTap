from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Appointment, BarberProfile, ClientNote, Service, User
from ..schemas import BarberClientRead, ClientNoteCreate
from ..security import get_current_user

router = APIRouter(prefix="/api/barber", tags=["barber"])


def current_barber(user: User, db: Session) -> BarberProfile:
    barber = db.scalar(select(BarberProfile).where(BarberProfile.user_id == user.id, BarberProfile.is_active.is_(True)))
    if barber is None:
        raise HTTPException(status_code=403, detail="No active barber profile is linked to this login")
    return barber


@router.get("/clients", response_model=list[BarberClientRead])
def list_clients(barber_id: int | None = Query(default=None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    barber = current_barber(user, db)
    if barber_id and barber_id != barber.id:
        if user.role != "owner":
            raise HTTPException(status_code=403, detail="You can only view your own client list")
        barber = db.scalar(select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == barber.shop_id, BarberProfile.is_active.is_(True)))
        if barber is None: raise HTTPException(status_code=404, detail="Barber not found")
    rows = db.execute(
        select(Appointment, Service.name)
        .join(Service, Service.id == Appointment.service_id)
        .where(Appointment.barber_id == barber.id, Appointment.status.in_(["confirmed", "manual_block"]))
        .order_by(Appointment.starts_at.desc())
    ).all()
    grouped: dict[tuple[str | None, str], dict] = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for appointment, service_name in rows:
        client_key = f"{appointment.client_name or 'Guest'}::{appointment.client_phone if appointment.sms_opt_in else 'private'}".lower()
        key = (appointment.client_name, client_key)
        item = grouped.setdefault(key, {"client_key": client_key, "client_name": appointment.client_name, "client_phone": appointment.client_phone if appointment.sms_opt_in else None,
                                        "sms_opt_in": appointment.sms_opt_in, "total_appointments": 0,
                                        "last_appointment_at": appointment.starts_at, "next_appointment_at": None, "last_service_name": service_name})
        item["total_appointments"] += 1
        if appointment.starts_at >= now and (item["next_appointment_at"] is None or appointment.starts_at < item["next_appointment_at"]):
            item["next_appointment_at"] = appointment.starts_at
    notes = db.scalars(select(ClientNote).where(ClientNote.barber_id == barber.id)).all()
    for note in notes:
        for item in grouped.values():
            if item["client_key"] == note.client_key:
                item.setdefault("notes", []).append(note.body)
    return list(grouped.values())


@router.post("/clients/{barber_id}/{client_key}/notes")
def add_client_note(barber_id: int, client_key: str, payload: ClientNoteCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    barber = current_barber(user, db)
    if barber_id != barber.id:
        if user.role != "owner":
            raise HTTPException(status_code=403, detail="You can only add notes to your own clients")
        barber = db.scalar(select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == barber.shop_id, BarberProfile.is_active.is_(True)))
        if barber is None: raise HTTPException(status_code=404, detail="Barber not found")
    db.add(ClientNote(shop_id=barber.shop_id, barber_id=barber.id, client_key=client_key, body=payload.body.strip()))
    db.commit()
    return {"status": "ok"}
