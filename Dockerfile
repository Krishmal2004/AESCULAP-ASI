FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    AESCULAP_APP_DATA=/data/app AESCULAP_DATA_DIR=/data/knowledge
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY character/ character/
COPY docs/ docs/
COPY knowledge/ knowledge/
COPY core/ core/
COPY agents/ agents/
COPY safety/ safety/
COPY eval/ eval/
COPY app/ app/
RUN useradd --create-home aesculap && mkdir -p /data && chown aesculap /data
USER aesculap
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "app", "--host", "0.0.0.0", "--port", "8000"]
