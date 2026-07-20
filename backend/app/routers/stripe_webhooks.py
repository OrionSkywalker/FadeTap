import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Appointment, BarberProfile, BarberShop, CheckoutAttempt, Service
from ..payments import get_payment_processing_fee_cents

router = APIRouter(prefix="/api/stripe", tags=["stripe"])


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc
    else:
        event = stripe.Event.construct_from(await request.json(), stripe.api_key)

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        # A Checkout Session can complete while a delayed payment remains unpaid.
        # Never publish a shop or appointment until Stripe reports available funds.
        if data.get("payment_status") != "paid":
            return {"received": True}

        metadata = data.get("metadata", {})
        purpose = metadata.get("purpose")

        if purpose == "shop_setup":
            shop = db.scalar(select(BarberShop).where(BarberShop.id == int(metadata["shop_id"])))
            if shop:
                shop.setup_payment_status = "paid"
                shop.stripe_setup_checkout_session_id = data.get("id")

        if purpose == "monthly_access":
            shop = db.scalar(select(BarberShop).where(BarberShop.id == int(metadata["shop_id"])))
            if shop:
                shop.monthly_access_paid_month = datetime.now(timezone.utc).strftime("%Y-%m")
                shop.access_warning_month = None
                shop.access_suspended = False

        if purpose == "booking_fee":
            attempt = db.scalar(
                select(CheckoutAttempt).where(CheckoutAttempt.id == int(metadata["checkout_attempt_id"]))
            )
            if attempt and attempt.status == "checkout_started":
                processing_fee_cents = get_payment_processing_fee_cents(data.get("payment_intent"))
                if processing_fee_cents is not None:
                    attempt.stripe_processing_fee_cents = processing_fee_cents
                service = db.scalar(select(Service).where(Service.id == attempt.service_id, Service.shop_id == attempt.shop_id))
                overlapping = False
                if service:
                    candidate_end = attempt.starts_at + timedelta(minutes=service.duration_minutes)
                    statement = (
                        select(Appointment.starts_at, Service.duration_minutes)
                        .join(Service, Service.id == Appointment.service_id)
                        .where(
                            Appointment.shop_id == attempt.shop_id,
                            Appointment.status.in_(["confirmed", "manual_block"]),
                            Appointment.starts_at < candidate_end,
                        )
                    )
                    if attempt.barber_id is not None:
                        statement = statement.where(Appointment.barber_id == attempt.barber_id)
                    for existing_start, existing_duration in db.execute(statement).all():
                        if attempt.starts_at < existing_start + timedelta(minutes=existing_duration):
                            overlapping = True
                            break
                if service and not overlapping:
                    appointment = Appointment(
                        shop_id=attempt.shop_id,
                        service_id=attempt.service_id,
                        barber_id=attempt.barber_id,
                        payout_stripe_account_id=attempt.payout_stripe_account_id,
                        client_phone=attempt.client_phone,
                        client_name=attempt.client_name,
                        sms_opt_in=attempt.sms_opt_in,
                        starts_at=attempt.starts_at,
                        status="confirmed",
                        stripe_checkout_session_id=data.get("id"),
                        stripe_payment_intent_id=data.get("payment_intent"),
                        payment_option=attempt.payment_option,
                        amount_collected_cents=attempt.amount_collected_cents,
                        booking_fee_cents=attempt.booking_fee_cents,
                        deposit_cents=attempt.deposit_cents,
                        platform_fee_cents=attempt.platform_fee_cents,
                        stripe_processing_fee_cents=attempt.stripe_processing_fee_cents,
                    )
                    db.add(appointment)
                    attempt.status = "paid"
                    attempt.stripe_payment_intent_id = data.get("payment_intent")
                else:
                    attempt.status = "paid_conflict"

        db.commit()

    if event_type == "charge.succeeded":
        # Checkout completion normally captures the fee above. Keep this event
        # as a reconciliation path when Stripe's balance transaction is ready
        # after the Checkout event has been delivered.
        payment_intent_id = data.get("payment_intent")
        processing_fee_cents = get_payment_processing_fee_cents(payment_intent_id)
        if payment_intent_id and processing_fee_cents is not None:
            for appointment in db.scalars(
                select(Appointment).where(Appointment.stripe_payment_intent_id == payment_intent_id)
            ):
                appointment.stripe_processing_fee_cents = processing_fee_cents
            for attempt in db.scalars(
                select(CheckoutAttempt).where(CheckoutAttempt.stripe_payment_intent_id == payment_intent_id)
            ):
                attempt.stripe_processing_fee_cents = processing_fee_cents
            db.commit()

    if event_type == "checkout.session.expired":
        metadata = data.get("metadata", {})
        if metadata.get("purpose") == "booking_fee":
            attempt = db.scalar(
                select(CheckoutAttempt).where(CheckoutAttempt.id == int(metadata["checkout_attempt_id"]))
            )
            if attempt and attempt.status == "checkout_started":
                attempt.status = "checkout_expired"
                db.commit()

    if event_type == "account.updated":
        account_id = data.get("id")
        payouts_enabled = bool(data.get("payouts_enabled"))
        charges_enabled = bool(data.get("charges_enabled"))
        is_complete = payouts_enabled and charges_enabled

        shop = db.scalar(select(BarberShop).where(BarberShop.stripe_account_id == account_id))
        if shop:
            shop.stripe_onboarding_complete = is_complete

        barber = db.scalar(select(BarberProfile).where(BarberProfile.stripe_account_id == account_id))
        if barber:
            barber.stripe_onboarding_complete = is_complete
        db.commit()

    return {"received": True}
