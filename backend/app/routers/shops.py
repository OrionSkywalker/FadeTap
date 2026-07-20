from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from secrets import choice as secure_choice
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from PIL import Image
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Appointment,
    BarberBlockout,
    BarberProfile,
    BarberShop,
    BusinessHour,
    CheckoutAttempt,
    Service,
    ShopDateHourOverride,
    User,
)
from ..payments import (
    create_account_link,
    create_booking_checkout as create_stripe_booking_checkout,
    create_connected_account,
    create_monthly_access_checkout,
    create_shop_setup_checkout,
    get_payment_processing_fee_cents,
    get_open_shop_setup_checkout_url,
    is_paid_shop_setup_checkout,
    retrieve_connected_account_status,
    select_payout_account,
    StripeConfigurationError,
    stripe_is_configured,
)
from ..schemas import (
    AppointmentCreate,
    BarberCreate,
    BarberUpdate,
    BarberRead,
    BarberShopRead,
    BarberShopRegister,
    BusinessHourBase,
    BusinessHoursUpdate,
    CheckoutResponse,
    ConnectLinkResponse,
    DashboardResponse,
    DateHourOverrideUpsert,
    ManualAppointmentCreate,
    RegistrationResponse,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    ShopDiscoveryRead,
    ShopProfileUpdate,
    ShopPublicResponse,
    ShopSlotsResponse,
    SlotRead,
    AppointmentCalendarRead,
    ToggleBlockoutRequest,
)
from ..security import create_access_token, get_current_user, hash_password, is_platform_admin

router = APIRouter(prefix="/api/shops", tags=["shops"])

UPLOAD_DIR = Path("uploads")
MONTHLY_PLATFORM_FEE_CAP_CENTS = 2500
ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MIN_HERO_SIZE = (600, 315)
MIN_LOGO_SIZE = (256, 256)


def get_owned_shop(user: User, db: Session) -> BarberShop:
    if user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only shop owners can access this dashboard")
    shop = db.scalar(select(BarberShop).where(BarberShop.owner_user_id == user.id))
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


def shop_is_publishable(shop: BarberShop) -> bool:
    return shop.setup_payment_status in {"paid", "demo"} or (
        not stripe_is_configured() and shop.setup_payment_status == "stripe_not_configured"
    )


def sync_connected_account_statuses(shop: BarberShop, barbers: list[BarberProfile], db: Session) -> None:
    if not stripe_is_configured():
        return

    changed = False
    if shop.stripe_account_id:
        try:
            account_ready, _ = retrieve_connected_account_status(shop.stripe_account_id)
        except StripeConfigurationError:
            account_ready = False
        if shop.stripe_onboarding_complete != account_ready:
            shop.stripe_onboarding_complete = account_ready
            changed = True

    for barber in barbers:
        if not barber.stripe_account_id:
            continue
        try:
            account_ready, _ = retrieve_connected_account_status(barber.stripe_account_id)
        except StripeConfigurationError:
            account_ready = False
        if barber.stripe_onboarding_complete != account_ready:
            barber.stripe_onboarding_complete = account_ready
            changed = True

    if changed:
        db.commit()


def serialize_dashboard(user: User, shop: BarberShop, db: Session) -> DashboardResponse:
    refresh_recent_processing_fees(shop.id, db)
    sync_shop_access(shop, db)
    barbers = db.scalars(
        select(BarberProfile)
        .where(BarberProfile.shop_id == shop.id, BarberProfile.is_active.is_(True))
        .order_by(BarberProfile.is_owner.desc(), BarberProfile.display_name.asc())
    ).all()
    services = db.scalars(
        select(Service)
        .where(Service.shop_id == shop.id, Service.is_active.is_(True))
        .order_by(Service.name.asc())
    ).all()
    hours = get_ordered_business_hours(shop.id, db)
    sync_connected_account_statuses(shop, list(barbers), db)
    now = datetime.now(timezone.utc)
    appointment_rows = db.execute(
        select(Appointment, Service.name, BarberProfile.display_name)
        .join(Service, Service.id == Appointment.service_id)
        .outerjoin(BarberProfile, BarberProfile.id == Appointment.barber_id)
        .where(
            Appointment.shop_id == shop.id,
            Appointment.starts_at >= now,
            Appointment.status.in_(["confirmed", "manual_block"]),
        )
        .order_by(Appointment.starts_at.asc())
        .limit(100)
    ).all()
    appointments = [
        AppointmentCalendarRead(
            **appointment.__dict__,
            service_name=service_name,
            barber_name=barber_name,
        )
        for appointment, service_name, barber_name in appointment_rows
    ]
    blockouts = list(
        db.scalars(
            select(BarberBlockout)
            .where(BarberBlockout.shop_id == shop.id)
            .order_by(BarberBlockout.blocked_date.asc())
        ).all()
    )
    date_hour_overrides = get_date_hour_overrides(shop.id, db)
    return DashboardResponse(
        user=user,
        shop=shop,
        barbers=list(barbers),
        services=list(services),
        business_hours=hours,
        date_hour_overrides=date_hour_overrides,
        upcoming_appointments=appointments,
        blockouts=blockouts,
        platform_fees_this_month_cents=platform_fees_for_month(shop.id, month_start(), db),
        previous_month_platform_fees_cents=platform_fees_for_month(shop.id, month_start(1), db),
        monthly_platform_fee_target_cents=MONTHLY_PLATFORM_FEE_CAP_CENTS,
    )


def hold_platform_fee_cents(booking_fee_cents: int) -> int:
    return booking_fee_cents // 3


def month_start(offset: int = 0) -> datetime:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - offset
    while month <= 0:
        year -= 1
        month += 12
    return datetime(year, month, 1)


