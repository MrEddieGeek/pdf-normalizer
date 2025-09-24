import os
import subprocess
import glob
from flask import Flask, request, send_file, render_template, flash, redirect, url_for
from werkzeug.utils import secure_filename
import magic

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['OUTPUT_FOLDER'] = "outputs"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Límite de 16MB
app.secret_key = "super_secret_key"

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
        flash(f"Error al verificar DPI: {e}", "error")
        return []

def normalize_image_dpi(image_path, output_image_path, target_dpi=300):
    """Ajusta DPI de una imagen usando ImageMagick."""
    try:
        cmd = [
            'convert', image_path,
            '-units', 'PixelsPerInch',
            '-density', str(target_dpi),
            output_image_path
        ]
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        flash(f"Error al normalizar DPI de la imagen {image_path}: {e}", "error")
        raise

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
            invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 150 or dpi > 300]
            if invalid_dpis:
                flash(f"DPI inválidos detectados: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}", "warning")
            else:
                flash("Todos los DPI están dentro del rango permitido.", "info")

        # Extraer imágenes y ajustar DPI
        try:
            temp_image_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_images')
            os.makedirs(temp_image_dir, exist_ok=True)
            temp_image_prefix = os.path.join(temp_image_dir, 'img')

            # Intentar extraer imágenes (sin forzar JPEG)
            subprocess.run(['pdfimages', input_path, temp_image_prefix], check=True)

            # Buscar imágenes generadas (.jpg, .png, .ppm)
            image_files = glob.glob(f"{temp_image_dir}/img*[0-9][0-9][0-9].[jp][pn][mg]")
            if not image_files:
                # Si no hay imágenes, usar Ghostscript directamente
                flash("No se encontraron imágenes en el PDF. Normalizando con Ghostscript.", "warning")
                cmd = [
                    'gs', '-sDEVICE=pdfwrite',
                    '-dCompatibilityLevel=1.4',
                    '-dPDFSETTINGS=/prepress',
                    '-dNOPAUSE', '-dQUIET', '-dBATCH',
                    '-dColorImageResolution=300',
                    '-dGrayImageResolution=300',
                    '-dMonoImageResolution=300',
                    f'-sOutputFile={output_path}', input_path
                ]
                subprocess.run(cmd, check=True)
            else:
                # Normalizar DPI de cada imagen
                for img in image_files:
                    normalized_img = os.path.join(temp_image_dir, f"normalized_{os.path.basename(img)}")
                    normalize_image_dpi(img, normalized_img, target_dpi=300)

                # Recomponer PDF con img2pdf
                temp_pdf = os.path.join(app.config['OUTPUT_FOLDER'], f"temp_{filename}")
                normalized_images = glob.glob(f"{temp_image_dir}/normalized_img*[0-9][0-9][0-9].[jp][pn][mg]")
                if not normalized_images:
                    flash("No se generaron imágenes normalizadas.", "error")
                    raise ValueError("No images to process")
                subprocess.run(['img2pdf'] + normalized_images + ['-o', temp_pdf], check=True)

                # Optimizar con Ghostscript
                cmd = [
                    'gs', '-sDEVICE=pdfwrite',
                    '-dCompatibilityLevel=1.4',
                    '-dPDFSETTINGS=/prepress',
                    '-dNOPAUSE', '-dQUIET', '-dBATCH',
                    '-dColorImageResolution=300',
                    '-dGrayImageResolution=300',
                    '-dMonoImageResolution=300',
                    f'-sOutputFile={output_path}', temp_pdf
                ]
                subprocess.run(cmd, check=True)

            # Verificar DPI del PDF resultante
            dpi_values = check_dpi(output_path)
            if dpi_values:
                invalid_dpis = [(page, dpi) for page, dpi in dpi_values if dpi < 150 or dpi > 300]
                if invalid_dpis:
                    flash(f"El PDF normalizado aún tiene DPI inválidos: {', '.join([f'Página {p}: {d} DPI' for p, d in invalid_dpis])}", "error")
                else:
                    flash("PDF normalizado correctamente a 300 DPI.", "success")

            response = send_file(output_path, as_attachment=True)

            # Limpiar archivos temporales
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], temp_image_dir]:
                for f in os.listdir(folder):
                    try:
                        os.remove(os.path.join(folder, f))
                    except:
                        pass
            if os.path.exists(temp_image_dir):
                os.rmdir(temp_image_dir)

            return response

        except (subprocess.CalledProcessError, ValueError) as e:
            flash(f"Error al procesar el PDF: {e}", "error")
            for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], temp_image_dir]:
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        try:
                            os.remove(os.path.join(folder, f))
                        except:
                            pass
                    if folder == temp_image_dir:
                        os.rmdir(temp_image_dir)
            return redirect(url_for('index'))

    template_path = os.path.join(app.template_folder, 'index.html')
    if not os.path.exists(template_path):
        return "Error: Template index.html no encontrado.", 500

    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True)