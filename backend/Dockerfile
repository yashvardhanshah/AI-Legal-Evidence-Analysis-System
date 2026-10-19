FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.lock -r requirements-ml.txt
COPY requirements-ml.lock ./
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-ml.lock && pip check
COPY requirements-phase3.lock ./
RUN pip install --no-cache-dir -r requirements-phase3.lock && pip check
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home appuser && mkdir /private_data && chown appuser:appuser /private_data
ENV PRIVATE_ROOT=/private_data HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 ANONYMIZED_TELEMETRY=False TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
