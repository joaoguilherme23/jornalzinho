FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home jornalzinho
WORKDIR /app
COPY requirements.txt requirements.resolved.txt ./
RUN pip install --no-cache-dir -r requirements.resolved.txt -r requirements.txt
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY scripts ./scripts
COPY --from=frontend /frontend/dist ./frontend/dist
RUN mkdir /dados && chown jornalzinho:jornalzinho /dados
USER 10001:10001
EXPOSE 8099
CMD ["python", "-m", "uvicorn", "app.main:aplicacao", "--host", "0.0.0.0", "--port", "8099", "--no-access-log"]
