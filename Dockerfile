FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for sentence-transformers/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite + ChromaDB persistence
RUN mkdir -p /data/characters_db

# Default env vars (Railway will override via env settings)
ENV DB_PATH=/data/bookboyfriend.db
ENV CHROMA_PATH=/data/characters_db
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
