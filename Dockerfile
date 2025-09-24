# Usa Python 3.12 como base
FROM python:3.12-slim

# Instala paquetes del sistema necesarios (Ghostscript, ImageMagick, etc.)
RUN apt-get update && apt-get install -y \
    ghostscript \
    imagemagick \
    poppler-utils \
    img2pdf \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copia el código de la app
COPY . /app

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto (Render usa $PORT automáticamente)
EXPOSE $PORT

# Comando para iniciar la app con Gunicorn (usa $PORT de Render)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--timeout", "0"]