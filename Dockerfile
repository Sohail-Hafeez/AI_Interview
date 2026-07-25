# --- Stage 1: build the React SPA ---
FROM node:22-alpine AS frontend

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Empty base makes every fetch same-origin. Requires the `??` fallback in
# HRDashboard.tsx / InterviewPage.tsx -- with `||` this would fall through
# to localhost:8000 and break every API call.
ENV VITE_API_BASE=""
RUN npm run build


# --- Stage 2: FastAPI backend + the built SPA ---
FROM python:3.12-slim

WORKDIR /app

# libpq for psycopg2, curl for the container healthcheck
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/dist ./static

ENV PORT=8001
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT}/api/candidates" > /dev/null || exit 1

# opentelemetry-instrument installs the TracerProvider and the OTLP exporters.
# Without it main.py's tracer is a no-op and no spans are ever exported.
# Single worker only: interview state lives in a process-local dict (main.py).
CMD ["sh", "-c", "opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
