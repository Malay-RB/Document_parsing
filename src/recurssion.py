"""
recursive_ocr.py
────────────────
Drop-in addition to your existing OCR framework.

Core idea
─────────
    extract(blocks)  ←── same function, called recursively
        for each block:
            if block is TEXT  → collect it
            if block is IMAGE → extract(blocks_inside_image)   ← recursion
                                 ↑ this is just calling ourselves again
                                   on the image's content

The image doesn't need a "special" handler.
It just becomes the next input to the same pipeline.
"""

import base64
import fitz          # PyMuPDF  — pip install pymupdf
import anthropic

client = anthropic.Anthropic()
MODEL  = "claude-sonnet-4-20250514"

# ─── The one recursive function ───────────────────────────────────────────────

def extract(source, depth: int = 0, max_depth: int = 3) -> str:
    """
    Extract all text from `source`, recursing into any images found.

    Parameters
    ----------
    source    : bytes  (image bytes)  ← called recursively on images
              | str    (pdf path)     ← called from outside on a PDF
    depth     : current recursion depth (managed automatically)
    max_depth : hard stop to prevent infinite recursion

    Returns
    -------
    All extracted text as a single string.
    """

    if depth > max_depth:
        return ""   # base case: too deep, stop

    # ── Dispatch based on what we received ────────────────────────────────────
    if isinstance(source, str):
        # It's a file path → extract page by page
        return _extract_pdf(source, depth, max_depth)
    else:
        # It's image bytes → send to Claude, get back blocks, recurse
        return _extract_image(source, depth, max_depth)


# ─── PDF path: iterate pages, collect text + images ──────────────────────────

def _extract_pdf(pdf_path: str, depth: int, max_depth: int) -> str:
    doc    = fitz.open(pdf_path)
    output = []

    for page_num, page in enumerate(doc):

        # 1. Native text layer
        native = page.get_text("text").strip()
        if native:
            output.append(native)

        # 2. Embedded images on this page → recurse
        for img_info in page.get_images(full=True):
            xref       = img_info[0]
            base_image = doc.extract_image(xref)
            img_bytes  = base_image["image"]
            w, h       = base_image["width"], base_image["height"]

            if w * h < 5_000:
                continue   # skip tiny decorative images

            # ── RECURSION: treat this image exactly like any other source ──
            img_text = extract(img_bytes, depth + 1, max_depth)
            if img_text:
                output.append(img_text)

    doc.close()
    return "\n\n".join(output)


# ─── Image bytes: ask Claude what's inside, recurse on any sub-images ─────────

def _extract_image(image_bytes: bytes, depth: int, max_depth: int) -> str:
    """
    Send image to Claude Vision.
    Claude returns text + signals if it sees sub-images worth extracting.
    We recurse on those too.
    """

    b64 = base64.b64encode(image_bytes).decode()

    response = client.messages.create(
        model      = MODEL,
        max_tokens = 2048,
        system     = (
            "You are an OCR engine embedded in a recursive extraction pipeline. "
            "Extract ALL visible text from the image. Rules:\n"
            "- Tables       → reproduce as Markdown table\n"
            "- Lists        → reproduce as numbered / bullet list\n"
            "- Running text → reproduce as plain paragraphs\n"
            "- Preserve headings, numbers, and hierarchy\n"
            "Output ONLY the extracted content. No commentary."
        ),
        messages   = [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": "image/png",
                        "data":       b64,
                    }
                },
                {
                    "type": "text",
                    "text": "Extract all text from this image."
                }
            ]
        }]
    )

    extracted = response.content[0].text.strip()

    # NOTE: at depth ≥ 1 we're already inside an image.
    # If Claude's output suggests there were further embedded visuals
    # (rare but possible in complex diagrams), you could detect and
    # recurse further here. For most textbooks, depth=1 is enough.

    return extracted


# ─── Convenience wrapper: single image file ───────────────────────────────────

def extract_image_file(path: str) -> str:
    """Extract text from a standalone image file (PNG / JPEG)."""
    with open(path, "rb") as f:
        return extract(f.read(), depth=0)


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python recursive_ocr.py book.pdf")
        print("  python recursive_ocr.py toc_image.png")
        sys.exit(1)

    path = sys.argv[1]

    if path.lower().endswith(".pdf"):
        result = extract(path)           # ← one call, handles everything
    else:
        result = extract_image_file(path)

    print(result)