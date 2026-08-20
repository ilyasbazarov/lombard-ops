import React from "react";
import Login from "./pages/Login.jsx";
import Catalog from "./pages/Catalog.jsx";

// T-2-4: путь /catalog добавлен рядом с /login. Простой роутинг по window.location.pathname
// (react-router не обязателен на этом шаге — брифом T-2-4 решает исполнитель).
// Реестр /, карточка /loan, /assess, /offer — T-2-2, T-2-3, T-2-5, вне scope этой задачи.
export default function App() {
  if (window.location.pathname === "/catalog") {
    return <Catalog />;
  }
  return <Login />;
}
