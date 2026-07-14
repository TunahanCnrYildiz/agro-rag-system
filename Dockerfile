# Backend API image (FastAPI + uvicorn).
#
# The vector store and the models are NOT baked in: mount the Chroma store as a
# volume and point LM_STUDIO_BASE_URL at your model host. For local-first use
# (container talks to the LOCAL LM Studio), just run `docker compose up --build`
# — see docs/roadmap-deployment.md.
FROM python:3.12-slim

# build-essential covers any native wheels that need compiling (chromadb deps).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
