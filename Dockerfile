# Single origin (ADR-0001): one image, one process, one URL. The Vue bundle is
# built here and served by FastAPI as static files, so there is no second service
# and no CORS.

FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.13-slim
WORKDIR /app

COPY pyproject.toml ./
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/ ./data/
RUN pip install --no-cache-dir .

# The built bundle, at the path app/main.py mounts (frontend/dist).
COPY --from=frontend /build/frontend/dist ./frontend/dist

# SQLite lives on the attached persistent volume, not in the image layer —
# Railway's filesystem is otherwise replaced on every deploy.
ENV DATABASE_URL=sqlite:////data/hardware_hub.db

CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
