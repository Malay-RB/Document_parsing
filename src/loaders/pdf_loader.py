import pypdfium2 as pdfium
from processing.logger import logger

class PDFLoader:

    def __init__(self, scale=3.0):
        self.scale = scale
        self.pdf = None

    def open(self, pdf_path):
        """Initializes the PdfDocument object."""
        try:
            self.pdf = pdfium.PdfDocument(pdf_path)
            logger.info(f"Successfully opened PDF: {pdf_path}")
        except Exception as e:
            logger.error(f"Failed to open PDF at {pdf_path}: {e}")
            raise

    def get_total_pages(self):
        if self.pdf is None:
            return 0
        return len(self.pdf)

    def load_page(self, page_number):
        """Renders a PDF page into a PIL Image (RGB)."""
        if self.pdf is None:
            raise RuntimeError("PDF not opened. Call open() first.")
            
        page = self.pdf[page_number - 1]
        bitmap = page.render(scale=self.scale)
        image = bitmap.to_pil()
        
        # Immediate conversion to RGB to support PIL.ImageOps (No RGBA errors)
        return image.convert("RGB")

    def close(self):
        """Explicitly closes the PDF document to release system resources."""
        if self.pdf is not None:
            self.pdf.close()
            self.pdf = None
            logger.info("PDF document resources released.")