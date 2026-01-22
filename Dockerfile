FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only what's needed for install/build first (better caching)
COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

CMD ["python", "-m", "fuj_coherent_receiver_gui"]
