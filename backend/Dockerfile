FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --create-home aiquery \
    && install -d -m 0700 -o aiquery -g aiquery /data
USER aiquery
EXPOSE 8000
CMD ["sh", "-c", "python -m app.seed && exec python -m app"]
