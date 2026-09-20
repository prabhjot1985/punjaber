FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUNJABER_DB=/data/punjaber.db \
    PUNJABER_WEB=/app/web \
    PUNJABER_AUDIO=/data/audio \
    PUNJABER_RECORDINGS=/data/recordings

# espeak-ng ships a native Punjabi voice that reads Gurmukhi directly. It is
# robotic, but it is offline, identical for every learner, and gets the
# contrasts that matter right — aspiration, retroflex/dental, and tone.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dev dependencies are included so `make test` runs in the same image the app
# ships in — no second build, no drift between what is tested and what runs.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY web ./web
COPY tests ./tests

# The course audio travels with the image so a fresh deployment is not silent.
# It is seeded onto the data volume at startup rather than read from here,
# because the studio needs somewhere writable to add to it.
COPY data/recordings ./seed/recordings
ENV PUNJABER_RECORDINGS_SEED=/app/seed/recordings

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
