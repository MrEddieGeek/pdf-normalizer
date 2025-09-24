# Usa una imagen base de Python
FROM python:3.12-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema
RUN apt-get update && apt-get install -y \
    poppler-utils \
    ghostscript \
    libmagic1 \
    img2pdf \
    && rm -rf /var/lib/apt/lists/*

# Copia los archivos del proyecto
COPY . /app

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto (si usas Flask/Gunicorn)
EXPOSE 5000

# Comando para iniciar la aplicación (puedes ajustarlo con Docker Command si es necesario)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "300", "--preload", "app:app"]