def platform_fees_for_month(shop_id: int, start: datetime, db: Session) -> int:
    end = datetime(start.year + 1, 1, 1) if start.month == 12 else datetime(start.year, start.month + 1, 1)
    net_platform_fee = Appointment.platform_fee_cents - Appointment.stripe_processing_fee_cents
    return int(db.scalar(select(func.coalesce(func.sum(net_platform_fee), 0)).where(
        Appointment.shop_id == shop_id, Appointment.status == "confirmed",
        Appointment.starts_at >= start, Appointment.starts_at < end,
    )) or 0)


def refresh_recent_processing_fees(shop_id: int, db: Session) -> None:
    """Backfill actual Stripe processing fees for recent paid appointments.

    The first dashboard visit after this release also corrects existing recent
    appointments that were created before processing fees were stored.
    """
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.shop_id == shop_id,
            Appointment.status == "confirmed",
            Appointment.starts_at >= month_start(2),
            Appointment.stripe_payment_intent_id.is_not(None),
            Appointment.stripe_processing_fee_cents == 0,
        )
        .limit(100)
    ).all()
    changed = False
    for appointment in appointments:
        fee_cents = get_payment_processing_fee_cents(appointment.stripe_payment_intent_id)
        if fee_cents is not None:
            appointment.stripe_processing_fee_cents = fee_cents
            changed = True
    if changed:
        db.commit()


def sync_shop_access(shop: BarberShop, db: Session) -> None:
    current_month = month_start().strftime("%Y-%m")
    current_fees = platform_fees_for_month(shop.id, month_start(), db)
    previous_month_start = month_start(1)
    previous_month = previous_month_start.strftime("%Y-%m")
    previous_fees = platform_fees_for_month(shop.id, previous_month_start, db)
    shop_created_at = shop.created_at.replace(tzinfo=timezone.utc) if shop.created_at.tzinfo is None else shop.created_at
    had_full_previous_month = shop_created_at < previous_month_start

    if current_fees >= MONTHLY_PLATFORM_FEE_CAP_CENTS or shop.monthly_access_paid_month == current_month:
        shop.access_warning_month, shop.access_suspended = None, False
    elif not had_full_previous_month or previous_fees >= MONTHLY_PLATFORM_FEE_CAP_CENTS or shop.monthly_access_paid_month == previous_month:
        shop.access_warning_month, shop.access_suspended = None, False
    elif shop.access_warning_month and shop.access_warning_month != current_month:
        shop.access_suspended = True
    else:
        shop.access_warning_month = current_month
        shop.access_suspended = False
    db.commit()


def capped_platform_fee(shop_id: int, normal_fee_cents: int, db: Session) -> int:
    remaining = MONTHLY_PLATFORM_FEE_CAP_CENTS - platform_fees_for_month(shop_id, month_start(), db)
    return max(0, min(normal_fee_cents, remaining))


def default_business_hours() -> list[BusinessHourBase]:
    return [
        BusinessHourBase(
            day_of_week=day,
            opens_at="09:00",
            closes_at="17:00",
            is_closed=day in {6},
        )
        for day in range(7)
    ]


def get_ordered_business_hours(shop_id: int, db: Session) -> list[BusinessHour]:
    db.rollback()
    hours = list(
        db.scalars(
            select(BusinessHour)
            .where(BusinessHour.shop_id == shop_id)
            .order_by(BusinessHour.day_of_week.asc())
        ).all()
    )
    if len(hours) == 7:
        return hours

    existing_days = {hour.day_of_week for hour in hours}
    try:
        for hour in default_business_hours():
            if hour.day_of_week not in existing_days:
                db.add(BusinessHour(shop_id=shop_id, **hour.model_dump()))
        db.commit()
    except IntegrityError:
        db.rollback()
    return list(
        db.scalars(
            select(BusinessHour)
            .where(BusinessHour.shop_id == shop_id)
            .order_by(BusinessHour.day_of_week.asc())
        ).all()
    )


def get_date_hour_overrides(shop_id: int, db: Session) -> list[ShopDateHourOverride]:
    return list(
        db.scalars(
            select(ShopDateHourOverride)
            .where(ShopDateHourOverride.shop_id == shop_id)
            .order_by(ShopDateHourOverride.specific_date.asc())
        ).all()
    )


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def to_microdegrees(value: float | None) -> int | None:
    return round(value * 1_000_000) if value is not None else None


def from_microdegrees(value: int | None) -> float | None:
    return value / 1_000_000 if value is not None else None


def distance_miles(
    origin_lat: float | None,
    origin_lng: float | None,
    shop_lat_micro: int | None,
    shop_lng_micro: int | None,
) -> float | None:
    shop_lat = from_microdegrees(shop_lat_micro)
    shop_lng = from_microdegrees(shop_lng_micro)
    if origin_lat is None or origin_lng is None or shop_lat is None or shop_lng is None:
        return None

    lat1, lng1, lat2, lng2 = map(radians, [origin_lat, origin_lng, shop_lat, shop_lng])
    lat_delta = lat2 - lat1
    lng_delta = lng2 - lng1
    haversine = sin(lat_delta / 2) ** 2 + cos(lat1) * cos(lat2) * sin(lng_delta / 2) ** 2
    return round(3958.8 * 2 * asin(sqrt(haversine)), 1)


