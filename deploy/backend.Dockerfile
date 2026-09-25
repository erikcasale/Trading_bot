FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# emergentintegrations serve solo alla funzione AI (import lazy, non nel cockpit) e
# crea un conflitto di dipendenze con litellm: la escludiamo dal build del VPS.
RUN grep -viE '^emergentintegrations' requirements.txt > req.vps.txt \
    && pip install -r req.vps.txt

COPY backend/ .

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
