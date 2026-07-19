import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../api";

const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const usTimeZones = [
  ["America/New_York", "Eastern Time"],
  ["America/Detroit", "Eastern Time - Michigan"],
  ["America/Kentucky/Louisville", "Eastern Time - Kentucky"],
  ["America/Indiana/Indianapolis", "Eastern Time - Indiana"],
  ["America/Chicago", "Central Time"],
  ["America/Indiana/Knox", "Central Time - Indiana"],
  ["America/Menominee", "Central Time - Michigan"],
  ["America/Denver", "Mountain Time"],
  ["America/Boise", "Mountain Time - Idaho"],
  ["America/Phoenix", "Arizona Time"],
  ["America/Los_Angeles", "Pacific Time"],
  ["America/Anchorage", "Alaska Time"],
  ["America/Juneau", "Alaska Time - Juneau"],
  ["America/Sitka", "Alaska Time - Sitka"],
  ["America/Nome", "Alaska Time - Nome"],
  ["America/Adak", "Hawaii-Aleutian Time - Aleutian"],
  ["Pacific/Honolulu", "Hawaii Time"],
];

const emptyService = {
  barber_id: "",
  name: "",
  description: "",
  duration_minutes: 30,
  price: "30.00",
  booking_fee: "3.00",
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function centsToDollars(cents) {
  return (Number(cents || 0) / 100).toFixed(2);
}

function dollarsToCents(value) {
  return Math.round(Number(value || 0) * 100);
}

function utcDate(value) {
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
}

function serviceToForm(service) {
  return {
    barber_id: String(service.barber_id ?? ""),
    name: service.name,
    description: service.description ?? "",
    duration_minutes: service.duration_minutes,
    price: centsToDollars(service.price_cents),
    booking_fee: centsToDollars(service.booking_fee_cents),
    is_active: service.is_active,
  };
}

function servicePayload(form) {
  const bookingFeeCents = dollarsToCents(form.booking_fee);
  return {
    barber_id: form.barber_id ? Number(form.barber_id) : null,
    name: form.name,
    description: form.description || null,
    duration_minutes: Number(form.duration_minutes),
    price_cents: dollarsToCents(form.price),
    booking_fee_cents: bookingFeeCents,
    deposit_cents: Math.max(0, bookingFeeCents - Math.floor(bookingFeeCents / 3)),
    platform_fee_cents: Math.floor(bookingFeeCents / 3),
    is_active: Boolean(form.is_active),
  };
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [profile, setProfile] = useState({ shop_name: "", owner_display_name: "", timezone: "" });
  const [service, setService] = useState(emptyService);
  const [serviceForms, setServiceForms] = useState({});
  const [selectedServiceBarberId, setSelectedServiceBarberId] = useState("");
  const [barberForms, setBarberForms] = useState({});
  const [hours, setHours] = useState([]);
  const [dateHour, setDateHour] = useState({
    specific_date: todayIso(),
    opens_at: "09:00",
    closes_at: "17:00",
    is_closed: false,
    note: "",
  });
  const [barber, setBarber] = useState({ display_name: "", bio: "", email: "" });
  const [manualAppointment, setManualAppointment] = useState({
    service_id: "",
    barber_id: "",
    starts_at: "",
    client_name: "Manual block",
    client_phone: "manual",
  });
  const [activeCalendarBarberId, setActiveCalendarBarberId] = useState("");
  const [serviceErrors, setServiceErrors] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function hydrate(data) {
    const owner = data.barbers.find((item) => item.is_owner);
    setDashboard(data);
    setProfile({
      shop_name: data.shop.name,
      owner_display_name: owner?.display_name ?? "",
      timezone: data.shop.timezone,
      booking_window_days: data.shop.booking_window_days,
      address_line1: data.shop.address_line1 ?? "",
      city: data.shop.city ?? "",
      state: data.shop.state ?? "",
      postal_code: data.shop.postal_code ?? "",
      latitude: data.shop.latitude_microdegrees !== null && data.shop.latitude_microdegrees !== undefined ? data.shop.latitude_microdegrees / 1000000 : "",
      longitude: data.shop.longitude_microdegrees !== null && data.shop.longitude_microdegrees !== undefined ? data.shop.longitude_microdegrees / 1000000 : "",
    });
    setServiceForms(Object.fromEntries(data.services.map((item) => [item.id, serviceToForm(item)])));
    setBarberForms(Object.fromEntries(data.barbers.filter((item) => !item.is_owner).map((item) => [item.id, {
      display_name: item.display_name,
      bio: item.bio ?? "",
    }])));
    setService((current) => ({ ...current, barber_id: current.barber_id || String(owner?.id ?? data.barbers[0]?.id ?? "") }));
    setHours(data.business_hours);
    setManualAppointment((current) => ({
      ...current,
      service_id: current.service_id || String(data.services[0]?.id ?? ""),
      barber_id: current.barber_id || String(owner?.id ?? data.barbers[0]?.id ?? ""),
    }));
    setDateHour((current) => {
      const existing = data.date_hour_overrides.find((item) => item.specific_date === current.specific_date);
      return existing
        ? { ...existing, note: existing.note ?? "" }
        : current;
    });
    setActiveCalendarBarberId((current) => {
      const stillExists = data.barbers.some((item) => String(item.id) === String(current));
      return stillExists ? current : String(owner?.id ?? data.barbers[0]?.id ?? "");
    });
    setSelectedServiceBarberId((current) => {
      const stillExists = data.barbers.some((item) => String(item.id) === String(current));
      return stillExists ? current : String(owner?.id ?? data.barbers[0]?.id ?? "");
    });
  }

  async function loadDashboard() {
    try {
      setError("");
      hydrate(await apiRequest("/api/shops/me"));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  async function startShopConnect() {
    const data = await apiRequest("/api/shops/me/connect", { method: "POST" });
    if (data.url) {
      window.location.href = data.url;
      return;
    }
    setMessage(data.message);
    await loadDashboard();
  }

  async function startSetupPayment() {
    const data = await apiRequest("/api/shops/me/setup-checkout", { method: "POST" });
    if (data.url) {
      window.location.href = data.url;
      return;
    }
    setMessage(data.message);
  }

  async function payForMonthlyAccess() {
    const data = await apiRequest("/api/shops/me/monthly-access-checkout", { method: "POST" });
    if (data.url) window.location.href = data.url;
    else setMessage(data.message);
  }

  async function startBarberConnect(barberId) {
    const data = await apiRequest(`/api/shops/me/barbers/${barberId}/connect`, { method: "POST" });
    if (data.url) {
      window.location.href = data.url;
      return;
    }
    setMessage(data.message);
    await loadDashboard();
  }

  async function saveProfile(event) {
    event.preventDefault();
    const profilePayload = {
      ...profile,
      address_line1: profile.address_line1 || null,
      city: profile.city || null,
      state: profile.state || null,
      postal_code: profile.postal_code || null,
      latitude: profile.latitude === "" ? null : Number(profile.latitude),
      longitude: profile.longitude === "" ? null : Number(profile.longitude),
    };
    hydrate(
      await apiRequest("/api/shops/me/profile", {
        method: "PATCH",
        body: JSON.stringify(profilePayload),
      }),
    );
    setMessage("Shop profile updated.");
  }

  async function addService(event) {
    event.preventDefault();
    const validation = validateServiceForm(service);
    if (validation) {
      setServiceErrors({ add: validation });
      return;
    }
    setServiceErrors({});
    await apiRequest("/api/shops/me/services", {
      method: "POST",
      body: JSON.stringify(servicePayload({ ...service, is_active: true })),
    });
    setService(emptyService);
    setMessage("Service added.");
    await loadDashboard();
  }

  async function saveService(serviceId) {
    const form = serviceForms[serviceId];
    const validation = validateServiceForm(form);
    if (validation) {
      setServiceErrors({ [serviceId]: validation });
      return;
    }
    setServiceErrors({});
    await apiRequest(`/api/shops/me/services/${serviceId}`, {
      method: "PATCH",
      body: JSON.stringify(servicePayload(form)),
    });
    setMessage("Service updated.");
    await loadDashboard();
  }

  async function removeService(serviceId, serviceName) {
    if (!window.confirm(`Remove ${serviceName} from future booking? Its past appointments will remain in history.`)) return;
    hydrate(await apiRequest(`/api/shops/me/services/${serviceId}`, { method: "DELETE" }));
    setMessage("Service removed from booking.");
  }

  async function saveHours(event) {
    event.preventDefault();
    hydrate(
      await apiRequest("/api/shops/me/hours", {
        method: "PUT",
        body: JSON.stringify({ hours }),
      }),
    );
    setMessage("Business hours updated.");
  }

  async function saveDateHour(event) {
    event.preventDefault();
    hydrate(
      await apiRequest("/api/shops/me/date-hours", {
        method: "PUT",
        body: JSON.stringify({ ...dateHour, note: dateHour.note || null }),
      }),
    );
    setMessage("Specific day hours saved.");
  }

  async function removeDateHour(specificDate) {
    hydrate(
      await apiRequest(`/api/shops/me/date-hours/${specificDate}`, {
        method: "DELETE",
      }),
    );
    setDateHour({
      specific_date: specificDate,
      opens_at: "09:00",
      closes_at: "17:00",
      is_closed: false,
      note: "",
    });
    setMessage("Specific day hours removed.");
  }

  function selectDateHour(specificDate) {
    const existing = dashboard.date_hour_overrides.find((item) => item.specific_date === specificDate);
    setDateHour(
      existing
        ? { ...existing, note: existing.note ?? "" }
        : {
            specific_date: specificDate,
            opens_at: "09:00",
            closes_at: "17:00",
            is_closed: false,
            note: "",
          },
    );
  }

  function validateServiceForm(form) {
    if (dollarsToCents(form.price) <= 100) {
      return "Full service price must be greater than $1.00 so full prepay can cover the platform fee.";
    }
    if (dollarsToCents(form.booking_fee) < 100) {
      return "Hold booking fee must be at least $1.00.";
    }
    return "";
  }

  async function toggleBlockout(day, blocked) {
    const barberId = Number(activeCalendarBarberId);
    if (!barberId) return;
    hydrate(
      await apiRequest("/api/shops/me/blockouts", {
        method: "POST",
        body: JSON.stringify({
          barber_id: barberId,
          blocked_date: day,
          blocked,
        }),
      }),
    );
    setMessage(blocked ? "Day blocked out." : "Day reopened.");
  }

  async function addBarber(event) {
    event.preventDefault();
    try {
      setError("");
      await apiRequest("/api/shops/me/barbers", {
        method: "POST",
        body: JSON.stringify({
          display_name: barber.display_name,
          bio: barber.bio || null,
          email: barber.email || null,
        }),
      });
      setBarber({ display_name: "", bio: "", email: "" });
      setMessage("Barber added.");
      await loadDashboard();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function deleteBarber(barberId, displayName) {
    const confirmed = window.confirm(`Delete ${displayName}? Existing appointment history will stay intact.`);
    if (!confirmed) return;
    hydrate(
      await apiRequest(`/api/shops/me/barbers/${barberId}`, {
        method: "DELETE",
      }),
    );
    setMessage("Barber removed.");
  }

  async function saveBarber(barberId) {
    const form = barberForms[barberId];
    await apiRequest(`/api/shops/me/barbers/${barberId}`, {
      method: "PATCH",
      body: JSON.stringify({ display_name: form.display_name, bio: form.bio || null }),
    });
    setMessage("Barber details updated.");
    await loadDashboard();
  }

  async function addManualAppointment(event) {
    event.preventDefault();
    if (!manualAppointment.starts_at || !manualAppointment.service_id || !manualAppointment.barber_id) return;
    hydrate(
      await apiRequest("/api/shops/me/manual-appointments", {
        method: "POST",
        body: JSON.stringify({
          service_id: Number(manualAppointment.service_id),
          barber_id: Number(manualAppointment.barber_id),
          starts_at: new Date(manualAppointment.starts_at).toISOString(),
          client_name: manualAppointment.client_name || "Manual block",
          client_phone: manualAppointment.client_phone || "manual",
        }),
      }),
    );
    setManualAppointment({ ...manualAppointment, starts_at: "", client_name: "Manual block", client_phone: "manual" });
    setMessage("Manual appointment added.");
  }

  function useCurrentLocationForShop() {
    if (!navigator.geolocation) {
      setError("Location is not available in this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setProfile((current) => ({
          ...current,
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6),
        }));
        setMessage("Current location filled into latitude and longitude. Save the profile to update discovery sorting.");
      },
      () => {
        setError("Location was not shared. Enter latitude and longitude manually.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  }

  if (error === "Not authenticated") {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-3xl font-bold">Login required</h1>
        <p className="mt-3 text-zinc-700">Sign in as the shop owner to manage this shop.</p>
        <Link className="mt-5 inline-block rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white" to="/login">
          Login
        </Link>
      </section>
    );
  }

  if (error && !dashboard) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-3xl font-bold">Dashboard unavailable</h1>
        <p className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
      </section>
    );
  }

  if (!dashboard) {
    return <section className="mx-auto max-w-6xl px-6 py-10 text-zinc-700">Loading dashboard...</section>;
  }

  const ownerPayoutReady = Boolean(dashboard.shop.stripe_account_id && dashboard.shop.stripe_onboarding_complete);
  const ownerPayoutButtonLabel = dashboard.shop.stripe_account_id ? "Refresh owner payouts" : "Set up owner payouts";

  return (
    <section className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">Owner dashboard</p>
          <h1 className="mt-2 text-3xl font-bold">{dashboard.shop.name}</h1>
          <p className="mt-2 text-zinc-700">
            Booking page: <Link className="font-semibold text-emerald-800" to={`/book/${dashboard.shop.slug}`}>/book/{dashboard.shop.slug}</Link>
          </p>
          <Link to={`/barber/clients?barber_id=${activeCalendarBarberId}`} className="mt-3 inline-block text-sm font-semibold text-emerald-800 hover:underline dark:text-emerald-300">
            View selected barber&apos;s client list
          </Link>
        </div>
        {ownerPayoutReady ? (
          <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
            Owner payouts ready
          </p>
        ) : (
          <button
            type="button"
            onClick={startShopConnect}
            className="rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white hover:bg-zinc-800"
          >
            {ownerPayoutButtonLabel}
          </button>
        )}
      </div>

      {(message || error) && (
        <p className={`mb-5 rounded-md p-3 text-sm ${error ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"}`}>
          {error || message}
        </p>
      )}

      {dashboard.shop.admin_message && (
        <p className="mb-5 rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"><span className="font-semibold">Message from platform support:</span> {dashboard.shop.admin_message}</p>
      )}
      {dashboard.shop.access_warning_month && !dashboard.shop.access_suspended && (
        <div className="mb-5 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/70 dark:text-amber-100"><p><span className="font-semibold">Account notice:</span> Your shop has generated ${(dashboard.platform_fees_this_month_cents / 100).toFixed(2)} of the $25.00 monthly platform-fee threshold. Reach it this month to keep uninterrupted access.</p><button type="button" onClick={payForMonthlyAccess} className="mt-3 rounded-md bg-amber-800 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700">Pay $25 for this month</button></div>
      )}
      {dashboard.shop.access_suspended && (
        <div className="mb-5 rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/70 dark:text-red-100"><p><span className="font-semibold">Access paused:</span> Pay $25 for the current month to restore booking access immediately.</p><button type="button" onClick={payForMonthlyAccess} className="mt-3 rounded-md bg-red-800 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700">Pay $25 and restore access</button></div>
      )}

      <details className="mb-5 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-xl font-semibold">
          Upcoming appointments ({dashboard.upcoming_appointments.length})
        </summary>
        <div className="mt-4 max-h-[520px] space-y-3 overflow-auto">
          {dashboard.upcoming_appointments.map((appointment) => (
            <div key={appointment.id} className="rounded-md border border-zinc-200 p-3 text-sm">
              <p className="font-semibold">{utcDate(appointment.starts_at).toLocaleString(undefined, { timeZone: dashboard.shop.timezone })}</p>
              <p className="text-zinc-700">{appointment.service_name}</p>
              <p className="text-zinc-600">
                {appointment.barber_name ?? "Shop owner"} | {appointment.client_name ?? "Guest"} | {appointment.client_phone}
              </p>
              <p className="text-zinc-500">{appointment.status}</p>
            </div>
          ))}
          {dashboard.upcoming_appointments.length === 0 && (
            <p className="rounded-md bg-stone-50 p-3 text-sm text-zinc-600">No upcoming appointments yet.</p>
          )}
        </div>
      </details>

      {dashboard.shop.setup_payment_status !== "paid" && dashboard.shop.setup_payment_status !== "demo" && (
        <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <p className="font-semibold">Setup payment is required before this shop is published.</p>
          <p className="mt-1">Complete the one-time setup payment to make the public booking page available.</p>
          <button
            type="button"
            onClick={startSetupPayment}
            className="mt-3 rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-800"
          >
            Complete setup payment
          </button>
        </div>
      )}

      {(dashboard.shop.setup_payment_status === "paid" || dashboard.shop.setup_payment_status === "demo") && !ownerPayoutReady && (
        <div className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          <p className="font-semibold">
            {dashboard.shop.stripe_account_id ? "Setup payment is complete. Payout status needs confirmation." : "Setup payment is complete. Payout setup is next."}
          </p>
          <p className="mt-1">
            {dashboard.shop.stripe_account_id
              ? "Refresh owner payouts or continue Stripe onboarding if Stripe still needs information."
              : "Connect the shop owner payout account before accepting live booking payments."}
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <details className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-xl font-semibold">Shop profile</summary>
          <form onSubmit={saveProfile}>
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-sm font-medium">
              Shop name
              <input value={profile.shop_name} onChange={(e) => setProfile({ ...profile, shop_name: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
            </label>
            <label className="grid gap-1 text-sm font-medium">
              Owner display name
              <input value={profile.owner_display_name} onChange={(e) => setProfile({ ...profile, owner_display_name: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
            </label>
            <label className="grid gap-1 text-sm font-medium">
              Time zone
              <select
                value={profile.timezone}
                onChange={(e) => setProfile({ ...profile, timezone: e.target.value })}
                className="rounded-md border border-zinc-300 px-3 py-2"
              >
                {usTimeZones.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label} ({value})
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-sm font-medium">
              Street address
              <input value={profile.address_line1} onChange={(e) => setProfile({ ...profile, address_line1: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="grid gap-1 text-sm font-medium">
                City
                <input value={profile.city} onChange={(e) => setProfile({ ...profile, city: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
              </label>
              <label className="grid gap-1 text-sm font-medium">
                State
                <input value={profile.state} onChange={(e) => setProfile({ ...profile, state: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
              </label>
              <label className="grid gap-1 text-sm font-medium">
                ZIP
                <input value={profile.postal_code} onChange={(e) => setProfile({ ...profile, postal_code: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm font-medium">
                Latitude
                <input type="number" step="0.000001" value={profile.latitude} onChange={(e) => setProfile({ ...profile, latitude: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
              </label>
              <label className="grid gap-1 text-sm font-medium">
                Longitude
                <input type="number" step="0.000001" value={profile.longitude} onChange={(e) => setProfile({ ...profile, longitude: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2" />
              </label>
            </div>
            <button
              type="button"
              onClick={useCurrentLocationForShop}
              className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-semibold hover:bg-stone-50"
            >
              Use my current location for shop coordinates
            </button>
            <label className="grid gap-1 text-sm font-medium">
              Advance booking window in days
              <input
                type="number"
                min="30"
                value={profile.booking_window_days}
                onChange={(e) => setProfile({ ...profile, booking_window_days: Number(e.target.value) })}
                className="rounded-md border border-zinc-300 px-3 py-2"
              />
              <span className="text-xs font-normal text-zinc-600">Minimum 30 days.</span>
            </label>
            <button className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Save profile</button>
          </div>
          </form>
        </details>

        <details className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-xl font-semibold">Payouts</summary>
          <p className="mt-2 text-sm text-zinc-600">
            Stripe onboarding is hosted by Stripe. The shop owner receives shop payments automatically once payouts are set up.
          </p>
          <p className="mt-3 break-all text-sm text-zinc-600">
            Owner payout account: {dashboard.shop.stripe_account_id ?? "Not set up"}
          </p>
          <p className="mt-2 text-sm font-semibold text-zinc-700">
            Status: {ownerPayoutReady ? "Ready for booking payouts" : dashboard.shop.stripe_account_id ? "Needs Stripe confirmation" : "Not connected"}
          </p>
        </details>
      </div>

      <details className="mt-8 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-xl font-semibold">Weekly default hours</summary>
        <form onSubmit={saveHours}>
          <p className="mt-3 text-sm text-zinc-600">
            These are the normal shop hours. Use specific day hours below for holidays, late openings, or one-off schedule changes.
          </p>
          <div className="mt-4 grid gap-3">
            {hours.map((hour, index) => (
              <div key={hour.day_of_week} className="grid gap-3 rounded-md border border-zinc-200 p-3 sm:grid-cols-[70px_1fr_1fr_110px] sm:items-center">
                <p className="font-medium">{days[hour.day_of_week]}</p>
                <input
                  type="time"
                  value={hour.opens_at}
                  disabled={hour.is_closed}
                  onChange={(e) => setHours(hours.map((item, i) => (i === index ? { ...item, opens_at: e.target.value } : item)))}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 disabled:bg-zinc-100"
                />
                <input
                  type="time"
                  value={hour.closes_at}
                  disabled={hour.is_closed}
                  onChange={(e) => setHours(hours.map((item, i) => (i === index ? { ...item, closes_at: e.target.value } : item)))}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 disabled:bg-zinc-100"
                />
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={hour.is_closed}
                    onChange={(e) => setHours(hours.map((item, i) => (i === index ? { ...item, is_closed: e.target.checked } : item)))}
                  />
                  Closed
                </label>
              </div>
            ))}
          </div>
          <button className="mt-4 rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Save hours</button>
        </form>
      </details>

      <details className="mt-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-xl font-semibold">Specific day hours</summary>
        <form onSubmit={saveDateHour}>
          <p className="mt-3 text-sm text-zinc-600">
            Set hours for an exact calendar date. These override the weekly default for the whole shop.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_120px] xl:items-end">
            <label className="grid gap-1 text-sm font-medium">
              Date
              <input
                type="date"
                value={dateHour.specific_date}
                onChange={(e) => selectDateHour(e.target.value)}
                className="w-full rounded-md border border-zinc-300 px-3 py-2"
              />
            </label>
            <label className="grid gap-1 text-sm font-medium">
              Opens
              <input
                type="time"
                value={dateHour.opens_at}
                disabled={dateHour.is_closed}
                onChange={(e) => setDateHour({ ...dateHour, opens_at: e.target.value })}
                className="w-full rounded-md border border-zinc-300 px-3 py-2 disabled:bg-zinc-100"
              />
            </label>
            <label className="grid gap-1 text-sm font-medium">
              Closes
              <input
                type="time"
                value={dateHour.closes_at}
                disabled={dateHour.is_closed}
                onChange={(e) => setDateHour({ ...dateHour, closes_at: e.target.value })}
                className="w-full rounded-md border border-zinc-300 px-3 py-2 disabled:bg-zinc-100"
              />
            </label>
            <label className="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={dateHour.is_closed}
                onChange={(e) => setDateHour({ ...dateHour, is_closed: e.target.checked })}
              />
              Closed
            </label>
          </div>
          <label className="mt-3 grid gap-1 text-sm font-medium">
            Note
            <input
              value={dateHour.note}
              onChange={(e) => setDateHour({ ...dateHour, note: e.target.value })}
              placeholder="Optional, for example holiday or private event"
              className="w-full rounded-md border border-zinc-300 px-3 py-2"
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-3">
            <button className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Save specific day</button>
            {dashboard.date_hour_overrides.some((item) => item.specific_date === dateHour.specific_date) && (
              <button
                type="button"
                onClick={() => removeDateHour(dateHour.specific_date)}
                className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-semibold"
              >
                Remove override
              </button>
            )}
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {dashboard.date_hour_overrides.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setDateHour({ ...item, note: item.note ?? "" })}
                className="rounded-md border border-zinc-200 bg-stone-50 px-3 py-2 text-left text-sm hover:border-zinc-400"
              >
                <span className="block font-semibold">{item.specific_date}</span>
                <span className="text-zinc-700">
                  {item.is_closed ? "Closed" : `${item.opens_at} - ${item.closes_at}`}
                </span>
                {item.note && <span className="block text-zinc-500">{item.note}</span>}
              </button>
            ))}
            {dashboard.date_hour_overrides.length === 0 && (
              <p className="rounded-md bg-stone-50 p-3 text-sm text-zinc-600">No specific day overrides yet.</p>
            )}
          </div>
        </form>
      </details>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <details className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-xl font-semibold">Services</summary>
          <label className="mt-4 grid gap-1 text-sm font-medium">
            Show services for
            <select value={selectedServiceBarberId} onChange={(e) => setSelectedServiceBarberId(e.target.value)} className="rounded-md border border-zinc-300 px-3 py-2">
              {dashboard.barbers.map((item) => <option key={item.id} value={item.id}>{item.display_name}{item.is_owner ? " (owner)" : ""}</option>)}
            </select>
          </label>
          <div className="mt-4 space-y-4">
            {dashboard.services.filter((item) => String(item.barber_id) === String(selectedServiceBarberId)).map((item) => {
              const form = serviceForms[item.id];
              return (
                <div key={item.id} className="rounded-md border border-zinc-200 p-4">
                  <div className="grid gap-3">
                    <label className="grid gap-1 text-sm font-medium">
                      Service name
                      <input value={form.name} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, name: e.target.value } })} className="rounded-md border border-zinc-300 px-3 py-2" />
                    </label>
                    <label className="grid gap-1 text-sm font-medium">Provider
                      <select value={form.barber_id} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, barber_id: e.target.value } })} className="rounded-md border border-zinc-300 px-3 py-2">
                        {dashboard.barbers.filter((barber) => barber.is_active).map((barber) => <option key={barber.id} value={barber.id}>{barber.display_name}</option>)}
                      </select>
                    </label>
                    <div className="grid gap-3 xl:grid-cols-3">
                      <label className="grid min-w-0 gap-1 text-sm font-medium">
                        Duration in minutes
                        <input type="number" min="10" value={form.duration_minutes} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, duration_minutes: e.target.value } })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
                      </label>
                      <label className="grid min-w-0 gap-1 text-sm font-medium">
                        Full service price
                        <input type="number" min="0" step="0.01" value={form.price} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, price: e.target.value } })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
                      </label>
                      <label className="grid min-w-0 gap-1 text-sm font-medium">
                        Hold booking fee
                        <input type="number" min="1" step="0.01" value={form.booking_fee} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, booking_fee: e.target.value } })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
                      </label>
                    </div>
                    <p className="text-sm text-zinc-600">
                      Hold fee split: platform receives one third. Full prepay: platform receives $1.00.
                    </p>
                    {serviceErrors[item.id] && (
                      <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{serviceErrors[item.id]}</p>
                    )}
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={form.is_active} onChange={(e) => setServiceForms({ ...serviceForms, [item.id]: { ...form, is_active: e.target.checked } })} />
                      Active on booking page
                    </label>
                    <div className="flex flex-wrap gap-3">
                      <button type="button" onClick={() => saveService(item.id)} className="rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">Save service</button>
                      <button type="button" onClick={() => removeService(item.id, item.name)} className="rounded-md border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50">Remove service</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {dashboard.services.filter((item) => String(item.barber_id) === String(selectedServiceBarberId)).length === 0 && (
            <p className="mt-4 rounded-md bg-stone-50 p-3 text-sm text-zinc-600">No services are assigned to this barber yet.</p>
          )}
          <form onSubmit={addService} className="mt-5 grid gap-3 border-t border-zinc-200 pt-5">
            <h3 className="font-semibold">Add service</h3>
            <label className="grid gap-1 text-sm font-medium">
              Service name
              <input value={service.name} onChange={(e) => setService({ ...service, name: e.target.value })} required className="rounded-md border border-zinc-300 px-3 py-2" />
            </label>
            <label className="grid gap-1 text-sm font-medium">Provider
              <select value={service.barber_id} onChange={(e) => setService({ ...service, barber_id: e.target.value })} className="rounded-md border border-zinc-300 px-3 py-2">
                {dashboard.barbers.filter((barber) => barber.is_active).map((barber) => <option key={barber.id} value={barber.id}>{barber.display_name}</option>)}
              </select>
            </label>
            <div className="grid gap-3 xl:grid-cols-3">
              <label className="grid min-w-0 gap-1 text-sm font-medium">
                Duration in minutes
                <input type="number" min="10" value={service.duration_minutes} onChange={(e) => setService({ ...service, duration_minutes: e.target.value })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
              </label>
              <label className="grid min-w-0 gap-1 text-sm font-medium">
                Full service price
                <input type="number" min="0" step="0.01" value={service.price} onChange={(e) => setService({ ...service, price: e.target.value })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
              </label>
              <label className="grid min-w-0 gap-1 text-sm font-medium">
                Hold booking fee
                <input type="number" min="1" step="0.01" value={service.booking_fee} onChange={(e) => setService({ ...service, booking_fee: e.target.value })} className="w-full rounded-md border border-zinc-300 px-3 py-2" />
              </label>
            </div>
            {serviceErrors.add && (
              <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{serviceErrors.add}</p>
            )}
            <button className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Add service</button>
          </form>
        </details>

        <details className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-xl font-semibold">Additional barbers</summary>
          <div className="mt-4 space-y-3">
            {dashboard.barbers.map((item) => (
              <div key={item.id} className="rounded-md border border-zinc-200 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    {item.is_owner ? (
                      <p className="font-medium">{item.display_name} (owner)</p>
                    ) : (
                      <div className="grid gap-2">
                        <input
                          value={barberForms[item.id]?.display_name ?? ""}
                          onChange={(e) => setBarberForms({ ...barberForms, [item.id]: { ...barberForms[item.id], display_name: e.target.value } })}
                          aria-label={`${item.display_name} display name`}
                          className="rounded-md border border-zinc-300 px-3 py-2 font-medium"
                        />
                        <textarea
                          value={barberForms[item.id]?.bio ?? ""}
                          onChange={(e) => setBarberForms({ ...barberForms, [item.id]: { ...barberForms[item.id], bio: e.target.value } })}
                          aria-label={`${item.display_name} biography`}
                          placeholder="Optional barber bio"
                          rows="2"
                          className="rounded-md border border-zinc-300 px-3 py-2 text-sm"
                        />
                      </div>
                    )}
                    <p className="break-all text-sm text-zinc-600">
                      {item.is_owner ? "Uses the shop owner payout account" : item.stripe_account_id ?? "No separate payout account yet"}
                    </p>
                  </div>
                  {!item.is_owner && (
                    <div className="flex flex-wrap justify-end gap-2">
                      {item.stripe_account_id && item.stripe_onboarding_complete ? (
                        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800">
                          Payouts ready
                        </span>
                      ) : (
                        <button type="button" onClick={() => startBarberConnect(item.id)} className="rounded-md border border-zinc-300 px-3 py-2 text-xs font-semibold">
                          {item.stripe_account_id ? "Refresh payouts" : "Set up payouts"}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => saveBarber(item.id)}
                        className="rounded-md border border-zinc-300 px-3 py-2 text-xs font-semibold"
                      >
                        Save details
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteBarber(item.id, item.display_name)}
                        className="rounded-md border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <form onSubmit={addBarber} className="mt-5 grid gap-3 border-t border-zinc-200 pt-5">
            <input value={barber.display_name} onChange={(e) => setBarber({ ...barber, display_name: e.target.value })} placeholder="Barber display name" required className="rounded-md border border-zinc-300 px-3 py-2" />
            <textarea value={barber.bio} onChange={(e) => setBarber({ ...barber, bio: e.target.value })} placeholder="Optional barber bio" rows="2" className="rounded-md border border-zinc-300 px-3 py-2" />
            <input type="email" value={barber.email} onChange={(e) => setBarber({ ...barber, email: e.target.value })} placeholder="Optional barber email" className="rounded-md border border-zinc-300 px-3 py-2" />
            <button className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Add barber</button>
          </form>
        </details>
      </div>

      <div className="mt-8">
        <details className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-xl font-semibold">Barber calendar</summary>
          <label className="mt-4 grid gap-1 text-sm font-medium">
            Active barber
            <select
              value={activeCalendarBarberId}
              onChange={(e) => setActiveCalendarBarberId(e.target.value)}
              className="rounded-md border border-zinc-300 px-3 py-2"
            >
              {dashboard.barbers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name}{item.is_owner ? " (owner)" : ""}
                </option>
              ))}
            </select>
          </label>
          <form onSubmit={addManualAppointment} className="mt-4 grid gap-3 rounded-md border border-zinc-200 bg-stone-50 p-3">
            <h3 className="font-semibold">Close time for outside appointment</h3>
            <div className="grid gap-3">
              <label className="grid gap-1 text-sm font-medium">
                Service length
                <select
                  value={manualAppointment.service_id}
                  onChange={(e) => setManualAppointment({ ...manualAppointment, service_id: e.target.value })}
                  className="rounded-md border border-zinc-300 px-3 py-2"
                >
                  {dashboard.services.filter((item) => item.is_active).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({item.duration_minutes} min)
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-medium">
                Barber
                <select
                  value={manualAppointment.barber_id}
                  onChange={(e) => setManualAppointment({ ...manualAppointment, barber_id: e.target.value })}
                  className="rounded-md border border-zinc-300 px-3 py-2"
                >
                  {dashboard.barbers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}{item.is_owner ? " (owner)" : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="grid gap-1 text-sm font-medium">
              Starts at (date and time)
              <input
                type="datetime-local"
                value={manualAppointment.starts_at}
                onChange={(e) => setManualAppointment({ ...manualAppointment, starts_at: e.target.value })}
                className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900"
                style={{ colorScheme: "light" }}
                required
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm font-medium">
                Name or note
                <input
                  value={manualAppointment.client_name}
                  onChange={(e) => setManualAppointment({ ...manualAppointment, client_name: e.target.value })}
                  className="rounded-md border border-zinc-300 px-3 py-2"
                />
              </label>
              <label className="grid gap-1 text-sm font-medium">
                Phone or reference
                <input
                  value={manualAppointment.client_phone}
                  onChange={(e) => setManualAppointment({ ...manualAppointment, client_phone: e.target.value })}
                  className="rounded-md border border-zinc-300 px-3 py-2"
                />
              </label>
            </div>
            <button className="rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">
              Close this time
            </button>
          </form>
          <div className="mt-4 grid grid-cols-7 gap-2 text-center text-xs font-semibold text-zinc-500">
            {days.map((day) => <span key={day}>{day}</span>)}
          </div>
          <div className="mt-2 grid grid-cols-7 gap-2">
            {Array.from({ length: 28 }, (_, index) => {
              const now = new Date();
              const mondayOffset = (now.getDay() + 6) % 7;
              const currentMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - mondayOffset);
              const calendarDay = new Date(currentMonday.getFullYear(), currentMonday.getMonth(), currentMonday.getDate() + index);
              const day = calendarDay.toISOString().slice(0, 10);
              const blocked = dashboard.blockouts.some(
                (item) => String(item.barber_id) === String(activeCalendarBarberId) && item.blocked_date === day,
              );
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => toggleBlockout(day, !blocked)}
                  className={`min-w-0 rounded-md border px-1 py-2 text-center text-xs sm:px-2 ${
                    blocked ? "border-red-300 bg-red-50 text-red-800" : "border-zinc-200 bg-stone-50 text-zinc-800"
                  }`}
                >
                  <span className="block font-semibold">{calendarDay.getDate()}</span>
                  <span className="hidden sm:block">{blocked ? "Blocked" : "Open"}</span>
                </button>
              );
            })}
          </div>
        </details>
      </div>
    </section>
  );
}
