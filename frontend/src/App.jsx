import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { API_BASE_URL, apiRequest } from "./api";
import fadetapLogo from "./assets/fadetap-logo.png";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
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
    setIsMenuOpen(false);
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
        <nav className="relative mx-auto flex min-h-48 max-w-6xl items-center justify-center px-4 py-3 sm:min-h-60 sm:px-6">
          <Link to="/" aria-label="FadeTap home" className="block">
            <img src={fadetapLogo} alt="FadeTap — the grooming booking network" className="h-44 w-[22rem] object-cover object-center sm:h-56 sm:w-[34rem]" />
          </Link>
          {!isShopBookingPage && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 sm:right-6">
              <button
                type="button"
                onClick={() => setIsMenuOpen((open) => !open)}
                aria-label="Toggle navigation menu"
                aria-expanded={isMenuOpen}
                className="rounded-md p-2 text-zinc-700 transition hover:bg-stone-100 hover:text-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              {isMenuOpen && (
                <div className="absolute right-0 top-full z-20 mt-2 grid min-w-48 overflow-hidden rounded-lg border border-zinc-200 bg-white py-1 text-sm font-medium text-zinc-700 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200">
                  <button type="button" onClick={() => { setIsMenuOpen(false); bookNow(); }} className="px-4 py-3 text-left hover:bg-stone-100 dark:hover:bg-zinc-800">Book now</button>
              {user?.role === "platform_admin" ? (
                  <button type="button" onClick={logout} className="px-4 py-3 text-left hover:bg-stone-100 dark:hover:bg-zinc-800">Logout</button>
              ) : user?.role === "owner" ? (
              <>
                    <Link to="/dashboard" onClick={() => setIsMenuOpen(false)} className="px-4 py-3 hover:bg-stone-100 dark:hover:bg-zinc-800">Dashboard</Link>
                    <button type="button" onClick={logout} className="px-4 py-3 text-left hover:bg-stone-100 dark:hover:bg-zinc-800">Logout</button>
              </>
            ) : user?.role === "barber" ? (
                  <><Link to="/barber/clients" onClick={() => setIsMenuOpen(false)} className="px-4 py-3 hover:bg-stone-100 dark:hover:bg-zinc-800">My clients</Link><button type="button" onClick={logout} className="px-4 py-3 text-left hover:bg-stone-100 dark:hover:bg-zinc-800">Logout</button></>
            ) : (
              <>
                    <Link to="/register" onClick={() => setIsMenuOpen(false)} className="px-4 py-3 hover:bg-stone-100 dark:hover:bg-zinc-800">Open a Shop</Link>
                    <Link to="/login" onClick={() => setIsMenuOpen(false)} className="px-4 py-3 hover:bg-stone-100 dark:hover:bg-zinc-800">Login</Link>
              </>
              )}
                </div>
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
