FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    poppler-utils \
    ghostscript \
    libmagic1 \
    img2pdf \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "--preload", "app:app"]