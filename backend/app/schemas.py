from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ServiceBase(BaseModel):
    barber_id: int | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    duration_minutes: int = Field(default=30, ge=10, le=240)
    price_cents: int = Field(default=3000, ge=0)
    booking_fee_cents: int = Field(default=300, ge=100)
    deposit_cents: int = Field(default=200, ge=0)
    platform_fee_cents: int = Field(default=100, ge=0)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    is_active: bool = True


class ServiceRead(ServiceBase):
    id: int
    shop_id: int
    is_active: bool

    model_config = {"from_attributes": True}


class BarberCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    bio: str | None = None
    email: EmailStr | None = None


class BarberUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    bio: str | None = None


class BarberRead(BaseModel):
    id: int
    shop_id: int
    display_name: str
    bio: str | None = None
    stripe_account_id: str | None = None
    stripe_onboarding_complete: bool
    is_owner: bool
    is_active: bool

    model_config = {"from_attributes": True}


class BarberClientRead(BaseModel):
    client_key: str
    client_name: str | None = None
    client_phone: str | None = None
    sms_opt_in: bool
    total_appointments: int
    last_appointment_at: datetime
    next_appointment_at: datetime | None = None
    last_service_name: str | None = None
    notes: list[str] = []


class ClientNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class BarberShopRegister(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9-]+$")
    owner_name: str = Field(min_length=2, max_length=120)
    owner_email: EmailStr
    timezone: str = "America/Los_Angeles"


class BarberShopRead(BaseModel):
    id: int
    name: str
    slug: str
    owner_email: EmailStr
    stripe_account_id: str | None = None
    stripe_onboarding_complete: bool
    setup_payment_status: str
    logo_path: str | None = None
    hero_image_path: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    latitude_microdegrees: int | None = None
    longitude_microdegrees: int | None = None
    timezone: str
    booking_window_days: int
    admin_message: str | None = None
    access_warning_month: str | None = None
    access_suspended: bool = False
    monthly_access_paid_month: str | None = None

    model_config = {"from_attributes": True}


class ShopProfileUpdate(BaseModel):
    shop_name: str = Field(min_length=2, max_length=120)
    owner_display_name: str = Field(min_length=2, max_length=120)
    timezone: str = "America/Los_Angeles"
    booking_window_days: int = Field(default=30, ge=30, le=365)
    address_line1: str | None = Field(default=None, max_length=160)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=40)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class BusinessHourBase(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    opens_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    closes_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    is_closed: bool = False


class BusinessHourRead(BusinessHourBase):
    id: int
    shop_id: int

    model_config = {"from_attributes": True}


class BusinessHoursUpdate(BaseModel):
    hours: list[BusinessHourBase] = Field(min_length=7, max_length=7)


class DateHourOverrideBase(BaseModel):
    specific_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    opens_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    closes_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    is_closed: bool = False
    note: str | None = Field(default=None, max_length=255)


class DateHourOverrideRead(DateHourOverrideBase):
    id: int
    shop_id: int

    model_config = {"from_attributes": True}


class DateHourOverrideUpsert(DateHourOverrideBase):
    pass


class RegistrationResponse(BaseModel):
    shop: BarberShopRead
    setup_checkout_url: str | None = None
    setup_payment_required: bool = True
    stripe_setup_required: bool = False
    message: str


class DashboardResponse(BaseModel):
    user: UserRead
    shop: BarberShopRead
    barbers: list[BarberRead]
    services: list[ServiceRead]
    business_hours: list[BusinessHourRead]
    date_hour_overrides: list[DateHourOverrideRead]
    upcoming_appointments: list["AppointmentCalendarRead"]
    blockouts: list["BarberBlockoutRead"]
    platform_fees_this_month_cents: int = 0
    previous_month_platform_fees_cents: int = 0
    monthly_platform_fee_target_cents: int = 2500
    unread_admin_message: str | None = None


class AppointmentCreate(BaseModel):
    service_id: int
    starts_at: datetime
    client_phone: str | None = Field(default=None, max_length=32)
    client_name: str | None = Field(default=None, max_length=120)
    sms_opt_in: bool = True
    barber_id: int | None = None
    payment_option: str = Field(default="hold_fee", pattern=r"^(hold_fee|pay_in_full)$")


class ManualAppointmentCreate(BaseModel):
    service_id: int
    starts_at: datetime
    barber_id: int
    client_name: str | None = Field(default="Manual block", max_length=120)
    client_phone: str = Field(default="manual", max_length=32)


class AppointmentRead(BaseModel):
    id: int
    shop_id: int
    service_id: int
    barber_id: int | None = None
    client_phone: str
    client_name: str | None = None
    sms_opt_in: bool = True
    starts_at: datetime
    status: str
    stripe_checkout_session_id: str | None = None
    stripe_payment_intent_id: str | None = None
    payment_option: str
    amount_collected_cents: int
    booking_fee_cents: int
    deposit_cents: int
    platform_fee_cents: int
    stripe_processing_fee_cents: int = 0

    model_config = {"from_attributes": True}


class AppointmentCalendarRead(AppointmentRead):
    service_name: str
    barber_name: str | None = None


class BarberBlockoutRead(BaseModel):
    id: int
    shop_id: int
    barber_id: int
    blocked_date: str
    reason: str | None = None

    model_config = {"from_attributes": True}


class ToggleBlockoutRequest(BaseModel):
    barber_id: int
    blocked_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    blocked: bool = True


class CheckoutResponse(BaseModel):
    checkout_attempt_id: int
    checkout_url: str | None = None
    stripe_setup_required: bool = False
    message: str


class ConnectLinkResponse(BaseModel):
    url: str | None = None
    stripe_setup_required: bool = False
    message: str


class SlotRead(BaseModel):
    starts_at: datetime
    label: str
    date: str
    barber_id: int | None = None


class ShopPublicResponse(BaseModel):
    shop: BarberShopRead
    services: list[ServiceRead]
    barbers: list[BarberRead]
    business_hours: list[BusinessHourRead]
    date_hour_overrides: list[DateHourOverrideRead]


class ShopDiscoveryRead(BaseModel):
    id: int
    name: str
    slug: str
    city: str | None = None
    state: str | None = None
    address_line1: str | None = None
    distance_miles: float | None = None
    next_service_name: str | None = None
    service_names: list[str] = []
    provider_names: list[str] = []


class ShopDiscoveryOption(BaseModel):
    slug: str
    label: str


class ShopDiscoveryFilters(BaseModel):
    shops: list[ShopDiscoveryOption]
    cities: list[str]
    states: list[str]
    services: list[str]


class ShopSlotsResponse(BaseModel):
    shop_id: int
    shop_slug: str
    shop_name: str
    shop: BarberShopRead
    service: ServiceRead
    services: list[ServiceRead]
    barbers: list[BarberRead]
    business_hours: list[BusinessHourRead]
    date_hour_overrides: list[DateHourOverrideRead]
    recommended_barber: BarberRead | None = None
    slots: list[SlotRead]
