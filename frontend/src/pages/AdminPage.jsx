import { useEffect, useState } from "react";
import { apiRequest } from "../api";

const utcDate = (value) => new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);

export default function AdminPage() {
  const [shops, setShops] = useState([]);
  const [policy, setPolicy] = useState({ allowed_shop_state: "CA", allowed_shop_county: "Kern County" });
  const [error, setError] = useState("");
  const [messages, setMessages] = useState({});

  async function load() {
    try {
      setError("");
      const [shopData, policyData] = await Promise.all([apiRequest("/api/admin/shops"), apiRequest("/api/admin/settings")]);
      setShops(shopData);
      setPolicy(policyData);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function saveMessage(id) {
    await apiRequest(`/api/admin/shops/${id}/message`, { method: "PUT", body: JSON.stringify({ message: messages[id] ?? null }) });
    load();
  }

  async function savePolicy(event) {
    event.preventDefault();
    await apiRequest("/api/admin/settings", { method: "PUT", body: JSON.stringify(policy) });
    load();
  }

  async function setPaymentAccess(shop, enabled) {
    const action = enabled ? "grant payment-free platform access to" : "restore normal payment requirements for";
    if (!window.confirm(`Are you sure you want to ${action} ${shop.name}? Client booking payments still apply.`)) return;
    await apiRequest(`/api/admin/shops/${shop.id}/payment-access`, { method: "PUT", body: JSON.stringify({ enabled }) });
    load();
  }

  async function removeBarber(shopId, barber) {
    if (!window.confirm(`Remove ${barber.display_name}? Their future services will be disabled, while appointment history remains.`)) return;
    await apiRequest(`/api/admin/shops/${shopId}/barbers/${barber.id}`, { method: "DELETE" });
    load();
  }

  async function removeShop(shop) {
    if (!window.confirm(`Permanently remove ${shop.name} and its booking data? This cannot be undone.`)) return;
    await apiRequest(`/api/admin/shops/${shop.id}`, { method: "DELETE" });
    load();
  }

  return (
    <section className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-bold">Platform administration</h1>
      <p className="mt-2 text-zinc-600">Monitor shops, control the launch area, and send one-time dashboard messages.</p>
      {error && <p className="mt-4 rounded bg-red-50 p-3 text-red-700">{error}</p>}

      <form onSubmit={savePolicy} className="mt-6 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Shop service area</h2>
        <p className="mt-1 text-sm text-zinc-600">Only verified U.S. shop locations in this area can be listed. Leave state or county empty to widen the area.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-sm font-medium">State (two-letter code)<input value={policy.allowed_shop_state ?? ""} maxLength="2" onChange={(event) => setPolicy({ ...policy, allowed_shop_state: event.target.value.toUpperCase() })} className="rounded border border-zinc-300 px-3 py-2" /></label>
          <label className="grid gap-1 text-sm font-medium">County<input value={policy.allowed_shop_county ?? ""} onChange={(event) => setPolicy({ ...policy, allowed_shop_county: event.target.value })} className="rounded border border-zinc-300 px-3 py-2" /></label>
        </div>
        <button className="mt-4 rounded bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">Save service area</button>
      </form>

      <div className="mt-6 space-y-4">
        {shops.map((shop) => (
          <article key={shop.id} className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap justify-between gap-3">
              <div>
                <h2 className="font-semibold">{shop.name}</h2>
                <p className="text-sm text-zinc-600">{shop.owner_email} · /book/{shop.slug}</p>
                <p className="mt-1 text-xs text-zinc-500">Google sign-in: {shop.owner_google_subject ? "linked" : "not linked"}{shop.owner_last_login_at ? ` · Last sign-in: ${utcDate(shop.owner_last_login_at).toLocaleString()}` : " · No recorded sign-in"}</p>
                <p className={`mt-2 text-xs font-semibold ${shop.location_verified ? "text-emerald-700" : "text-amber-700"}`}>Location: {shop.location_verified ? `${shop.location_county}, ${shop.location_country_code}` : "not yet verified"}</p>
              </div>
              <p className="text-sm">{shop.appointments} paid appointments · ${(shop.platform_fees_cents / 100).toFixed(2)} platform fees</p>
            </div>
            <div className="mt-4 rounded bg-stone-50 p-3"><p className="text-sm font-semibold">Barbers</p><div className="mt-2 flex flex-wrap gap-2">{shop.barbers.map((barber) => <span key={barber.id} className="inline-flex items-center gap-2 rounded border border-zinc-200 bg-white px-2 py-1 text-sm">{barber.display_name}{barber.is_owner ? " (owner)" : ""}{!barber.is_active && " (removed)"}{!barber.is_owner && barber.is_active && <button type="button" onClick={() => removeBarber(shop.id, barber)} className="text-xs font-semibold text-red-700">Remove</button>}</span>)}</div></div>
            <textarea className="mt-4 w-full rounded border border-zinc-300 p-3 text-sm" rows="2" placeholder="One-time message shown the next time the owner opens their dashboard" value={messages[shop.id] ?? shop.admin_message ?? ""} onChange={(event) => setMessages({ ...messages, [shop.id]: event.target.value })} />
            <div className="mt-3 flex flex-wrap gap-3">
              <button type="button" onClick={() => saveMessage(shop.id)} className="rounded bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">Send message</button>
              <button type="button" onClick={() => setPaymentAccess(shop, !shop.payment_access_override)} className="rounded border border-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-800">{shop.payment_access_override ? "Restore payment requirements" : "Grant payment-free platform access"}</button>
              <button type="button" onClick={() => removeShop(shop)} className="rounded border border-red-300 px-4 py-2 text-sm font-semibold text-red-700">Permanently remove shop</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
