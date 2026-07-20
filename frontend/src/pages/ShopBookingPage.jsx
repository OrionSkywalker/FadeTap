import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { API_BASE_URL } from "../api";

const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function visitorTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
}

function formatVisitorTime(isoValue, timeZone) {
  if (!isoValue || !timeZone) return "";
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
    timeZoneName: "short",
  }).format(new Date(isoValue));
}

export default function ShopBookingPage() {
  const { shopSlug } = useParams();
  const [availability, setAvailability] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [selectedServiceId, setSelectedServiceId] = useState(null);
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [paymentOption, setPaymentOption] = useState("pay_in_full");
  const [client, setClient] = useState({ client_name: "", client_phone: "", sms_opt_in: true });
  const [status, setStatus] = useState("loading");
  const [checkoutMessage, setCheckoutMessage] = useState("");
  const [findingInitialAvailability, setFindingInitialAvailability] = useState(true);

  const displayName = useMemo(
    () =>
      shopSlug
        ?.split("-")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ") ?? "Shop",
    [shopSlug],
  );

  useEffect(() => {
    let isMounted = true;

    async function loadSlots() {
      try {
        setStatus("loading");
        const query = new URLSearchParams();
        if (selectedServiceId) query.set("service_id", selectedServiceId);
        if (selectedDate) query.set("selected_date", selectedDate);
        const queryString = query.toString() ? `?${query.toString()}` : "";
        const response = await fetch(`${API_BASE_URL}/api/shops/${shopSlug}/slots${queryString}`);

        if (!response.ok) {
          throw new Error("Unable to load availability");
        }

        const data = await response.json();
        if (isMounted) {
          setAvailability(data);
          setSelectedSlot(null);
          if (!selectedServiceId) {
            setFindingInitialAvailability(false);
            setStatus("ready");
            return;
          }
          if (findingInitialAvailability && data.slots.length === 0) {
            const nextDate = new Date(`${selectedDate}T12:00:00`);
            nextDate.setDate(nextDate.getDate() + 1);
            const nextDateIso = nextDate.toISOString().slice(0, 10);
            const finalDate = new Date(Date.now() + (data.shop.booking_window_days ?? 30) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
            if (nextDateIso <= finalDate) {
              setSelectedDate(nextDateIso);
              return;
            }
          }
          setFindingInitialAvailability(false);
          setStatus("ready");
        }
      } catch (error) {
        if (isMounted) {
          console.error(error);
          setStatus("error");
        }
      }
    }

    loadSlots();

    return () => {
      isMounted = false;
    };
  }, [shopSlug, selectedServiceId, selectedDate]);

  async function createCheckout() {
    if (!selectedSlot || !selectedServiceId || (client.sms_opt_in && !client.client_phone) || (!client.sms_opt_in && !client.client_name)) return;

    setCheckoutMessage("");
    const response = await fetch(`${API_BASE_URL}/api/shops/${shopSlug}/appointments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service_id: selectedServiceId,
        barber_id: null,
        payment_option: paymentOption,
        starts_at: selectedSlot.starts_at,
        client_phone: client.client_phone,
        client_name: client.client_name || null,
        sms_opt_in: client.sms_opt_in,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      setCheckoutMessage(data.detail ?? "Unable to create checkout");
      return;
    }

    if (data.checkout_url) {
      window.location.href = data.checkout_url;
      return;
    }

    setCheckoutMessage(data.message);
  }

  const selectedService = availability?.services.find((service) => service.id === selectedServiceId);
  const amountDueCents =
    paymentOption === "pay_in_full"
      ? selectedService?.price_cents ?? 0
      : selectedService?.booking_fee_cents ?? 300;
  const bookingFeeCents = selectedService?.booking_fee_cents ?? 300;
  const selectedDateHour = availability?.date_hour_overrides?.find((item) => item.specific_date === selectedDate);
  const bookingWindowDays = availability?.shop?.booking_window_days ?? 30;
  const shopTimeZone = availability?.shop?.timezone ?? "";
  const clientTimeZone = visitorTimeZone();
  const selectedSlotVisitorTime =
    selectedSlot && clientTimeZone && shopTimeZone && clientTimeZone !== shopTimeZone
      ? formatVisitorTime(selectedSlot.starts_at, clientTimeZone)
      : "";
  const maxDate = bookingWindowDays
    ? new Date(Date.now() + bookingWindowDays * 24 * 60 * 60 * 1000)
        .toISOString()
        .slice(0, 10)
    : "";

  return (
    <section className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8">
        <h1 className="mt-2 text-3xl font-bold">Book with {availability?.shop_name ?? displayName}</h1>
        <p className="mt-3 text-zinc-700">
          Pick a service, then choose a date and time up to {bookingWindowDays} days ahead.
        </p>
      </div>

      {status === "loading" && <p className="text-zinc-700">Loading available slots...</p>}
      {status === "error" && (
        <p className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700">
          Availability could not be loaded. Make sure the FastAPI server is running on port 8000.
        </p>
      )}

      {status === "ready" && availability && (
        <div className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
          <div className="flex flex-col gap-6">
            <div className="order-last rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">Business hours</h2>
              {selectedDateHour && (
                <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  Selected date: {selectedDateHour.is_closed ? "Closed" : `${selectedDateHour.opens_at} - ${selectedDateHour.closes_at}`}
                  {selectedDateHour.note ? ` (${selectedDateHour.note})` : ""}
                </p>
              )}
              <div className="mt-3 grid gap-2 text-sm text-zinc-700 sm:grid-cols-2">
                {availability.business_hours.map((hour) => (
                  <p key={hour.day_of_week} className="flex justify-between gap-4 rounded-md bg-stone-50 px-3 py-2">
                    <span className="font-medium">{days[hour.day_of_week]}</span>
                    <span>{hour.is_closed ? "Closed" : `${hour.opens_at} - ${hour.closes_at}`}</span>
                  </p>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">Service</h2>
              <div className="mt-4 grid gap-3">
                {availability.services.map((service) => (
                  <button
                  key={service.id}
                  type="button"
                  onClick={() => {
                    setSelectedServiceId(service.id);
                    setFindingInitialAvailability(true);
                  }}
                    className={`rounded-md border p-4 text-left ${
                      selectedServiceId === service.id
                        ? "border-zinc-950 bg-zinc-950 text-white"
                        : "border-zinc-200 bg-white hover:border-zinc-400"
                    }`}
                  >
                    <p className="font-semibold">{service.name}</p>
                    <p className="mt-1 text-sm opacity-80">
                      {service.duration_minutes} min | ${(service.price_cents / 100).toFixed(2)} service price
                    </p>
                  </button>
                ))}
              </div>
            </div>

            <div className="order-first rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">Time</h2>
              {!selectedServiceId ? (
                <p className="mt-4 rounded-md bg-stone-50 p-3 text-sm text-zinc-700">Choose a service to see available appointment times.</p>
              ) : (
                <>
                  <label className="mt-4 grid gap-1 text-sm font-medium">
                    Date
                    <input
                      type="date"
                      value={selectedDate}
                      min={new Date().toISOString().slice(0, 10)}
                      max={maxDate}
                      onChange={(event) => { setFindingInitialAvailability(false); setSelectedDate(event.target.value); }}
                      className="booking-date-input mt-1 min-w-0 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-950"
                    />
                  </label>
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {availability.slots.map((slot) => (
                      <button
                        key={slot.starts_at}
                        type="button"
                        onClick={() => setSelectedSlot(slot)}
                        className={`rounded-md border px-4 py-3 text-left text-sm font-semibold transition ${
                          selectedSlot?.starts_at === slot.starts_at
                            ? "border-zinc-950 bg-zinc-950 text-white"
                            : "border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400"
                        }`}
                      >
                        {slot.label}
                      </button>
                    ))}
                    {availability.slots.length === 0 && (
                      <p className="col-span-full rounded-md bg-amber-50 p-3 text-sm text-amber-800">No open times for this date.</p>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <aside className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-semibold">Booking summary</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-600">Service</dt>
                <dd className="font-medium">{selectedService?.name ?? "Choose a service"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-600">Selected time</dt>
                <dd className="font-medium">{selectedSlot?.label ?? "Choose a slot"}</dd>
              </div>
              {selectedSlotVisitorTime && (
                <div className="flex justify-between gap-4">
                  <dt className="text-zinc-600">Your local time</dt>
                  <dd className="text-right font-medium">{selectedSlotVisitorTime}</dd>
                </div>
              )}
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-600">Provider</dt>
                <dd className="text-right font-medium">Assigned based on availability</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-600">Payment choice</dt>
                <dd className="text-right font-medium">
                  {paymentOption === "pay_in_full" ? "Pay in full" : "Hold my spot"}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-zinc-600">Due now</dt>
                <dd className="font-medium">${(amountDueCents / 100).toFixed(2)}</dd>
              </div>
            </dl>

            <div className="mt-5 grid gap-3 rounded-md border border-zinc-200 p-3">
              <label className="flex gap-3 text-sm">
                <input
                  type="radio"
                  name="paymentOption"
                  value="hold_fee"
                  checked={paymentOption === "hold_fee"}
                  onChange={() => setPaymentOption("hold_fee")}
                />
                  <span>
                  <span className="block font-semibold">Hold my spot for ${(bookingFeeCents / 100).toFixed(2)}</span>
                  <span className="text-zinc-600">Pay the barber in person after the cut.</span>
                </span>
              </label>
              <label className="flex gap-3 text-sm">
                <input
                  type="radio"
                  name="paymentOption"
                  value="pay_in_full"
                  checked={paymentOption === "pay_in_full"}
                  onChange={() => setPaymentOption("pay_in_full")}
                />
                <span>
                  <span className="block font-semibold">Pay now</span>
                  <span className="text-zinc-600">
                    Save $3 and pay ${(amountDueCents / 100).toFixed(2)} now.
                  </span>
                </span>
              </label>
              <p className="text-xs font-semibold uppercase tracking-wide text-red-700">
                Online payments are non-refundable.
              </p>
            </div>

            <div className="mt-5 grid gap-3">
              <input
                value={client.client_name}
                onChange={(event) => setClient({ ...client, client_name: event.target.value })}
                placeholder="Your name"
                className="rounded-md border border-zinc-300 px-3 py-2"
              />
              <input
                value={client.client_phone}
                onChange={(event) => setClient({ ...client, client_phone: event.target.value })}
                placeholder={client.sms_opt_in ? "Phone for SMS reminders" : "Phone number not shared"}
                className="rounded-md border border-zinc-300 px-3 py-2"
                required={client.sms_opt_in}
                disabled={!client.sms_opt_in}
              />
              <label className="flex items-start gap-2 text-sm text-zinc-700">
                <input type="checkbox" checked={!client.sms_opt_in} onChange={(event) => setClient({ ...client, sms_opt_in: !event.target.checked, client_phone: event.target.checked ? "" : client.client_phone })} />
                <span>I prefer not to share my phone number or receive text updates.</span>
              </label>
            </div>

            {checkoutMessage && (
              <p className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800">{checkoutMessage}</p>
            )}

            <button
              type="button"
              onClick={createCheckout}
              disabled={!selectedSlot || (client.sms_opt_in ? !client.client_phone : !client.client_name)}
              className="mt-6 w-full rounded-md bg-emerald-700 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
            >
              Continue to payment
            </button>
          </aside>
        </div>
      )}
    </section>
  );
}
