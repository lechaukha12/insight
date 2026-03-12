FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install OTel auto-instrumentation bootstrap (installs all instrumentors)
RUN opentelemetry-bootstrap -a install 2>/dev/null || true

COPY app.py .

ENV APP_PORT=8091
EXPOSE 8091

# Use opentelemetry-instrument to auto-instrument the app
CMD ["opentelemetry-instrument", "python", "app.py"]
