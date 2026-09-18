FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for serial and BLE support
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluetooth bluez libbluetooth-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python package
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Data volume for repeater DB and config persistence
VOLUME ["/app/data"]

# Expose web dashboard port
EXPOSE 8075

ENTRYPOINT ["python", "-m", "meshcore_pathbot"]
CMD ["--config", "/app/data/config.toml"]
