import { Link } from "react-router-dom";

const questions = [
  ["What is FadeTap?", "FadeTap is a scheduling and payment platform for appointment-based businesses. It gives each shop a booking page, live availability, payment collection, barber calendars, and client history."],
  ["Why should I use FadeTap?", "It keeps booking, availability, client information, and payment collection in one place, while clients can book without creating their own account."],
  ["How much does it cost?", "A one-time shop setup payment is collected when you publish. FadeTap platform fees from bookings are capped at $25 per shop per calendar month. After that cap is reached, the shop keeps the rest of its booking funds for that month. A shop can also choose to pay $25 for monthly access."],
  ["Is it safe?", "Shop and barber access uses Google sign-in, booking payments are processed by Stripe, and clients do not need accounts. FadeTap only requests the information needed to provide scheduling and payment features."],
  ["Does it cost more to add users to my account?", "No. Adding additional barbers or service providers does not add a per-user charge."],
  ["Is it only for barbers?", "No. FadeTap was designed around barber-shop workflows, but any appointment-based provider can use it to offer their own services."],
];

export default function FaqPage() {
  return <section className="mx-auto max-w-3xl px-6 py-10"><Link to="/register" className="text-sm font-semibold text-emerald-700 hover:underline">← Back to shop setup</Link><h1 className="mt-4 text-3xl font-bold">Frequently asked questions</h1><div className="mt-6 space-y-4">{questions.map(([question, answer]) => <article key={question} className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm"><h2 className="text-lg font-semibold">{question}</h2><p className="mt-2 leading-7 text-zinc-700">{answer}</p></article>)}</div></section>;
}
