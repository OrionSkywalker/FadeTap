import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import BarberClientsPage from "./pages/BarberClientsPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import FaqPage from "./pages/FaqPage.jsx";
import LandingPage from "./pages/LandingPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import ShopBookingPage from "./pages/ShopBookingPage.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<LandingPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="barber/clients" element={<BarberClientsPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="faq" element={<FaqPage />} />
          <Route path="book/:shopSlug" element={<ShopBookingPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
