import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["fadetap-app-logo-192.png", "fadetap-app-logo-512.png"],
      manifest: {
        name: "FadeTap",
        short_name: "FadeTap",
        description: "The grooming booking network.",
        theme_color: "#07523F",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/fadetap-app-logo-192.png", sizes: "192x192", type: "image/png" },
          { src: "/fadetap-app-logo-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
      },
      devOptions: {
        enabled: true,
        type: "module",
      },
    }),
  ],
  server: {
    port: 5173,
  },
});
