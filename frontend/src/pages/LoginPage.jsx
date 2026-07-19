import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../api";
import GoogleIcon from "../components/GoogleIcon";

export default function LoginPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const user = await apiRequest("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(form),
      });
      navigate(user.role === "platform_admin" ? "/admin" : user.role === "barber" ? "/barber/clients" : "/dashboard");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-md px-6 py-10">
      <h1 className="text-3xl font-bold">Service Provider Login</h1>
      <form onSubmit={submit} className="mt-6 grid gap-4 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
        <button
          type="button"
          onClick={() => { window.location.href = `${import.meta.env.VITE_API_BASE_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`}/api/auth/google/login`; }}
          className="flex items-center justify-center gap-3 rounded-md border border-zinc-300 px-4 py-3 text-sm font-semibold text-zinc-900 hover:bg-stone-50"
        >
          <GoogleIcon />
          Continue with Google
        </button>
        <div className="flex items-center gap-3 text-xs text-zinc-500"><span className="h-px flex-1 bg-zinc-200" />Password sign-in (temporary)<span className="h-px flex-1 bg-zinc-200" /></div>
        <label className="grid gap-2 text-sm font-medium">
          Email
          <input
            type="email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            className="rounded-md border border-zinc-300 px-3 py-2"
            required
          />
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Password
          <input
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            className="rounded-md border border-zinc-300 px-3 py-2"
            required
          />
        </label>
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <button className="rounded-md bg-zinc-950 px-4 py-3 text-sm font-semibold text-white" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </section>
  );
}
