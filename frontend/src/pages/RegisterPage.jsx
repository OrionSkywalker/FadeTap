import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest } from "../api";

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    slug: "",
    owner_name: "",
    owner_email: "",
    timezone: "America/Los_Angeles",
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleEmail, setGoogleEmail] = useState("");

  useEffect(() => {
    apiRequest("/api/auth/me").then((user) => {
      setGoogleEmail(user.email);
      setForm((current) => ({ ...current, owner_email: user.email }));
    }).catch(() => setGoogleEmail(""));
  }, []);

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: name === "slug" ? value.toLowerCase().replace(/[^a-z0-9-]/g, "") : value,
    }));
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const data = await apiRequest("/api/shops/register", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setResult(data);
      if (data.setup_checkout_url) {
        window.location.href = data.setup_checkout_url;
        return;
      } else {
        navigate("/dashboard");
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8">
        <div className="flex items-center justify-between gap-4"><p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">Shop setup</p><Link to="/faq" className="text-sm font-semibold text-emerald-700 hover:underline">FAQ</Link></div>
        <h1 className="mt-2 text-3xl font-bold">Open your booking page</h1>
        <p className="mt-3 text-zinc-700">
          Sign in with Google, reserve a shop URL, and continue directly to the one-time setup payment before publishing live bookings.
        </p>
      </div>

      {!googleEmail ? (
        <div className="grid gap-4 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-zinc-700">Use your Google account to create and manage this shop. FadeTap does not collect a password.</p>
          <button type="button" onClick={() => { window.location.href = `${import.meta.env.VITE_API_BASE_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`}/api/auth/google/login?next=register`; }} className="rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white">Continue with Google</button>
        </div>
      ) : <form onSubmit={submit} className="grid gap-4 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
        {[
          ["name", "Shop name", "Fresh Cuts"],
          ["slug", "Booking slug", "fresh-cuts"],
          ["owner_name", "Owner display name", "Ryan"],
          ["owner_email", "Google account email", "owner@example.com"],
        ].map(([name, label, placeholder]) => (
          <label key={name} className="grid gap-2 text-sm font-medium text-zinc-800">
            {label}
            <input
              name={name}
              type={name.includes("email") ? "email" : "text"}
              value={form[name]}
              onChange={updateField}
              readOnly={name === "owner_email"}
              placeholder={placeholder}
              required
              className="rounded-md border border-zinc-300 px-3 py-2 text-zinc-950 outline-none focus:border-emerald-700"
            />
          </label>
        ))}

        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white hover:bg-zinc-800 disabled:bg-zinc-300"
        >
          {loading ? "Creating..." : "Create shop and pay setup fee"}
        </button>
      </form>}

      {result && (
        <div className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900">
          <p className="font-semibold">{result.message}</p>
          {result.setup_checkout_url && <p className="mt-2">Redirecting to Stripe Checkout...</p>}
        </div>
      )}
    </section>
  );
}
