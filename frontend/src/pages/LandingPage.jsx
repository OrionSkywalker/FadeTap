import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../api";
import InstallAppButton from "../components/InstallAppButton";
import fadetapDarkLogo from "../assets/fadetap-logo-dark.png";
import fadetapLightLogo from "../assets/fadetap-logo-light.png";

export default function LandingPage() {
  const navigate = useNavigate();
  const [shops, setShops] = useState([]);
  const [discoveryFilters, setDiscoveryFilters] = useState({ shops: [], cities: [], states: [], services: [] });
  const [selectedFilters, setSelectedFilters] = useState({ shop_slug: "", city: "", state: "", service: "" });
  const [searchCoords, setSearchCoords] = useState(null);
  const [searchRadius, setSearchRadius] = useState(25);
  const [locationStatus, setLocationStatus] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadShops(coords = searchCoords, radius = searchRadius, filters = selectedFilters) {
    setLoading(true);
    const query = new URLSearchParams();
    if (coords) {
      query.set("lat", coords.latitude);
      query.set("lng", coords.longitude);
      query.set("max_distance_miles", radius);
    }
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const queryString = query.toString() ? `?${query.toString()}` : "";
    try {
      const response = await fetch(`${API_BASE_URL}/api/shops${queryString}`);
      setShops(response.ok ? await response.json() : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    useMyLocation({ silentFallback: true });
    fetch(`${API_BASE_URL}/api/shops/discovery-filters`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => data && setDiscoveryFilters(data))
      .catch(() => setDiscoveryFilters({ shops: [], cities: [], states: [], services: [] }));
  }, []);

  useEffect(() => {
    if (searchCoords) {
      loadShops(searchCoords, searchRadius);
    }
  }, [searchRadius]);

  function useMyLocation(options = {}) {
    if (!navigator.geolocation) {
      setLocationStatus("Location is not available in this browser.");
      loadShops();
      return;
    }
    setLocationStatus("Finding nearby shops...");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setSearchCoords(position.coords);
        loadShops(position.coords, searchRadius);
        setLocationStatus("Showing shops nearest to your current location.");
      },
      () => {
        setLocationStatus(
          options.silentFallback
            ? "Location was not shared. Showing all shops; distance sorting needs your location."
            : "Location was not shared. Showing all shops.",
        );
        setSearchCoords(null);
        loadShops(null, searchRadius);
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }

  function bookNow() {
    if (shops[0]) return navigate(`/book/${shops[0].slug}`);
    navigate("/book/demo-cuts");
  }

  function updateFilter(name, value) {
    setSelectedFilters((current) => ({ ...current, [name]: value }));
  }

  function searchProviders() {
    loadShops(searchCoords, searchRadius, selectedFilters);
  }

  function clearFilters() {
    const emptyFilters = { shop_slug: "", city: "", state: "", service: "" };
    setSelectedFilters(emptyFilters);
    loadShops(searchCoords, searchRadius, emptyFilters);
  }

  return (
    <>
      <section className="mx-auto max-w-6xl px-6 py-12">
      <div className="grid gap-8 lg:grid-cols-[1fr_0.9fr] lg:items-start">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
            Appointment booking for barber shops
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-tight text-zinc-950 sm:text-5xl">
            Find a barber, book an appointment. It's that easy.
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
            FadeTap helps shops publish live availability, collect payments, and keep calendars current.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => useMyLocation()}
              className="rounded-md bg-zinc-950 px-5 py-3 text-sm font-semibold text-white hover:bg-zinc-800"
            >
              Refresh nearby shops
            </button>
            <InstallAppButton />
          </div>
          {locationStatus && <p className="mt-3 text-sm text-zinc-600">{locationStatus}</p>}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col justify-between gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end">
            <div>
              <h2 className="text-2xl font-bold">Available shops</h2>
            </div>
            <button type="button" onClick={bookNow} className="text-sm font-semibold text-emerald-800">
              Book now
            </button>
          </div>

          <div className="mt-4 rounded-md border border-zinc-200 bg-stone-50 p-3">
            <p className="text-sm font-semibold text-zinc-800">Find a provider</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs font-semibold text-zinc-700">
                Shop
                <select value={selectedFilters.shop_slug} onChange={(event) => updateFilter("shop_slug", event.target.value)} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-normal text-zinc-900">
                  <option value="">Any shop</option>
                  {discoveryFilters.shops.map((shop) => <option key={shop.slug} value={shop.slug}>{shop.label}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold text-zinc-700">
                Service
                <select value={selectedFilters.service} onChange={(event) => updateFilter("service", event.target.value)} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-normal text-zinc-900">
                  <option value="">Any service</option>
                  {discoveryFilters.services.map((service) => <option key={service} value={service}>{service}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold text-zinc-700">
                City
                <select value={selectedFilters.city} onChange={(event) => updateFilter("city", event.target.value)} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-normal text-zinc-900">
                  <option value="">Any city</option>
                  {discoveryFilters.cities.map((city) => <option key={city} value={city}>{city}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold text-zinc-700">
                State
                <select value={selectedFilters.state} onChange={(event) => updateFilter("state", event.target.value)} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-normal text-zinc-900">
                  <option value="">Any state</option>
                  {discoveryFilters.states.map((state) => <option key={state} value={state}>{state}</option>)}
                </select>
              </label>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={searchProviders} className="rounded-md bg-zinc-950 px-3 py-2 text-sm font-semibold text-white hover:bg-zinc-800">Search providers</button>
              <button type="button" onClick={clearFilters} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-semibold text-zinc-700 hover:bg-stone-100">Clear</button>
            </div>
          </div>

          <div className="mt-4 rounded-md border border-zinc-200 bg-stone-50 p-3">
            <div className="flex items-center justify-between gap-4">
              <label htmlFor="shop-radius" className="text-sm font-semibold text-zinc-800">
                Search range
              </label>
              <span className="text-sm font-semibold text-emerald-800">{searchRadius} miles</span>
            </div>
            <input
              id="shop-radius"
              type="range"
              min="1"
              max="100"
              value={searchRadius}
              onChange={(event) => setSearchRadius(Number(event.target.value))}
              disabled={!searchCoords}
              className="mt-3 w-full"
            />
            <p className="mt-2 text-xs text-zinc-600">
              {searchCoords
                ? "Showing up to 20 closest shops in this range."
                : "Share your location to filter shops by distance."}
            </p>
          </div>

          <div className="mt-5 space-y-3">
            {loading && <p className="rounded-md bg-stone-50 p-3 text-sm text-zinc-600">Loading shops...</p>}
            {!loading && shops.length === 0 && (
              <p className="rounded-md bg-stone-50 p-3 text-sm text-zinc-600">No shops are listed yet.</p>
            )}
            {shops.map((shop) => (
              <Link
                key={shop.id}
                to={`/book/${shop.slug}`}
                className="block rounded-md border border-zinc-200 px-4 py-3 hover:border-zinc-400"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold">{shop.name}</p>
                    <p className="text-sm text-zinc-600">
                      {[shop.city, shop.state].filter(Boolean).join(", ") || "Location not listed"}
                    </p>
                    {shop.service_names?.length > 0 && (
                      <p className="mt-1 text-sm text-zinc-500">Services: {shop.service_names.join(", ")}</p>
                    )}
                    {shop.provider_names?.length > 0 && (
                      <p className="mt-1 text-sm text-zinc-500">Providers: {shop.provider_names.join(", ")}</p>
                    )}
                  </div>
                  {shop.distance_miles !== null && (
                    <p className="shrink-0 rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800">
                      {shop.distance_miles} mi
                    </p>
                  )}
                  {shop.distance_miles === null && (
                    <p className="shrink-0 rounded-md bg-stone-100 px-2 py-1 text-xs font-semibold text-zinc-600">
                      distance unavailable
                    </p>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
      </section>
      <div className="mt-4 overflow-hidden border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <img
          src={fadetapLightLogo}
          alt="FadeTap"
          className="block w-full dark:hidden"
        />
        <img src={fadetapDarkLogo} alt="" className="hidden w-full dark:block" />
      </div>
    </>
  );
}