def shop_timezone(shop: BarberShop) -> ZoneInfo:
    try:
        return ZoneInfo(shop.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Los_Angeles")


def appointment_statuses_that_hold_time() -> list[str]:
    return ["confirmed", "stripe_not_configured", "manual_block"]


CHECKOUT_ATTEMPT_EXPIRY_MINUTES = 31


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def has_appointment_overlap(
    shop_id: int,
    starts_at: datetime,
    duration_minutes: int,
    db: Session,
    barber_id: int | None = None,
) -> bool:
    starts_at = utc_naive(starts_at)
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    rows = db.execute(
        select(Appointment.starts_at, Service.duration_minutes)
        .join(Service, Service.id == Appointment.service_id)
        .where(
            Appointment.shop_id == shop_id,
            Appointment.status.in_(appointment_statuses_that_hold_time()),
            Appointment.starts_at < ends_at,
        )
    )
    if barber_id is not None:
        rows = db.execute(
            select(Appointment.starts_at, Service.duration_minutes)
            .join(Service, Service.id == Appointment.service_id)
            .where(
                Appointment.shop_id == shop_id,
                Appointment.barber_id == barber_id,
                Appointment.status.in_(appointment_statuses_that_hold_time()),
                Appointment.starts_at < ends_at,
            )
        )

    for existing_start, existing_duration in rows.all():
        existing_start = utc_naive(existing_start)
        existing_end = existing_start + timedelta(minutes=existing_duration)
        if starts_at < existing_end and existing_start < ends_at:
            return True
    return False


def build_available_slots(
    shop: BarberShop,
    service: Service,
    db: Session,
    selected_date: date | None = None,
    barber_id: int | None = None,
) -> list[SlotRead]:
    tz = shop_timezone(shop)
    now_local = datetime.now(tz)
    hours_by_day = {hour.day_of_week: hour for hour in get_ordered_business_hours(shop.id, db)}
    date_overrides = {
        override.specific_date: override for override in get_date_hour_overrides(shop.id, db)
    }
    candidate_starts: list[datetime] = []
    max_days = max(30, shop.booking_window_days or 30)
    candidate_limit = 96 if selected_date is not None else 24
    start_offset = 0
    end_offset = max_days

    if selected_date:
        today = now_local.date()
        if selected_date < today or selected_date > today + timedelta(days=max_days):
            return []
        start_offset = (selected_date - today).days
        end_offset = start_offset + 1

    for day_offset in range(start_offset, end_offset):
        local_day = now_local.date() + timedelta(days=day_offset)
        date_override = date_overrides.get(local_day.isoformat())
        business_hour = date_override or hours_by_day.get(local_day.weekday())
        if business_hour is None or business_hour.is_closed:
            continue
        opens_at = datetime.combine(local_day, parse_hhmm(business_hour.opens_at), tzinfo=tz)
        closes_at = datetime.combine(local_day, parse_hhmm(business_hour.closes_at), tzinfo=tz)
        slot_start = opens_at
        while slot_start + timedelta(minutes=service.duration_minutes) <= closes_at:
            if slot_start > now_local + timedelta(minutes=30):
                candidate_starts.append(slot_start.astimezone(timezone.utc))
            # Quarter-hour starts accommodate services such as 45-minute cuts
            # without forcing providers into half-hour-only gaps.
            slot_start += timedelta(minutes=15)
            if len(candidate_starts) >= candidate_limit:
                break
        if len(candidate_starts) >= candidate_limit:
            break

    slots = []
    for slot_start in candidate_starts:
        available_providers = available_service_providers(
            shop, service, slot_start, db, barber_id=barber_id,
        )
        if not available_providers:
            continue
        local_start = slot_start.astimezone(tz)
        slots.append(
            SlotRead(
                starts_at=slot_start,
                label=local_start.strftime("%a %I:%M %p"),
                date=local_start.date().isoformat(),
                barber_id=barber_id,
            )
        )
        if selected_date is None and len(slots) == 8:
            break
    return slots


def matching_service_offerings(shop: BarberShop, service: Service, db: Session) -> list[tuple[Service, BarberProfile]]:
    """Find active providers offering the same public service at the same price and duration."""
    if service.barber_id is None:
        barbers = db.scalars(
            select(BarberProfile)
            .where(BarberProfile.shop_id == shop.id, BarberProfile.is_active.is_(True))
            .order_by(BarberProfile.is_owner.desc(), BarberProfile.id.asc())
        ).all()
        return [(service, barber) for barber in barbers]
    return list(
        db.execute(
            select(Service, BarberProfile)
            .join(BarberProfile, BarberProfile.id == Service.barber_id)
            .where(
                Service.shop_id == shop.id,
                Service.is_active.is_(True),
                Service.name == service.name,
                Service.description == service.description,
                Service.duration_minutes == service.duration_minutes,
                Service.price_cents == service.price_cents,
                Service.booking_fee_cents == service.booking_fee_cents,
                Service.deposit_cents == service.deposit_cents,
                Service.platform_fee_cents == service.platform_fee_cents,
                BarberProfile.shop_id == shop.id,
                BarberProfile.is_active.is_(True),
            )
            .order_by(BarberProfile.is_owner.desc(), BarberProfile.id.asc())
        ).all()
    )


def available_service_providers(
    shop: BarberShop,
    service: Service,
    starts_at: datetime,
    db: Session,
    barber_id: int | None = None,
) -> list[tuple[Service, BarberProfile]]:
    local_date = starts_at.astimezone(shop_timezone(shop)).date().isoformat()
    providers = matching_service_offerings(shop, service, db)
    if barber_id is not None:
        providers = [provider for provider in providers if provider[1].id == barber_id]
    return [
        provider
        for provider in providers
        if not is_barber_blocked(shop.id, provider[1].id, local_date, db)
        and not has_appointment_overlap(
            shop.id, starts_at, provider[0].duration_minutes, db, provider[1].id,
        )
    ]


def assign_available_service_provider(
    shop: BarberShop,
    service: Service,
    starts_at: datetime,
    db: Session,
    barber_id: int | None = None,
) -> tuple[Service, BarberProfile] | None:
    providers = available_service_providers(shop, service, starts_at, db, barber_id=barber_id)
    if not providers:
        return None
    owner_provider = next((provider for provider in providers if provider[1].is_owner), None)
    return owner_provider or secure_choice(providers)


def public_service_signature(service: Service) -> tuple[object, ...]:
    return (
        service.name.casefold(),
        service.description or "",
        service.duration_minutes,
        service.price_cents,
        service.booking_fee_cents,
        service.deposit_cents,
        service.platform_fee_cents,
    )


def unique_public_services(services: list[Service]) -> list[Service]:
    choices: list[Service] = []
    signatures: set[tuple[object, ...]] = set()
    for service in services:
        signature = public_service_signature(service)
        if signature not in signatures:
            signatures.add(signature)
            choices.append(service)
    return choices


def validate_service_amounts(service_data: dict) -> None:
    if service_data["booking_fee_cents"] < 100:
        raise HTTPException(status_code=400, detail="Hold booking fee must be at least $1.00")
    if service_data["price_cents"] <= 100:
        raise HTTPException(
            status_code=400,
            detail="Full service price must be greater than $1.00",
        )


def assign_service_barber(service_data: dict, shop: BarberShop, db: Session) -> None:
    barber_id = service_data.get("barber_id")
    if barber_id is None:
        default_barber = db.scalar(
            select(BarberProfile)
            .where(BarberProfile.shop_id == shop.id, BarberProfile.is_active.is_(True))
            .order_by(BarberProfile.is_owner.desc(), BarberProfile.id.asc())
        )
        if default_barber is None:
            raise HTTPException(status_code=400, detail="Add an active barber before creating a service")
        service_data["barber_id"] = default_barber.id
        return
    barber = db.scalar(
        select(BarberProfile).where(
            BarberProfile.id == barber_id,
            BarberProfile.shop_id == shop.id,
            BarberProfile.is_active.is_(True),
        )
    )
    if barber is None:
        raise HTTPException(status_code=400, detail="Choose an active barber from this shop")


def validate_hour_window(opens_at: str, closes_at: str, is_closed: bool) -> None:
    if not is_closed and opens_at >= closes_at:
        raise HTTPException(status_code=400, detail="Opening time must be before closing time")


def is_barber_blocked(shop_id: int, barber_id: int, blocked_date: str, db: Session) -> bool:
    return (
        db.scalar(
            select(BarberBlockout).where(
                BarberBlockout.shop_id == shop_id,
                BarberBlockout.barber_id == barber_id,
                BarberBlockout.blocked_date == blocked_date,
            )
        )
        is not None
    )


def choose_fair_barber(shop_id: int, db: Session) -> BarberProfile | None:
    active_barbers = db.scalars(
        select(BarberProfile)
        .where(
            BarberProfile.shop_id == shop_id,
            BarberProfile.is_active.is_(True),
            BarberProfile.is_owner.is_(False),
        )
        .order_by(BarberProfile.created_at.asc())
    ).all()
    if not active_barbers:
        return None

    now = datetime.now(timezone.utc)
    appointment_counts = dict(
        db.execute(
            select(Appointment.barber_id, func.count(Appointment.id))
            .where(
                Appointment.shop_id == shop_id,
                Appointment.starts_at >= now,
                Appointment.status.in_(["pending_payment", "confirmed", "stripe_not_configured"]),
                Appointment.barber_id.is_not(None),
            )
            .group_by(Appointment.barber_id)
        ).all()
    )
    return min(active_barbers, key=lambda barber: (appointment_counts.get(barber.id, 0), barber.created_at))


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register_shop(
    payload: BarberShopRegister,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.email.lower() != payload.owner_email.lower():
        raise HTTPException(status_code=400, detail="Use the Google email currently signed in")
    existing_user = db.scalar(select(User).where(User.email == payload.owner_email, User.id != user.id))
    existing_shop = db.scalar(select(BarberShop).where(BarberShop.slug == payload.slug))
    if existing_user is not None or existing_shop is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user or shop with that email/slug already exists",
        )

    user.role = "owner"

    shop = BarberShop(
        owner_user_id=user.id,
        name=payload.name,
        slug=payload.slug,
        owner_email=payload.owner_email,
        timezone=payload.timezone,
    )
    db.add(shop)
    db.flush()

    owner_barber = BarberProfile(
        shop_id=shop.id,
        user_id=user.id,
        display_name=payload.owner_name,
        is_owner=True,
    )
    db.add(owner_barber)
    db.flush()

    db.add_all(
        [
            Service(
                shop_id=shop.id,
                barber_id=owner_barber.id,
                name="Classic Haircut",
                duration_minutes=30,
                price_cents=3000,
                booking_fee_cents=300,
                deposit_cents=200,
                platform_fee_cents=100,
            ),
            Service(
                shop_id=shop.id,
                barber_id=owner_barber.id,
                name="Haircut and Beard Trim",
                duration_minutes=45,
                price_cents=4500,
                booking_fee_cents=300,
                deposit_cents=200,
                platform_fee_cents=100,
            ),
        ]
    )
    db.add_all([BusinessHour(shop_id=shop.id, **hour.model_dump()) for hour in default_business_hours()])
    db.flush()

    session_id, setup_url = create_shop_setup_checkout(shop)
    shop.stripe_setup_checkout_session_id = session_id
    if not stripe_is_configured():
        shop.setup_payment_status = "stripe_not_configured"

    db.commit()
    db.refresh(shop)

    token = create_access_token(user)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 8,
    )

    return RegistrationResponse(
        shop=shop,
        setup_checkout_url=setup_url,
        setup_payment_required=True,
        stripe_setup_required=not stripe_is_configured(),
        message=(
            "Shop created. Redirecting to the one-time setup payment."
            if setup_url
            else "Shop created. Add STRIPE_SECRET_KEY to collect the $20 setup payment in local test mode."
        ),
    )


