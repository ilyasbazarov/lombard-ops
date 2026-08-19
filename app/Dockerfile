# app-lombard — единый образ Cloud Run service (бриф T-2-1).
# Стадия 1: сборка React frontend в статику; стадия 2: Flask API (gunicorn) отдаёт API + статику.
#
# Сборка билд-аккаунтом lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
# (11_INFRA_FACTS.md, ADR-076/ADR-077) — команда сборки/деплоя в scripts/T-2-1_deploy.sh, класс B.

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY
ENV VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN
ENV VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-build /frontend/dist ../frontend/dist
ENV PORT=8080
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
