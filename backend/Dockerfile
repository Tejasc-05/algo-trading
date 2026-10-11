FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt requirements-quant.txt ./
RUN pip install -r requirements.txt -r requirements-quant.txt

ARG INSTALL_LOCAL_FINBERT=0
COPY requirements-sentiment.txt ./
RUN if [ "$INSTALL_LOCAL_FINBERT" = "1" ]; then pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-sentiment.txt; fi

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
