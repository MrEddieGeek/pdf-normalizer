import os
import subprocess
from flask import Flask, request, send_file, render_template

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            output_path = os.path.join(OUTPUT_FOLDER, "normalizado_" + file.filename)
            file.save(input_path)

            # Ejecutar Ghostscript para normalizar a 300 DPI
            cmd = [
                "gs", "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/prepress",
                "-dNOPAUSE", "-dQUIET", "-dBATCH",
                "-dColorImageResolution=300",
                "-dGrayImageResolution=300",
                "-dMonoImageResolution=300",
                f"-sOutputFile={output_path}", input_path
            ]
            subprocess.run(cmd, check=True)

            return send_file(output_path, as_attachment=True)

    return render_template("index.html")
