from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import BarberProfile, BarberShop, BusinessHour, Service, User
from .security import hash_password


def seed_demo_shop() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        demo = db.scalar(select(BarberShop).where(BarberShop.slug == "demo-cuts"))
        if demo is not None:
            demo.address_line1 = "100 Main Street"
            demo.city = "Bakersfield"
            demo.state = "CA"
            demo.postal_code = "93301"
            demo.latitude_microdegrees = 35373292
            demo.longitude_microdegrees = -119018713
            demo.location_country_code = "US"
            demo.location_county = "Kern County"
            demo.location_verified = True
            db.commit()
            return

        user = User(
            email="owner@democuts.example.com",
            password_hash=hash_password("password1234"),
            role="owner",
        )
        db.add(user)
        db.flush()

        shop = BarberShop(
            owner_user_id=user.id,
            name="Demo Cuts",
            slug="demo-cuts",
            owner_email=user.email,
            timezone="America/Los_Angeles",
            setup_payment_status="demo",
            address_line1="100 Main Street",
            city="Bakersfield",
            state="CA",
            postal_code="93301",
            latitude_microdegrees=35373292,
            longitude_microdegrees=-119018713,
            location_country_code="US",
            location_county="Kern County",
            location_verified=True,
        )
        db.add(shop)
        db.flush()

        db.add_all(
            [
                BarberProfile(
                    shop_id=shop.id,
                    user_id=user.id,
                    display_name="Owner Barber",
                    is_owner=True,
                ),
                BarberProfile(
                    shop_id=shop.id,
                    display_name="Guest Chair",
                    bio="A second barber profile showing payout routing.",
                ),
            ]
        )

        db.add_all(
            [
                Service(
                    shop_id=shop.id,
                    name="Classic Haircut",
                    duration_minutes=30,
                    price_cents=3000,
                    booking_fee_cents=300,
                    deposit_cents=200,
                    platform_fee_cents=100,
                ),
                Service(
                    shop_id=shop.id,
                    name="Haircut and Beard Trim",
                    duration_minutes=45,
                    price_cents=4500,
                    booking_fee_cents=300,
                    deposit_cents=200,
                    platform_fee_cents=100,
                ),
            ]
        )

        db.add_all(
            [
                BusinessHour(
                    shop_id=shop.id,
                    day_of_week=day,
                    opens_at="09:00",
                    closes_at="17:00",
                    is_closed=day == 6,
                )
                for day in range(7)
            ]
        )
        db.commit()
    finally:
        db.close()
