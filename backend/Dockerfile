FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt requirements-quant.txt ./
RUN pip install -r requirements.txt -r requirements-quant.txt

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
