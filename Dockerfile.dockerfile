FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates unzip \
    xvfb \
    python3 python3-pip \
    libglib2.0-0 libpng16-16 \
    libsm6 libxrender1 libxext6 libx11-6 \
    libxcb1 libglu1-mesa libdbus-1-3 \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------
# MuseScore 4.4.4 via AppImage
# ----------------------------------------
RUN wget -q \
    "https://github.com/musescore/MuseScore/releases/download/v4.4.4/MuseScore-Studio-4.4.4.243461245-x86_64.AppImage" \
    -O /tmp/musescore.AppImage \
    && chmod +x /tmp/musescore.AppImage \
    && cd /tmp \
    && ./musescore.AppImage --appimage-extract \
    && mv /tmp/squashfs-root /opt/musescore \
    && rm /tmp/musescore.AppImage \
    && echo "=== MuseScore bin ===" \
    && ls -la /opt/musescore/bin/

ENV MUSESCORE_CLI=/opt/musescore/bin/mscore4portable

# ----------------------------------------
# App
# ----------------------------------------
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY app.py .
RUN mkdir -p /app/data

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]