import React, { useState } from "react";
import { signInWithEmailAndPassword } from "firebase/auth";
import { auth } from "../firebase.js";

// Экран /login — 12_UX_CONTRACT.md §3.1: поля адрес почты + пароль, self-signup выключен
// (заводится только скриптом T-2-1_identity_platform_setup.sh, класс B), ошибка входа —
// одним сообщением без различения "нет пользователя" / "неверный пароль".
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [tokenPreview, setTokenPreview] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setTokenPreview("");
    try {
      const cred = await signInWithEmailAndPassword(auth, email, password);
      const idResult = await cred.user.getIdToken();
      // Токен целиком в UI/лог не печатается (секрет сессии) — только факт получения и префикс.
      setTokenPreview(idResult.slice(0, 12) + "…");
    } catch (err) {
      setError("Не удалось войти: проверьте почту и пароль.");
    }
  }

  return (
    <main style={{ maxWidth: 360, margin: "10vh auto", fontFamily: "sans-serif" }}>
      <h1>app-lombard — вход</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="email">Адрес почты</label>
          <br />
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div style={{ marginTop: 8 }}>
          <label htmlFor="password">Пароль</label>
          <br />
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" style={{ marginTop: 12 }}>
          Войти
        </button>
      </form>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {tokenPreview && <p>Токен получен: {tokenPreview}</p>}
    </main>
  );
}
