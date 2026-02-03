# Use a lightweight Python version
FROM python:3.10-slim

# 1. Install System Dependencies (The "Missing Libraries")
# WeasyPrint needs Pango, Cairo, and GDK-PixBuf to render images.
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up the App Directory
WORKDIR /app

# 3. Install Python Libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy Bot Code & Run
COPY . .
CMD ["python", "bot.py"]