import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest } from "../api";

const utcDate = (value) => new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);

export default function BarberClientsPage() {
  const [clients, setClients] = useState(null);
  const [searchParams] = useSearchParams();
  const barberId = searchParams.get("barber_id");
  const [noteDrafts, setNoteDrafts] = useState({});
  const [error, setError] = useState("");
  const load = () => apiRequest(`/api/barber/clients${barberId ? `?barber_id=${barberId}` : ""}`).then(setClients).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [barberId]);
  async function addNote(client) { const body = noteDrafts[client.client_key]?.trim(); if (!body || !barberId) return; await apiRequest(`/api/barber/clients/${barberId}/${encodeURIComponent(client.client_key)}/notes`, { method: "POST", body: JSON.stringify({ body }) }); setNoteDrafts({ ...noteDrafts, [client.client_key]: "" }); load(); }
  if (error === "Not authenticated") return <section className="mx-auto max-w-3xl px-6 py-10"><h1 className="text-3xl font-bold">Login required</h1><Link to="/login" className="mt-4 inline-block text-emerald-700">Login</Link></section>;
  if (error) return <section className="mx-auto max-w-3xl px-6 py-10"><p className="rounded bg-red-50 p-3 text-red-700">{error}</p></section>;
  if (!clients) return <section className="mx-auto max-w-5xl px-6 py-10">Loading clients...</section>;
  return <section className="mx-auto max-w-5xl px-6 py-10"><Link to="/dashboard" className="text-sm font-semibold text-emerald-700 hover:underline">← Back to dashboard</Link><h1 className="mt-3 text-3xl font-bold">Client list</h1><p className="mt-2 text-zinc-600">Private appointment history and notes for the selected barber.</p><div className="mt-6 space-y-3">{clients.map((client, index) => <article key={`${client.client_name}-${index}`} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-semibold">{client.client_name || "Guest client"}</h2><p className="text-sm text-zinc-600">{client.sms_opt_in ? client.client_phone : "No phone number shared"}</p></div><p className="text-sm font-medium">{client.total_appointments} appointment{client.total_appointments === 1 ? "" : "s"}</p></div><p className="mt-3 text-sm text-zinc-700">Last service: {client.last_service_name || "—"} · Last visit: {utcDate(client.last_appointment_at).toLocaleDateString()}</p>{client.next_appointment_at && <p className="mt-1 text-sm text-emerald-700">Next appointment: {utcDate(client.next_appointment_at).toLocaleString()}</p>}<div className="mt-3 rounded bg-stone-50 p-3 text-sm"><p className="font-semibold">Private notes</p>{client.notes.map((note, noteIndex) => <p key={noteIndex} className="mt-1 text-zinc-700">• {note}</p>)}<textarea value={noteDrafts[client.client_key] ?? ""} onChange={(e) => setNoteDrafts({ ...noteDrafts, [client.client_key]: e.target.value })} placeholder="Add a private note, such as updated contact details" rows="2" className="mt-3 w-full rounded border border-zinc-300 p-2" />{barberId && <button type="button" onClick={() => addNote(client)} className="mt-2 rounded bg-zinc-950 px-3 py-2 text-xs font-semibold text-white">Save note</button>}</div></article>)}{clients.length === 0 && <p className="rounded bg-stone-100 p-4 text-zinc-600">No confirmed clients yet.</p>}</div></section>;
}
