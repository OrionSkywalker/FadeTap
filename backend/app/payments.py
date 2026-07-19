import os
from datetime import timezone

import stripe

from .models import BarberProfile, BarberShop, CheckoutAttempt, Service

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
SETUP_FEE_CENTS = int(os.getenv("SHOP_SETUP_FEE_CENTS", "2000"))


class StripeConfigurationError(RuntimeError):
    pass


def stripe_error_message(exc: stripe.StripeError) -> str:
    user_message = getattr(exc, "user_message", None)
    return user_message or str(exc)


def describe_requirement(requirement: str) -> str:
    labels = {
        "business_profile.mcc": "business category",
        "business_profile.url": "business website or profile URL",
        "business_type": "business type",
        "external_account": "bank account or debit card for payouts",
        "representative.dob.day": "representative date of birth",
        "representative.dob.month": "representative date of birth",
        "representative.dob.year": "representative date of birth",
        "representative.email": "representative email",
        "representative.first_name": "representative first name",
        "representative.last_name": "representative last name",
        "tos_acceptance.date": "terms of service acceptance",
        "tos_acceptance.ip": "terms of service acceptance",
    }
    return labels.get(requirement, requirement.replace("_", " ").replace(".", " "))


def describe_requirements(requirements: list[str]) -> str:
    readable = []
    for requirement in requirements:
        label = describe_requirement(requirement)
        if label not in readable:
            readable.append(label)
    return ", ".join(readable)


def stripe_is_configured() -> bool:
    return bool(stripe.api_key and stripe.api_key.startswith("sk_"))


def create_shop_setup_checkout(shop: BarberShop) -> tuple[str | None, str | None]:
    if not stripe_is_configured():
        return None, None

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        customer_email=shop.owner_email,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "FadeTap shop setup"},
                    "unit_amount": SETUP_FEE_CENTS,
                },
                "quantity": 1,
            }
        ],
        metadata={"shop_id": str(shop.id), "purpose": "shop_setup"},
        success_url=f"{APP_BASE_URL}/dashboard?setup=paid",
        cancel_url=f"{APP_BASE_URL}/dashboard?setup=cancelled",
    )
    return session.id, session.url


def create_connected_account(email: str, business_name: str) -> str | None:
    if not stripe_is_configured():
        return None

    try:
        account = stripe.Account.create(
            type="express",
            country="US",
            email=email,
            business_profile={"name": business_name},
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )
    except stripe.StripeError as exc:
        raise StripeConfigurationError(stripe_error_message(exc)) from exc
    return account.id


def create_account_link(account_id: str) -> str | None:
    if not stripe_is_configured():
        return None

    try:
        link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=f"{APP_BASE_URL}/dashboard?stripe=refresh",
            return_url=f"{APP_BASE_URL}/dashboard?stripe=return",
            type="account_onboarding",
        )
    except stripe.StripeError as exc:
        raise StripeConfigurationError(stripe_error_message(exc)) from exc
    return link.url


def retrieve_connected_account_status(account_id: str) -> tuple[bool, str]:
    if not stripe_is_configured():
        return False, "Stripe is not configured."

    try:
        account = stripe.Account.retrieve(account_id)
    except stripe.StripeError as exc:
        raise StripeConfigurationError(stripe_error_message(exc)) from exc

    capabilities = account.get("capabilities") or {}
    transfers_active = capabilities.get("transfers") == "active"
    payouts_enabled = bool(account.get("payouts_enabled"))
    details_submitted = bool(account.get("details_submitted"))

    if transfers_active and payouts_enabled and details_submitted:
        return True, "Connected account is ready for payouts."

    requirements = account.get("requirements") or {}
    currently_due = requirements.get("currently_due") or []
    if currently_due:
        missing = describe_requirements(currently_due)
        return False, f"Stripe onboarding is incomplete. Missing: {missing}. Click Set up owner payouts in the dashboard to continue."
    return False, "Stripe has not activated transfers for this connected account yet. Finish onboarding or wait for Stripe to activate the account."


def select_payout_account(shop: BarberShop, barber: BarberProfile | None) -> str | None:
    if barber and barber.stripe_account_id:
        return barber.stripe_account_id
    return shop.stripe_account_id


def create_booking_checkout(
    shop: BarberShop,
    service: Service,
    checkout_attempt: CheckoutAttempt,
    payout_account_id: str,
) -> tuple[str | None, str | None]:
    if not stripe_is_configured():
        return None, None

    if checkout_attempt.payment_option == "pay_in_full":
        product_name = f"{shop.name} {service.name} prepaid"
        checkout_amount_cents = service.price_cents
    else:
        product_name = f"{shop.name} booking hold fee"
        checkout_amount_cents = service.booking_fee_cents

    try:
        expires_at = checkout_attempt.expires_at
        session = stripe.checkout.Session.create(
            mode="payment",
            expires_at=int(expires_at.replace(tzinfo=timezone.utc).timestamp()) if expires_at else None,
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": product_name},
                        "unit_amount": checkout_amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            payment_intent_data={
                "transfer_data": {"destination": payout_account_id},
                "metadata": {
                    "checkout_attempt_id": str(checkout_attempt.id),
                    "shop_id": str(shop.id),
                    "service_id": str(service.id),
                    "payment_option": checkout_attempt.payment_option,
                    "non_refundable": "true",
                },
            } | ({"application_fee_amount": checkout_attempt.platform_fee_cents} if checkout_attempt.platform_fee_cents else {}),
            metadata={
                "checkout_attempt_id": str(checkout_attempt.id),
                "shop_id": str(shop.id),
                "purpose": "booking_fee",
                "payment_option": checkout_attempt.payment_option,
            },
            success_url=f"{APP_BASE_URL}/book/{shop.slug}?booking=success",
            cancel_url=f"{APP_BASE_URL}/book/{shop.slug}?booking=cancelled",
        )
    except stripe.StripeError as exc:
        raise StripeConfigurationError(stripe_error_message(exc)) from exc
    return session.id, session.url


def create_monthly_access_checkout(shop: BarberShop) -> tuple[str | None, str | None]:
    if not stripe_is_configured():
        return None, None
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd", "product_data": {"name": f"{shop.name} monthly platform access"}, "unit_amount": 2500}, "quantity": 1}],
            metadata={"shop_id": str(shop.id), "purpose": "monthly_access"},
            success_url=f"{APP_BASE_URL}/dashboard?access=paid",
            cancel_url=f"{APP_BASE_URL}/dashboard?access=cancelled",
        )
    except stripe.StripeError as exc:
        raise StripeConfigurationError(stripe_error_message(exc)) from exc
    return session.id, session.url
