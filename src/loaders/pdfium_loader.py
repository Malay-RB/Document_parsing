# loaders/pdf_loader.py

import pypdfium2 as pdfium

class PDFLoader:

    def __init__(self, scale=3.0):
        self.scale = scale
        self.pdf = None

    def open(self, pdf_path):
        self.pdf = pdfium.PdfDocument(pdf_path)

    def get_total_pages(self):
        return len(self.pdf)

    def load_page(self, page_number):
        page = self.pdf[page_number - 1]

        bitmap = page.render(scale=self.scale)
        image = bitmap.to_pil()

        return image.convert("RGB")
