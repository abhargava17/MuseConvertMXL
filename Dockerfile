FROM debian:12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates unzip \
    python3 python3-pip \
    libglib2.0-0 libpng16-16 \
    libsm6 libxrender1 libxext6 libx11-6 \
    libxcb1 libglu1-mesa libdbus-1-3 \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 \
    libxkbcommon0 libxkbcommon-x11-0 libxkbcommon-dev libxkbcommon-x11-dev \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    libegl1 libegl-mesa0 \
    libfontconfig1 \
    libfreetype6 \
    libxcb-glx0 \
    libxcb-xkb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-render0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-util1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xtest0 \
    libgl1 \
    libglx-mesa0 \
    libglx0 \
    libpulse0 \
    libopengl0 \
    && rm -rf /var/lib/apt/lists/*

# Download MuseScore AppImage and extract it
RUN wget -q \
    "https://github.com/musescore/MuseScore/releases/download/v4.4.4/MuseScore-Studio-4.4.4.243461245-x86_64.AppImage" \
    -O /tmp/musescore.AppImage \
    && chmod +x /tmp/musescore.AppImage \
    && cd /tmp \
    && ./musescore.AppImage --appimage-extract \
    && mv /tmp/squashfs-root /opt/musescore \
    && rm /tmp/musescore.AppImage

# Use the portable binary directly (headless mode)
ENV MUSESCORE_CLI=/opt/musescore/bin/mscore4portable
ENV QT_QPA_PLATFORM=offscreen

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py .

# Copy engraving style files
COPY styles/ /app/styles/

CMD ["python3", "app.py"]
