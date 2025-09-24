import os
import subprocess
from flask import Flask, request, send_file, render_template, flash, redirect, url_for
from werkzeug.utils import secure_filename
import magic

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
    return mime.from_file(file_path) == 'application/pdf'

def check_dpi(pdf_path):
    """Verifica los DPI de las imágenes en un PDF usando pdfimages."""
    try:
        result = subprocess.run(['pdfimages', '-list', pdf_path], capture_output=True, text=True, check=True)
        dpi_lines = [line for line in result.stdout.splitlines() if 'image' in line]
        dpi_values = []
        for line in dpi_lines:
            parts = line.split()
            try:
                dpi_x, dpi_y = float(parts[8]), float(parts[9])  # Columnas de DPI
                dpi_values.append((int(parts[0]), min(dpi_x, dpi_y)))  # Página y DPI mínimo
            except (IndexError, ValueError):
                continue
        return dpi_values
    except subprocess.CalledProcessError as e:
        flash(f"Error al verificar DPI: {e.stderr}", "error")
        return []

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if 'file' not in request.files:
            flash("No se seleccionó ningún archivo.", "error")
            return redirect(url_for('index'))

        file = request.files['file']
        if file.filename == '':
            flash("No se seleccionó ningún archivo.", "error")
            return redirect(url_for('index'))

        if not file.filename.lower().endswith('.pdf'):
            flash("El archivo debe ser un PDF.", "error")
            return redirect(url_for('index'))

        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"normalizado_{filename}")
        file.save(input_path)

        if not validate_pdf(input_path):
            os.remove(input_path)
            flash("El archivo subido no es un PDF válido.", "error")
            return redirect(url_for('index'))

        # Verificar DPI iniciales
        dpi_values = check_dpi(input_path)
        if dpi_values:
            invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 290 or dpi > 310]  # Tolerancia ±10 DPI
            if invalid_dpis:
                flash(f"DPI inválidos detectados en el PDF original: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}", "warning")
            else:
                flash("Todos los DPI están dentro del rango permitido.", "info")

        # Normalizar PDF con Ghostscript (300 DPI, escala de grises, PDF/A-1b)
        try:
            cmd = [
                'gs',
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.4',
                '-dPDFA=1',  # Cambiado a PDF/A-1b (más común en VUCEM)
                '-dPDFACompatibilityPolicy=1',
                '-dNOPAUSE', '-dQUIET', '-dBATCH',
                '-dAutoFilterColorImages=false',  # Deshabilitar compresión automática
                '-dColorImageFilter=/DCTEncode',  # Usar JPEG para imágenes en color
                '-dColorImageResolution=300',
                '-dGrayImageResolution=300',
                '-dMonoImageResolution=300',
                '-sColorConversionStrategy=Gray',
                '-dProcessColorModel=/DeviceGray',
                '-dDownsampleColorImages=true',  # Forzar reescalado
                '-dDownsampleGrayImages=true',
                '-dDownsampleMonoImages=true',
                f'-sOutputFile={output_path}',
                input_path
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            app.logger.info(f"Ghostscript output: {result.stdout}")

            # Verificar DPI del PDF resultante
            dpi_values = check_dpi(output_path)
            if dpi_values:
                invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 290 or dpi > 310]
                if invalid_dpis:
                    flash(f"El PDF normalizado tiene DPI inválidos: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}. Inténtalo de nuevo o contacta al soporte.", "error")
                    os.remove(input_path)
                    os.remove(output_path)
                    return redirect(url_for('index'))
                else:
                    flash("PDF normalizado correctamente a 300 DPI en escala de grises.", "success")
            else:
                flash("No se detectaron imágenes en el PDF normalizado.", "warning")

            response = send_file(output_path, as_attachment=True)

            # Limpiar archivos temporales
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
                for f in os.listdir(folder):
                    try:
                        os.remove(os.path.join(folder, f))
                    except:
                        pass

            return response

        except subprocess.CalledProcessError as e:
            flash(f"Error al procesar el PDF: {e.stderr}", "error")
            app.logger.error(f"Ghostscript error: {e.stderr}")
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        try:
                            os.remove(os.path.join(folder, f))
                        except:
                            pass
            return redirect(url_for('index'))

    template_path = os.path.join(app.template_folder, 'index.html')
    if not os.path.exists(template_path):
        return "Error: Template index.html no encontrado.", 500

    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True)