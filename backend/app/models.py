from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="owner")
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    barber_profiles: Mapped[list["BarberProfile"]] = relationship(back_populates="user")
    owned_shops: Mapped[list["BarberShop"]] = relationship(back_populates="owner")


class BarberShop(Base):
    __tablename__ = "barber_shops"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    setup_payment_status: Mapped[str] = mapped_column(String(40), default="pending")
    stripe_setup_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hero_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(160), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude_microdegrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    longitude_microdegrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="America/Los_Angeles")
    booking_window_days: Mapped[int] = mapped_column(Integer, default=30)
    admin_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_warning_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    access_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_access_paid_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="owned_shops")
    barbers: Mapped[list["BarberProfile"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )
    services: Mapped[list["Service"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )
    business_hours: Mapped[list["BusinessHour"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )
    date_hour_overrides: Mapped[list["ShopDateHourOverride"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )


class BarberProfile(Base):
    __tablename__ = "barber_profiles"
    __table_args__ = (
        UniqueConstraint("shop_id", "display_name", name="uq_barbers_shop_id_display_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shop: Mapped["BarberShop"] = relationship(back_populates="barbers")
    user: Mapped["User | None"] = relationship(back_populates="barber_profiles")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="barber")
    blockouts: Mapped[list["BarberBlockout"]] = relationship(
        back_populates="barber",
        cascade="all, delete-orphan",
    )


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("shop_id", "barber_id", "name", name="uq_services_shop_barber_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barber_profiles.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    price_cents: Mapped[int] = mapped_column(Integer, default=3000)
    booking_fee_cents: Mapped[int] = mapped_column(Integer, default=300)
    deposit_cents: Mapped[int] = mapped_column(Integer, default=200)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    shop: Mapped["BarberShop"] = relationship(back_populates="services")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")
    barber: Mapped["BarberProfile | None"] = relationship()


class BusinessHour(Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        UniqueConstraint("shop_id", "day_of_week", name="uq_business_hours_shop_id_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[str] = mapped_column(String(5), default="09:00")
    closes_at: Mapped[str] = mapped_column(String(5), default="17:00")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    shop: Mapped["BarberShop"] = relationship(back_populates="business_hours")


class ShopDateHourOverride(Base):
    __tablename__ = "shop_date_hour_overrides"
    __table_args__ = (
        UniqueConstraint("shop_id", "specific_date", name="uq_shop_date_hour_overrides_shop_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    specific_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    opens_at: Mapped[str] = mapped_column(String(5), default="09:00")
    closes_at: Mapped[str] = mapped_column(String(5), default="17:00")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shop: Mapped["BarberShop"] = relationship(back_populates="date_hour_overrides")


class BarberBlockout(Base):
    __tablename__ = "barber_blockouts"
    __table_args__ = (
        UniqueConstraint("barber_id", "blocked_date", name="uq_barber_blockouts_barber_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barber_profiles.id"), index=True, nullable=False)
    blocked_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    barber: Mapped["BarberProfile"] = relationship(back_populates="blockouts")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True, nullable=False)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barber_profiles.id"), index=True, nullable=True)
    payout_stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending_payment")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_option: Mapped[str] = mapped_column(String(40), default="hold_fee")
    amount_collected_cents: Mapped[int] = mapped_column(Integer, default=300)
    booking_fee_cents: Mapped[int] = mapped_column(Integer, default=300)
    deposit_cents: Mapped[int] = mapped_column(Integer, default=200)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, default=100)
    stripe_processing_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shop: Mapped["BarberShop"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments")
    barber: Mapped["BarberProfile | None"] = relationship(back_populates="appointments")


class ClientNote(Base):
    __tablename__ = "client_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barber_profiles.id"), index=True, nullable=False)
    client_key: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckoutAttempt(Base):
    """A Stripe checkout audit record. This is never a scheduled appointment."""

    __tablename__ = "checkout_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("barber_shops.id"), index=True, nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True, nullable=False)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barber_profiles.id"), index=True, nullable=True)
    payout_stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    payment_option: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_collected_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    booking_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_processing_fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="checkout_started")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
