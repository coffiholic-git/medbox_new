FROM python:3.12-slim

WORKDIR /app

# tesseract-ocr is optional at runtime: backend/services/ocr_service.py
# detects its absence and falls back to a labelled simulated OCR read,
# so the image builds and runs fine without it — installed here so the
# real OCR path also works out of the box.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Build context is the backend/ folder itself; everything gets copied
# into /app/backend so `backend.main:app` still resolves as a package
# (backend/__init__.py makes it one) with the app run from /app.
COPY requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . ./backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
