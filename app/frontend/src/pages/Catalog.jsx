import React, { useEffect, useState } from "react";
import { auth } from "../firebase.js";

// Экран /catalog — 12_UX_CONTRACT.md §3.6: справочник ликвидности, только просмотр, все три роли
// (§4). Таблица vehicle_catalog как есть: марка, модель, класс, LTV макс, скупочная база,
// комментарий, price_source, updated_at (02 §2). Баннер синтетичности — §7.2/ADR-064 п.2: пока
// есть хоть одна строка price_source=synthetic, показывается; скрывается сама при N=0.
export default function Catalog() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const user = auth.currentUser;
        if (!user) {
          if (!cancelled) {
            setError("Нужен вход, чтобы увидеть справочник.");
            setLoading(false);
          }
          return;
        }
        const idResult = await user.getIdToken();
        const resp = await fetch("/api/catalog", {
          headers: { Authorization: "Bearer " + idResult },
        });
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        const data = await resp.json();
        if (!cancelled) {
          setRows(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError("Не удалось загрузить справочник.");
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const syntheticCount = rows.filter((r) => r.price_source === "synthetic").length;

  return (
    <main style={{ maxWidth: 900, margin: "5vh auto", fontFamily: "sans-serif" }}>
      <h1>Справочник ликвидности</h1>

      {syntheticCount > 0 && (
        <p style={{ background: "#fff3cd", padding: 8, border: "1px solid #ffe08a" }}>
          Справочник синтетический, строк {syntheticCount}. Скупочная цена по этим маркам — мок,
          не рыночное значение.
        </p>
      )}

      {loading && <p>Загрузка…</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {!loading && !error && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={cellStyle}>Марка</th>
              <th style={cellStyle}>Модель</th>
              <th style={cellStyle}>Класс</th>
              <th style={cellStyle}>LTV макс</th>
              <th style={cellStyle}>Скупочная база</th>
              <th style={cellStyle}>Комментарий</th>
              <th style={cellStyle}>price_source</th>
              <th style={cellStyle}>updated_at</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={cellStyle}>{r.make}</td>
                <td style={cellStyle}>{r.model}</td>
                <td style={cellStyle}>{classLabel(r.liquidity_class)}</td>
                <td style={cellStyle}>{r.ltv_max != null ? Math.round(r.ltv_max * 100) + "%" : "—"}</td>
                <td style={cellStyle}>{r.buyout_price != null ? r.buyout_price : "—"}</td>
                <td style={cellStyle}>{r.comment || "—"}</td>
                <td style={cellStyle}>{r.price_source}</td>
                <td style={cellStyle}>{r.updated_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function classLabel(liquidityClass) {
  if (liquidityClass === "green") return "🟢";
  if (liquidityClass === "yellow") return "🟡";
  if (liquidityClass === "red") return "🔴";
  return liquidityClass || "—";
}

const cellStyle = { border: "1px solid #ddd", padding: "6px 8px", textAlign: "left" };
