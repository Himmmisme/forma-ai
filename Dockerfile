FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    APP_DATA_DIR=/var/lib/forma/data APP_SECRET_DIR=/var/lib/forma/secrets \
    APP_WEB_DIR=/app/web APP_DEMO_IMAGE=/app/web/forma-product.webp
WORKDIR /app/backend
RUN groupadd --gid 10001 forma \
    && useradd --uid 10001 --gid 10001 --no-create-home forma \
    && install -d -m 0750 -o forma -g forma /var/lib/forma/data /var/lib/forma/secrets
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=web /build/dist /app/web
COPY --chmod=755 scripts/entrypoint.sh /usr/local/bin/forma-entrypoint
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["forma-entrypoint"]
