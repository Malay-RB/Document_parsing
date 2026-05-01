from abc import ABC, abstractmethod
from processing.logger import logger
from PIL import Image, ImageEnhance, ImageFilter

# ==========================================
# 1. BASE INTERFACE (The Contract)
# ==========================================
class BasePDFLoader(ABC):
    @abstractmethod
    def open(self, pdf_path: str):
        """Opens the PDF file and stores the state."""
        pass

    @abstractmethod
    def get_total_pages(self) -> int:
        """Returns the total number of pages."""
        pass

    @abstractmethod
    def load_page(self, page_number: int) -> Image.Image:
        """Renders a specific page to a PIL RGB Image."""
        pass

    @abstractmethod
    def close(self):
        """Releases the file pointer and system resources."""
        pass


# ==========================================
# 2. SPECIFIC WRAPPERS
# ==========================================
class PyPdfiumWrapper(BasePDFLoader):
    def __init__(self, scale=3.0, **kwargs):
        self.scale = scale
        self.pdf = None

    def open(self, pdf_path):
        # Deferred import for fast startup
        import pypdfium2 as pdfium 
        try:
            self.pdf = pdfium.PdfDocument(pdf_path)
            logger.info(f"Successfully opened PDF via PyPdfium: {pdf_path}")
        except Exception as e:
            logger.error(f"Failed to open PDF at {pdf_path}: {e}")
            raise

    def get_total_pages(self):
        return len(self.pdf) if self.pdf else 0

    def load_page(self, page_number):
        if self.pdf is None:
            raise RuntimeError("PDF not opened. Call open() first.")
            
        page = self.pdf[page_number - 1]
        bitmap = page.render(scale=self.scale)
        image = bitmap.to_pil()
        
        return image.convert("RGB")

    def close(self):
        if self.pdf is not None:
            self.pdf.close()
            self.pdf = None
            logger.info("PyPdfium document resources released.")


class IronPdfWrapper(BasePDFLoader):
    def __init__(self, dpi=150, **kwargs):
        self.dpi = dpi
        self.pdf = None

    def open(self, pdf_path):
        # Deferred import for fast startup
        from ironpdf import PdfDocument
        try:
            self.pdf = PdfDocument.FromFile(pdf_path)
            logger.info(f"Successfully opened PDF via IronPDF: {pdf_path}")
        except Exception as e:
            logger.error(f"Failed to open PDF at {pdf_path}: {e}")
            raise

    def get_total_pages(self):
        return self.pdf.PageCount if self.pdf else 0

    def load_page(self, page_number):
        if self.pdf is None:
            raise RuntimeError("PDF not opened. Call open() first.")

        logger.info(f"Rendering page {page_number} via IronPDF")
        single_page_pdf = self.pdf.CopyPage(page_number - 1)
        bmp_array = single_page_pdf.ToBitmap(0, DPI=self.dpi)
        bmp = bmp_array[0] 

        img = Image.frombytes(
            "RGBA",
            (bmp.Width, bmp.Height),
            bytes(bmp.GetBytes()),
            "raw",
            "BGRA"
        )

        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        img = img.convert("RGB")

        # Image enhancement pipeline
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=180, threshold=3))

        return img

    def close(self):
        if self.pdf is not None:
            self.pdf.Dispose()
            self.pdf = None
            logger.info("IronPDF document resources released.")


# ==========================================
# 3. THE FACTORY
# ==========================================
class PDFFactory:
    def __init__(self):
        # Map string keys to the class blueprints
        self._classes = {
            "pypdfium": PyPdfiumWrapper,
            "ironpdf": IronPdfWrapper
        }

    def create_loader(self, loader_name: str, **kwargs) -> BasePDFLoader:
        """
        Instantiates and returns a BRAND NEW loader.
        (We do not cache these like AI models because they hold active file states).
        """
        if loader_name not in self._classes:
            raise ValueError(f"❌ Unknown PDF loader requested: {loader_name}")

        # Notice how kwargs allows you to pass 'scale=3.0' or 'dpi=150' dynamically!
        return self._classes[loader_name](**kwargs)