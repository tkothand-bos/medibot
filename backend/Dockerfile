FROM python:3.11-slim

WORKDIR /srv/medibot

# System deps for docling / pdf parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# mediassist.db is mounted at runtime: -v $(pwd)/data:/srv/data
ENV SQLITE_DB_PATH=/srv/data/mediassist.db \
    DATA_DIR=/srv/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
