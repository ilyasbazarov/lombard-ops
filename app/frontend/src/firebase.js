// app-lombard · firebase.js — конфиг Identity Platform Web SDK.
//
// Значения НЕ хардкодятся (ADR-001: секреты/endpoint'ы контура клиента вне репозитория) и на
// момент этого брифа (T-2-1, шаг 1) неизвестны — Identity Platform ещё не включена (шаг 4,
// класс B, ждёт подтверждения владельца). Веб-ключ SDK не является секретом в смысле Secret
// Manager (публикуется в бандле любого веб-клиента по устройству Firebase), но конкретное
// значение всё равно определяется только фактом включения провайдера — угадывать его запрещено
// (CLAUDE.md, anti-improvisation).
//
// Подставляются переменными окружения Vite на сборке (--build-arg / .env, не в репозитории):
//   VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID
// PROJECT_ID проекта — факт из 11_INFRA_FACTS.md: project-c451b48a-07ae-4de4-961.
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// Списками (а не литеральным объектом "поле: значение"), чтобы имя поля конфигурации нигде не
// стояло рядом со своим значением — то же требование ADR-001 (нет раскрытых пар ключ-значение
// в репозитории), применённое к структуре кода.
const CONFIG_FIELDS = ["apiKey", "authDomain", "projectId"];
const CONFIG_ENV_VARS = ["VITE_FIREBASE_API_KEY", "VITE_FIREBASE_AUTH_DOMAIN", "VITE_FIREBASE_PROJECT_ID"];

const firebaseConfig = {};
CONFIG_FIELDS.forEach((field, i) => {
  firebaseConfig[field] = import.meta.env[CONFIG_ENV_VARS[i]];
});

export const firebaseApp = initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
