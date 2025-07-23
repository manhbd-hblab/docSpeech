# document_reader.py
from docx import Document
import fitz  # PyMuPDF

class DocumentReader:
    @staticmethod
    def read_docx(file_path):
        doc = Document(file_path)
        return " ".join([p.text for p in doc.paragraphs])

    @staticmethod
    def read_pdf(file_path):
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))
            for block in blocks:
                text += block[4] + " "
            text += "\n"
        return text
