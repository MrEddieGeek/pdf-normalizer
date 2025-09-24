import os
import subprocess
import logging
import glob
from flask import Flask, request, send_file, render_template, flash, redirect, url_for
from werkzeug.utils import secure_filename
import magic

# Configurar logging para producción
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['OUTPUT_FOLDER'] = "outputs"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Límite de 16MB
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super_secret_key')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def validate_pdf(file_path):
    """Valida que el archivo sea un PDF usando python-magic."""
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(file_path)
    logger.info(f"Validando archivo: {file_path}, MIME: {mime_type}")
    return mime_type == 'application/pdf'

def check_dpi(pdf_path):
    """Verifica los DPI de las imágenes en un PDF usando pdfimages."""
    logger.info(f"Verificando DPI del archivo: {pdf_path}")
    try:
        result = subprocess.run(['pdfimages', '-list', pdf_path], capture_output=True, text=True, check=True)
        logger.info(f"Salida completa de pdfimages: {result.stdout}")
        dpi_lines = [line for line in result.stdout.splitlines() if 'image' in line]
        dpi_values = []
        for line in dpi_lines:
            parts = line.split()
            try:
                # DPI suelen estar en columnas 10 y 11, pero verificamos dinámicamente
                if len(parts) >= 12 and parts[8].isdigit() and parts[9].isdigit():
                    dpi_x, dpi_y = float(parts[10]), float(parts[11])
                    dpi_values.append((int(parts[0]), min(dpi_x, dpi_y)))  # Página y DPI mínimo
                else:
                    logger.warning(f"Formato inesperado en línea de pdfimages: {line}")
            except (IndexError, ValueError) as e:
                logger.warning(f"Error al parsear línea de pdfimages: {line}, error: {e}")
                continue
        logger.info(f"DPI detectados: {dpi_values}")
        return dpi_values
    except subprocess.CalledProcessError as e:
        logger.error(f"Error al verificar DPI: {e.stderr}")
        flash(f"Error al verificar DPI: {e.stderr}", "error")
        return []

@app.route("/", methods=["GET", "POST"])
def index():
    logger.info(f"Recibida solicitud: {request.method} {request.url}")
    if request.method == "POST":
        if 'file' not in request.files:
            logger.error("No se seleccionó ningún archivo.")
            flash("No se seleccionó ningún archivo.", "error")
            return redirect(url_for('index'))

        file = request.files['file']
        if file.filename == '':
            logger.error("No se seleccionó ningún archivo (nombre vacío).")
            flash("No se seleccionó ningún archivo.", "error")
            return redirect(url_for('index'))

        if not file.filename.lower().endswith('.pdf'):
            logger.error(f"Archivo no es PDF: {file.filename}")
            flash("El archivo debe ser un PDF.", "error")
            return redirect(url_for('index'))

        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"normalizado_{filename}")
        logger.info(f"Guardando archivo en: {input_path}")
        file.save(input_path)

        if not validate_pdf(input_path):
            logger.error(f"Archivo no es un PDF válido: {input_path}")
            os.remove(input_path)
            flash("El archivo subido no es un PDF válido.", "error")
            return redirect(url_for('index'))

        # Verificar DPI iniciales
        dpi_values = check_dpi(input_path)
        if dpi_values:
            invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 290 or dpi > 310]
            if invalid_dpis:
                logger.warning(f"DPI inválidos detectados en el PDF original: {invalid_dpis}")
                flash(f"DPI inválidos detectados: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}", "warning")
            else:
                logger.info("Todos los DPI están dentro del rango permitido.")
                flash("Todos los DPI están dentro del rango permitido.", "info")
        else:
            logger.warning("No se detectaron imágenes o error al verificar DPI en el PDF original.")
            flash("No se detectaron imágenes en el PDF original o error al verificar DPI.", "warning")

        # Normalizar PDF con Ghostscript (300 DPI, escala de grises, PDF/A-1b)
        try:
            logger.info(f"Normalizando PDF: {input_path} -> {output_path}")
            cmd = [
                'gs',
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.4',
                '-dPDFA=1',  # PDF/A-1b para VUCEM
                '-dPDFACompatibilityPolicy=1',
                '-dNOPAUSE', '-dBATCH', '-dQUIET',
                '-dAutoFilterColorImages=false',
                '-dColorImageFilter=/DCTEncode',
                '-dColorImageResolution=300',
                '-dGrayImageResolution=300',
                '-dMonoImageResolution=300',
                '-sColorConversionStrategy=Gray',
                '-dProcessColorModel=/DeviceGray',
                '-dDownsampleColorImages=true',
                '-dDownsampleGrayImages=true',
                '-dDownsampleMonoImages=true',
                '-dColorImageDownsampleType=/Bicubic',  # Mejor calidad de reescalado
                '-dGrayImageDownsampleType=/Bicubic',
                '-dMonoImageDownsampleType=/Bicubic',
                '-dColorImageDownsampleThreshold=1.0',
                '-dGrayImageDownsampleThreshold=1.0',
                '-dMonoImageDownsampleThreshold=1.0',
                '-dPreserveOPIComments=false',
                '-dUseCropBox=true',
                f'-sOutputFile={output_path}',
                input_path
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Ghostscript ejecutado con éxito: {result.stdout}")

            # Verificar DPI del PDF resultante
            dpi_values = check_dpi(output_path)
            if dpi_values:
                invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 290 or dpi > 310]
                if invalid_dpis:
                    logger.error(f"El PDF normalizado tiene DPI inválidos: {invalid_dpis}")
                    flash(f"El PDF normalizado tiene DPI inválidos: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}. Inténtalo de nuevo o contacta al soporte.", "error")
                    os.remove(input_path)
                    os.remove(output_path)
                    return redirect(url_for('index'))
                else:
                    logger.info("PDF normalizado correctamente a 300 DPI en escala de grises.")
                    flash("PDF normalizado correctamente a 300 DPI en escala de grises.", "success")
            else:
                logger.warning("No se detectaron imágenes en el PDF normalizado.")
                flash("No se detectaron imágenes en el PDF normalizado, pero el procesamiento continuó.", "warning")

            logger.info(f"Enviando archivo normalizado: {output_path}")
            response = send_file(output_path, as_attachment=True)

            # Limpiar archivos temporales
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
                for f in os.listdir(folder):
                    try:
                        os.remove(os.path.join(folder, f))
                    except Exception as e:
                        logger.warning(f"Error al eliminar archivo {f}: {e}")

            return response

        except subprocess.CalledProcessError as e:
            logger.error(f"Error al procesar el PDF: {e.stderr}")
            flash(f"Error al procesar el PDF: {e.stderr}", "error")
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        try:
                            os.remove(os.path.join(folder, f))
                        except Exception as e:
                            logger.warning(f"Error al eliminar archivo {f}: {e}")
            return redirect(url_for('index'))

    template_path = os.path.join(app.template_folder, 'index.html')
    if not os.path.exists(template_path):
        logger.error("Template index.html no encontrado.")
        return "Error: Template index.html no encontrado.", 500

    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True)