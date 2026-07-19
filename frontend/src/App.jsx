import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { API_BASE_URL, apiRequest } from "./api";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const isShopBookingPage = location.pathname.startsWith("/book/");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    let isMounted = true;

    async function loadCurrentUser() {
      try {
        const currentUser = await apiRequest("/api/auth/me");
        if (isMounted) setUser(currentUser);
      } catch {
        if (isMounted) setUser(null);
      }
    }

    loadCurrentUser();

    return () => {
      isMounted = false;
    };
  }, [location.pathname]);

  async function logout() {
    await apiRequest("/api/auth/logout", { method: "POST" });
    setUser(null);
    navigate("/");
  }

  function bookNow() {
    const openNearestShop = async (coords) => {
      try {
        const query = new URLSearchParams({
          lat: String(coords.latitude),
          lng: String(coords.longitude),
          max_distance_miles: "25",
        });
        const response = await fetch(`${API_BASE_URL}/api/shops?${query}`);
        const shops = response.ok ? await response.json() : [];
        navigate(shops[0] ? `/book/${shops[0].slug}` : "/book/demo-cuts");
      } catch {
        navigate("/book/demo-cuts");
      }
    };
    if (!navigator.geolocation) {
      navigate("/book/demo-cuts");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => openNearestShop(position.coords),
      () => navigate("/book/demo-cuts"),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }

  return (
    <div className="min-h-screen bg-stone-50 text-zinc-950 transition-colors dark:bg-zinc-950 dark:text-zinc-50">
      <header className="border-b border-zinc-200 bg-white transition-colors dark:border-zinc-800 dark:bg-zinc-950">
        <nav className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <Link to="/" className="text-lg font-semibold leading-none text-zinc-950 dark:text-zinc-50">
            FadeTap
          </Link>
          {!isShopBookingPage && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              <button type="button" onClick={bookNow} className="hover:text-zinc-950 dark:hover:text-white">Book now</button>
              {user?.role === "platform_admin" ? (
              <button type="button" onClick={logout} className="font-medium hover:text-zinc-950 dark:hover:text-white">Logout</button>
              ) : user?.role === "owner" ? (
              <>
                <Link to="/dashboard" className="hover:text-zinc-950 dark:hover:text-white">
                  Dashboard
                </Link>
                <button type="button" onClick={logout} className="font-medium hover:text-zinc-950 dark:hover:text-white">
                  Logout
                </button>
              </>
            ) : user?.role === "barber" ? (
              <><Link to="/barber/clients" className="hover:text-zinc-950 dark:hover:text-white">My clients</Link><button type="button" onClick={logout} className="font-medium hover:text-zinc-950 dark:hover:text-white">Logout</button></>
            ) : (
              <>
                <Link to="/register" className="hover:text-zinc-950 dark:hover:text-white">
                  Open a Shop
                </Link>
                <Link to="/login" className="hover:text-zinc-950 dark:hover:text-white">
                  Login
                </Link>
              </>
              )}
            </div>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="px-6 py-8 text-center">
        <button
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="text-xs font-medium text-zinc-500 hover:text-zinc-950 dark:text-zinc-400 dark:hover:text-white"
        >
          Switch to {theme === "dark" ? "light" : "dark"} theme
        </button>
      </footer>
    </div>
  );
}