@router.post("/me/setup-checkout", response_model=ConnectLinkResponse)
def create_setup_payment_retry(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    if shop.setup_payment_status == "paid":
        return ConnectLinkResponse(message="Setup payment is already complete.")
    if not stripe_is_configured():
        return ConnectLinkResponse(
            stripe_setup_required=True,
            message="Add STRIPE_SECRET_KEY before collecting the shop setup payment.",
        )

    if is_paid_shop_setup_checkout(shop):
        shop.setup_payment_status = "paid"
        db.commit()
        return ConnectLinkResponse(message="Setup payment confirmed. Your shop is now published.")

    existing_checkout_url = get_open_shop_setup_checkout_url(shop)
    if existing_checkout_url:
        return ConnectLinkResponse(
            url=existing_checkout_url,
            message="Continue the existing setup payment instead of starting another one.",
        )

    session_id, setup_url = create_shop_setup_checkout(shop)
    shop.stripe_setup_checkout_session_id = session_id
    db.commit()
    return ConnectLinkResponse(url=setup_url, message="Continue to the one-time setup payment.")


@router.post("/me/monthly-access-checkout", response_model=ConnectLinkResponse)
def create_monthly_access_payment(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    if not stripe_is_configured():
        return ConnectLinkResponse(stripe_setup_required=True, message="Add STRIPE_SECRET_KEY before collecting this payment.")
    _, checkout_url = create_monthly_access_checkout(shop)
    return ConnectLinkResponse(url=checkout_url, message="Continue to the monthly access payment.")


@router.get("/me", response_model=DashboardResponse)
def get_my_shop(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    shop = get_owned_shop(user, db)
    return serialize_dashboard(user, shop, db)


@router.patch("/me/profile", response_model=DashboardResponse)
def update_shop_profile(
    payload: ShopProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    shop.name = payload.shop_name
    shop.timezone = payload.timezone
    shop.booking_window_days = max(30, payload.booking_window_days)
    shop.address_line1 = payload.address_line1
    shop.city = payload.city
    shop.state = payload.state
    shop.postal_code = payload.postal_code
    shop.latitude_microdegrees = to_microdegrees(payload.latitude)
    shop.longitude_microdegrees = to_microdegrees(payload.longitude)
    owner_barber = db.scalar(
        select(BarberProfile).where(
            BarberProfile.shop_id == shop.id,
            BarberProfile.user_id == user.id,
            BarberProfile.is_owner.is_(True),
        )
    )
    if owner_barber:
        owner_barber.display_name = payload.owner_display_name
    db.commit()
    db.refresh(shop)
    return serialize_dashboard(user, shop, db)


@router.post("/me/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    service_data = payload.model_dump()
    validate_service_amounts(service_data)
    assign_service_barber(service_data, shop, db)
    service_data["platform_fee_cents"] = hold_platform_fee_cents(service_data["booking_fee_cents"])
    service = Service(shop_id=shop.id, **service_data)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/me/services/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: int,
    payload: ServiceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    service = db.scalar(select(Service).where(Service.id == service_id, Service.shop_id == shop.id))
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    service_data = payload.model_dump()
    validate_service_amounts(service_data)
    assign_service_barber(service_data, shop, db)
    for key, value in service_data.items():
        setattr(service, key, value)
    service.platform_fee_cents = hold_platform_fee_cents(service.booking_fee_cents)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/me/services/{service_id}", response_model=DashboardResponse)
def remove_service(
    service_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hide a service from future booking while retaining its appointment history."""
    shop = get_owned_shop(user, db)
    service = db.scalar(select(Service).where(Service.id == service_id, Service.shop_id == shop.id))
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    service.is_active = False
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.put("/me/hours", response_model=DashboardResponse)
def update_business_hours(
    payload: BusinessHoursUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    if sorted(hour.day_of_week for hour in payload.hours) != list(range(7)):
        raise HTTPException(status_code=400, detail="Provide exactly one entry for each weekday")

    existing = {hour.day_of_week: hour for hour in get_ordered_business_hours(shop.id, db)}
    for hour_payload in payload.hours:
        validate_hour_window(hour_payload.opens_at, hour_payload.closes_at, hour_payload.is_closed)
        hour = existing[hour_payload.day_of_week]
        hour.opens_at = hour_payload.opens_at
        hour.closes_at = hour_payload.closes_at
        hour.is_closed = hour_payload.is_closed
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.put("/me/date-hours", response_model=DashboardResponse)
def upsert_date_hour_override(
    payload: DateHourOverrideUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    validate_hour_window(payload.opens_at, payload.closes_at, payload.is_closed)
    override = db.scalar(
        select(ShopDateHourOverride).where(
            ShopDateHourOverride.shop_id == shop.id,
            ShopDateHourOverride.specific_date == payload.specific_date,
        )
    )
    if override is None:
        override = ShopDateHourOverride(shop_id=shop.id, **payload.model_dump())
        db.add(override)
    else:
        override.opens_at = payload.opens_at
        override.closes_at = payload.closes_at
        override.is_closed = payload.is_closed
        override.note = payload.note
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.delete("/me/date-hours/{specific_date}", response_model=DashboardResponse)
def delete_date_hour_override(
    specific_date: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    override = db.scalar(
        select(ShopDateHourOverride).where(
            ShopDateHourOverride.shop_id == shop.id,
            ShopDateHourOverride.specific_date == specific_date,
        )
    )
    if override is not None:
        db.delete(override)
        db.commit()
    return serialize_dashboard(user, shop, db)


@router.post("/me/blockouts", response_model=DashboardResponse)
def toggle_blockout(
    payload: ToggleBlockoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    barber = db.scalar(
        select(BarberProfile).where(
            BarberProfile.id == payload.barber_id,
            BarberProfile.shop_id == shop.id,
            BarberProfile.is_active.is_(True),
        )
    )
    if barber is None:
        raise HTTPException(status_code=404, detail="Barber not found")

    blockout = db.scalar(
        select(BarberBlockout).where(
            BarberBlockout.shop_id == shop.id,
            BarberBlockout.barber_id == barber.id,
            BarberBlockout.blocked_date == payload.blocked_date,
        )
    )
    if payload.blocked and blockout is None:
        db.add(
            BarberBlockout(
                shop_id=shop.id,
                barber_id=barber.id,
                blocked_date=payload.blocked_date,
            )
        )
    if not payload.blocked and blockout is not None:
        db.delete(blockout)
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.post("/me/barbers", response_model=BarberRead, status_code=status.HTTP_201_CREATED)
def create_barber(
    payload: BarberCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    existing_barber = db.scalar(
        select(BarberProfile).where(
            BarberProfile.shop_id == shop.id,
            func.lower(BarberProfile.display_name) == payload.display_name.strip().lower(),
        )
    )
    if existing_barber is not None:
        state = "already active" if existing_barber.is_active else "was previously removed"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A barber named '{existing_barber.display_name}' {state}. Choose a different display name.",
        )
    barber_user = None
    if payload.email:
        barber_user = db.scalar(select(User).where(User.email == payload.email))
        if barber_user is None:
            barber_user = User(
                email=payload.email,
                password_hash=hash_password("temporary-password-change-me"),
                role="barber",
            )
            db.add(barber_user)
            db.flush()

    barber = BarberProfile(
        shop_id=shop.id,
        user_id=barber_user.id if barber_user else None,
        display_name=payload.display_name.strip(),
        bio=payload.bio,
        is_owner=False,
    )
    db.add(barber)
    db.flush()
    db.add_all(
        [
            Service(shop_id=shop.id, barber_id=barber.id, name="Classic Haircut", duration_minutes=30,
                    price_cents=3000, booking_fee_cents=300, deposit_cents=200, platform_fee_cents=100),
            Service(shop_id=shop.id, barber_id=barber.id, name="Haircut and Beard Trim", duration_minutes=45,
                    price_cents=4500, booking_fee_cents=300, deposit_cents=200, platform_fee_cents=100),
        ]
    )
    db.commit()
    db.refresh(barber)
    return barber


@router.patch("/me/barbers/{barber_id}", response_model=BarberRead)
def update_barber(
    barber_id: int,
    payload: BarberUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    barber = db.scalar(
        select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == shop.id)
    )
    if barber is None:
        raise HTTPException(status_code=404, detail="Barber not found")
    if barber.is_owner:
        raise HTTPException(status_code=400, detail="Edit the owner name in Shop profile.")
    barber.display_name = payload.display_name
    barber.bio = payload.bio
    db.commit()
    db.refresh(barber)
    return barber


@router.delete("/me/barbers/{barber_id}", response_model=DashboardResponse)
def delete_barber(
    barber_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    barber = db.scalar(
        select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == shop.id)
    )
    if barber is None:
        raise HTTPException(status_code=404, detail="Barber not found")
    if barber.is_owner:
        raise HTTPException(
            status_code=400,
            detail="The owner barber cannot be deleted from here. Closing the shop account is required.",
        )
    barber.is_active = False
    for service in db.scalars(
        select(Service).where(Service.shop_id == shop.id, Service.barber_id == barber.id)
    ):
        service.is_active = False
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.post("/me/manual-appointments", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
def create_manual_appointment(
    payload: ManualAppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    service = db.scalar(
        select(Service).where(
            Service.id == payload.service_id,
            Service.shop_id == shop.id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    barber = db.scalar(
        select(BarberProfile).where(
            BarberProfile.id == payload.barber_id,
            BarberProfile.shop_id == shop.id,
            BarberProfile.is_active.is_(True),
        )
    )
    if barber is None:
        raise HTTPException(status_code=404, detail="Barber not found")
    if service.barber_id is not None and service.barber_id != barber.id:
        raise HTTPException(status_code=400, detail="Select a service offered by this barber")

    starts_at = utc_naive(payload.starts_at)
    local_date = starts_at.replace(tzinfo=timezone.utc).astimezone(shop_timezone(shop)).date().isoformat()
    if is_barber_blocked(shop.id, barber.id, local_date, db):
        raise HTTPException(status_code=409, detail="That barber is blocked out on this date")
    if has_appointment_overlap(shop.id, starts_at, service.duration_minutes, db, barber.id):
        raise HTTPException(status_code=409, detail="That time overlaps an existing appointment")

    appointment = Appointment(
        shop_id=shop.id,
        service_id=service.id,
        barber_id=barber.id,
        payout_stripe_account_id=select_payout_account(shop, barber),
        client_phone=payload.client_phone,
        client_name=payload.client_name or "Manual block",
        starts_at=starts_at,
        status="manual_block",
        payment_option="manual",
        amount_collected_cents=0,
        booking_fee_cents=0,
        deposit_cents=0,
        platform_fee_cents=0,
    )
    db.add(appointment)
    db.commit()
    return serialize_dashboard(user, shop, db)


@router.post("/me/logo")
def upload_shop_logo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPG, or WebP image")

    data = file.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be 2 MB or smaller")

    try:
        image = Image.open(BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    width, height = image.size
    if width < MIN_LOGO_SIZE[0] or height < MIN_LOGO_SIZE[1]:
        raise HTTPException(status_code=400, detail="Logo must be at least 256x256")

    UPLOAD_DIR.mkdir(exist_ok=True)
    extension = ALLOWED_IMAGE_TYPES[content_type]
    path = UPLOAD_DIR / f"shop-{shop.id}-logo{extension}"
    path.write_bytes(data)
    shop.logo_path = str(path)
    db.commit()
    return {"logo_path": shop.logo_path}


@router.post("/me/connect", response_model=ConnectLinkResponse)
def create_shop_connect_link(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    if not stripe_is_configured():
        return ConnectLinkResponse(
            stripe_setup_required=True,
            message="Add STRIPE_SECRET_KEY before starting Stripe Connect onboarding.",
        )

    if not shop.stripe_account_id:
        try:
            shop.stripe_account_id = create_connected_account(shop.owner_email, shop.name)
        except StripeConfigurationError as exc:
            return ConnectLinkResponse(
                stripe_setup_required=True,
                message=f"Stripe Connect is not ready: {exc}",
            )
        db.commit()
        db.refresh(shop)
    else:
        try:
            account_ready, account_message = retrieve_connected_account_status(shop.stripe_account_id)
        except StripeConfigurationError as exc:
            return ConnectLinkResponse(
                stripe_setup_required=True,
                message=f"Stripe Connect account could not be checked: {exc}",
            )
        if account_ready:
            shop.stripe_onboarding_complete = True
            db.commit()
            return ConnectLinkResponse(message="Owner payout account is ready.")

    try:
        url = create_account_link(shop.stripe_account_id)
    except StripeConfigurationError as exc:
        return ConnectLinkResponse(
            stripe_setup_required=True,
            message=f"Stripe Connect onboarding could not be started: {exc}",
        )
    return ConnectLinkResponse(url=url, message="Continue Stripe onboarding.")


@router.post("/me/barbers/{barber_id}/connect", response_model=ConnectLinkResponse)
def create_barber_connect_link(
    barber_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shop = get_owned_shop(user, db)
    barber = db.scalar(
        select(BarberProfile).where(BarberProfile.id == barber_id, BarberProfile.shop_id == shop.id)
    )
    if barber is None:
        raise HTTPException(status_code=404, detail="Barber not found")
    if not stripe_is_configured():
        return ConnectLinkResponse(
            stripe_setup_required=True,
            message="Add STRIPE_SECRET_KEY before starting Stripe Connect onboarding.",
        )

    if not barber.stripe_account_id:
        try:
            barber.stripe_account_id = create_connected_account(shop.owner_email, f"{shop.name} - {barber.display_name}")
        except StripeConfigurationError as exc:
            return ConnectLinkResponse(
                stripe_setup_required=True,
                message=f"Stripe Connect is not ready: {exc}",
            )
        db.commit()
        db.refresh(barber)
    else:
        try:
            account_ready, account_message = retrieve_connected_account_status(barber.stripe_account_id)
        except StripeConfigurationError as exc:
            return ConnectLinkResponse(
                stripe_setup_required=True,
                message=f"Stripe Connect account could not be checked: {exc}",
            )
        if account_ready:
            barber.stripe_onboarding_complete = True
            db.commit()
            return ConnectLinkResponse(message="Barber payout account is ready.")

    try:
        url = create_account_link(barber.stripe_account_id)
    except StripeConfigurationError as exc:
        return ConnectLinkResponse(
            stripe_setup_required=True,
            message=f"Stripe Connect onboarding could not be started: {exc}",
        )
    return ConnectLinkResponse(url=url, message="Continue barber Stripe onboarding.")


@router.get("", response_model=list[ShopDiscoveryRead])
def discover_shops(
    lat: float | None = None,
    lng: float | None = None,
    max_distance_miles: int = Query(default=25, ge=1, le=500),
    db: Session = Depends(get_db),
):
    shops = db.scalars(select(BarberShop).order_by(BarberShop.name.asc())).all()
    rows: list[ShopDiscoveryRead] = []
    for shop in shops:
        if is_platform_admin(shop.owner):
            continue
        if not shop_is_publishable(shop):
            continue
        service_name = db.scalar(
            select(Service.name)
            .where(Service.shop_id == shop.id, Service.is_active.is_(True))
            .order_by(Service.name.asc())
            .limit(1)
        )
        if service_name is None:
            continue
        shop_distance = distance_miles(
            lat,
            lng,
            shop.latitude_microdegrees,
            shop.longitude_microdegrees,
        )
        if lat is not None and lng is not None and shop_distance is not None and shop_distance > max_distance_miles:
            continue
        rows.append(
            ShopDiscoveryRead(
                id=shop.id,
                name=shop.name,
                slug=shop.slug,
                city=shop.city,
                state=shop.state,
                address_line1=shop.address_line1,
                distance_miles=shop_distance,
                next_service_name=service_name,
            )
        )

    return sorted(
        rows,
        key=lambda row: (
            row.distance_miles is None,
            row.distance_miles if row.distance_miles is not None else 0,
            row.name.lower(),
        ),
    )[:20]


@router.get("/{shop_slug}", response_model=ShopPublicResponse)
def get_public_shop(shop_slug: str, db: Session = Depends(get_db)):
    shop = db.scalar(select(BarberShop).where(BarberShop.slug == shop_slug))
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if not shop_is_publishable(shop):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop is not published yet")

    all_services = list(db.scalars(
        select(Service)
        .outerjoin(BarberProfile, BarberProfile.id == Service.barber_id)
        .where(Service.shop_id == shop.id, Service.is_active.is_(True))
        .order_by(Service.name.asc(), BarberProfile.is_owner.desc(), Service.id.asc())
    ).all())
    services = unique_public_services(all_services)
    barbers = db.scalars(
        select(BarberProfile)
        .where(BarberProfile.shop_id == shop.id, BarberProfile.is_active.is_(True))
        .order_by(BarberProfile.is_owner.desc(), BarberProfile.display_name.asc())
    ).all()
    return ShopPublicResponse(
        shop=shop,
        services=list(services),
        barbers=list(barbers),
        business_hours=get_ordered_business_hours(shop.id, db),
        date_hour_overrides=get_date_hour_overrides(shop.id, db),
    )


@router.get("/{shop_slug}/slots", response_model=ShopSlotsResponse)
def get_shop_slots(
    shop_slug: str,
    service_id: int | None = None,
    selected_date: date | None = None,
    barber_id: int | None = None,
    db: Session = Depends(get_db),
):
    shop = db.scalar(select(BarberShop).where(BarberShop.slug == shop_slug))
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if not shop_is_publishable(shop):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop is not published yet")

    all_services = list(db.scalars(
        select(Service)
        .outerjoin(BarberProfile, BarberProfile.id == Service.barber_id)
        .where(Service.shop_id == shop.id, Service.is_active.is_(True))
        .order_by(Service.name.asc(), BarberProfile.is_owner.desc(), Service.id.asc())
    ).all())
    services = unique_public_services(all_services)
    if not services:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No services configured")

    service = next((item for item in services if item.id == service_id), services[0])
    barbers = db.scalars(
        select(BarberProfile)
        .where(BarberProfile.shop_id == shop.id, BarberProfile.is_active.is_(True))
        .order_by(BarberProfile.is_owner.desc(), BarberProfile.display_name.asc())
    ).all()
    if barber_id is not None and not any(barber.id == barber_id for barber in barbers):
        raise HTTPException(status_code=404, detail="Barber not found")
    recommended_barber = choose_fair_barber(shop.id, db)
    slots = build_available_slots(shop, service, db, selected_date, barber_id)

    return ShopSlotsResponse(
        shop_id=shop.id,
        shop_slug=shop.slug,
        shop_name=shop.name,
        shop=shop,
        service=service,
        services=list(services),
        barbers=list(barbers),
        business_hours=get_ordered_business_hours(shop.id, db),
        date_hour_overrides=get_date_hour_overrides(shop.id, db),
        recommended_barber=recommended_barber,
        slots=slots,
    )


@router.post("/{shop_slug}/appointments", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
def create_booking_checkout(
    shop_slug: str,
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
):
    shop = db.scalar(select(BarberShop).where(BarberShop.slug == shop_slug))
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    if not shop_is_publishable(shop):
        raise HTTPException(status_code=404, detail="Shop is not published yet")
    sync_shop_access(shop, db)
    if shop.access_suspended:
        raise HTTPException(status_code=403, detail="This shop's access is currently paused. Contact platform support.")
    if payload.sms_opt_in and not payload.client_phone:
        raise HTTPException(status_code=400, detail="Provide a phone number or choose not to receive text updates")
    if not payload.sms_opt_in and not payload.client_name:
        raise HTTPException(status_code=400, detail="Provide your name when you choose not to share a phone number")

    service = db.scalar(
        select(Service).where(
            Service.id == payload.service_id,
            Service.shop_id == shop.id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")

    local_start_date = payload.starts_at.astimezone(shop_timezone(shop)).date()
    available_slots = build_available_slots(
        shop=shop,
        service=service,
        db=db,
        selected_date=local_start_date,
        barber_id=payload.barber_id,
    )
    if payload.starts_at not in {slot.starts_at for slot in available_slots}:
        raise HTTPException(status_code=409, detail="That time is no longer available")

    assignment = assign_available_service_provider(
        shop, service, payload.starts_at, db, barber_id=payload.barber_id,
    )
    if assignment is None:
        raise HTTPException(status_code=409, detail="That time is no longer available")
    service, barber = assignment

    conflict_query = select(Appointment).where(
        Appointment.shop_id == shop.id,
        Appointment.starts_at == payload.starts_at,
        Appointment.status.in_(appointment_statuses_that_hold_time()),
    )
    if barber:
        conflict_query = conflict_query.where(Appointment.barber_id == barber.id)
    existing_appointment = db.scalar(conflict_query)
    if existing_appointment is not None:
        raise HTTPException(status_code=409, detail="That time is no longer available")

    payout_account_id = select_payout_account(shop, barber)
    if not payout_account_id and stripe_is_configured():
        raise HTTPException(
            status_code=409,
            detail="This shop or selected barber must complete Stripe onboarding before accepting bookings",
        )
    if payout_account_id and stripe_is_configured():
        try:
            account_ready, account_message = retrieve_connected_account_status(payout_account_id)
        except StripeConfigurationError as exc:
            raise HTTPException(status_code=409, detail=f"Stripe payout account could not be checked: {exc}") from exc
        if not account_ready:
            raise HTTPException(status_code=409, detail=account_message)

    amount_collected_cents = (
        service.price_cents if payload.payment_option == "pay_in_full" else service.booking_fee_cents
    )
    normal_platform_fee_cents = 100 if payload.payment_option == "pay_in_full" else hold_platform_fee_cents(service.booking_fee_cents)
    platform_fee_cents = capped_platform_fee(shop.id, normal_platform_fee_cents, db)
    if amount_collected_cents <= platform_fee_cents:
        raise HTTPException(
            status_code=400,
            detail="Payment amount must be greater than the platform fee",
        )

    if not stripe_is_configured():
        raise HTTPException(status_code=503, detail="Stripe must be configured before accepting bookings")

    checkout_attempt = CheckoutAttempt(
        shop_id=shop.id,
        service_id=service.id,
        barber_id=barber.id if barber else None,
        payout_stripe_account_id=payout_account_id,
        client_phone=payload.client_phone or "Not shared",
        client_name=payload.client_name,
        sms_opt_in=payload.sms_opt_in,
        starts_at=payload.starts_at,
        payment_option=payload.payment_option,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=CHECKOUT_ATTEMPT_EXPIRY_MINUTES),
        amount_collected_cents=amount_collected_cents,
        booking_fee_cents=service.booking_fee_cents,
        deposit_cents=service.deposit_cents,
        platform_fee_cents=platform_fee_cents,
    )
    db.add(checkout_attempt)
    db.flush()

    try:
        session_id, checkout_url = create_stripe_booking_checkout(
            shop=shop,
            service=service,
            checkout_attempt=checkout_attempt,
            payout_account_id=payout_account_id,
        )
    except StripeConfigurationError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Stripe Checkout could not be created: {exc}") from exc

    checkout_attempt.stripe_checkout_session_id = session_id
    db.commit()
    db.refresh(checkout_attempt)

    return CheckoutResponse(
        checkout_attempt_id=checkout_attempt.id,
        checkout_url=checkout_url,
        stripe_setup_required=False,
        message="Redirect the client to Stripe Checkout.",
    )
