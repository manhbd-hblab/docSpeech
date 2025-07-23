from flask import Flask, request, send_from_directory
import os
import asyncio
from tts.document_reader import DocumentReader
from tts.text_splitter import TextSplitter
from tts.tts_processor import TTSProcessor
from tts.audio_combiner import AudioCombiner
from tts.utils import setup_dirs
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_FOLDER = "./input"
OUTPUT_FOLDER = "./output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        f = request.files["file"]
        filename = secure_filename(f.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        f.save(filepath)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process(filepath, filename))

        output_file = os.path.splitext(filename)[0] + ".mp3"
        return f"""
        <p>✅ Xong! <a href="/download/{output_file}">Tải file</a></p>
        """

    return """
    <h2>Upload DOCX hoặc PDF</h2>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    """


async def process(path, filename):
    _, output_dir, temp_dir = setup_dirs()
    text = (
        DocumentReader.read_docx(path)
        if filename.endswith(".docx")
        else DocumentReader.read_pdf(path)
    )
    chunks = TextSplitter.smart_split(text)
    tts = TTSProcessor("vi-VN-HoaiMyNeural", temp_dir)
    results = await tts.process_batch(chunks, 4)
    success_files = [p for _, p, ok in results if ok]
    combiner = AudioCombiner()
    output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + ".mp3")
    combiner.combine(success_files, output_path)


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
