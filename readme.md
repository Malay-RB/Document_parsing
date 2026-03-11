# Document Parsing Pipeline

An intelligent, multi-stage PDF extraction pipeline designed to convert complex documents (like NCERT/CBSE textbooks) into structured JSON data. It utilizes AI models for layout detection, OCR, and semantic classification.

# Project Structure

Document_parsing/
├── src/
│   ├── main.py                # Pipeline Orchestrator
│   ├── config.py              # Environment & Project Configuration
│   ├── loaders/               # PDF (Pdfium) and Model Loaders
│   ├── modules/
│   │   ├── scout_sync.py      # Phase 1: TOC Discovery & Sync
│   │   ├── toc_extractor.py   # Phase 2: Hierarchy Building
│   │   └── extract.py         # Phase 3: Deep Block Extraction
│   ├── processing/
│   │   ├── optimize_layout.py    # layout detection utils - padding, margin, coordinates, etc.
│   │   ├── page_no_tracker.py    # page number tracker logic for missing page numbers
│   │   ├── page_strategy.py      # page number detection logic based on "Header" and "Footer"
│   │   ├── pipeline_utils.py     # main logic of pipeline - scout and sync and extraction logic
│   │   ├── structural_matcher.py # matching based on start page number and end page number in extracted doc and table of contents
│   │   ├── logger.py             # Unified Logging System
│   │   └── performance_track.py  # Telemetry Decorator
│   └── tests/                    # Pytest Suite (Scout, TOC, E2E)
├── input/                        # Source PDF Files
└── output/                       # Generated JSONs and Debug Visuals


# Installation

1. clone the repository:

    git clone https://github.com/Malay-RB/Document_parsing.git

2. Environment setup:

    cd Document_parsing
    poetry install

3. Dependencies:

    Ensure you have Poppler installed and added to your system path for pdf2image support.

# Usage

    cd src

1. Pipeline run:
    To process a PDF from the "input/" directory

    python main.py


2. Standalone module run:

    python -m modules.toc_extractor 
    #replace toc_extractor with a different module name

3. Testing and coverage:

    python -m pytest tests/ -v -s --cov=. --cov-report=term-missing

