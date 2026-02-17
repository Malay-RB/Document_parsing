from pdf2image import convert_from_path


class PDFLoader:

    def __init__(self, dpi=400):
        self.dpi = dpi


    def load(self, pdf_path):

        print(f"Loading PDF: {pdf_path}")
        print(f"DPI: {self.dpi}")

        pages = convert_from_path(
            pdf_path,
            dpi=self.dpi
        )

        print(f"Total pages loaded: {len(pages)}")

        return pages
