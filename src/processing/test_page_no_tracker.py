from page_no_tracker import PageNumberTracker

# 🔥 Placeholder test data (replace later with JSON if needed)
data = [
    {"pdf_page": 1,  "printed_page": 1},
    {"pdf_page": 2,  "printed_page": 2},
    {"pdf_page": 3,  "printed_page": 3},
    {"pdf_page": 4,  "printed_page": 4},
    {"pdf_page": 5,  "printed_page": 5},
    {"pdf_page": 6,  "printed_page": 6},
    {"pdf_page": 7,  "printed_page": 200},
    {"pdf_page": 8,  "printed_page": 11},
    {"pdf_page": 9,  "printed_page": 12},
    {"pdf_page": 10, "printed_page": 13},
    {"pdf_page": 11, "printed_page": 14},
    {"pdf_page": 12, "printed_page": 15},
    {"pdf_page": 13, "printed_page": 16},
    {"pdf_page": 14, "printed_page": 17},
    {"pdf_page": 15, "printed_page": 18},
    {"pdf_page": 16, "printed_page": 12},
    {"pdf_page": 17, "printed_page": 18},
    {"pdf_page": 18, "printed_page": None},
    {"pdf_page": 19, "printed_page": 51},
    {"pdf_page": 20, "printed_page": 52},
    {"pdf_page": 21, "printed_page": 53},
    {"pdf_page": 22, "printed_page": 54},
    {"pdf_page": 23, "printed_page": 55},
    {"pdf_page": 24, "printed_page": 56},
    {"pdf_page": 25, "printed_page": 57},
    {"pdf_page": 26, "printed_page": 58},
    {"pdf_page": 27, "printed_page": 59},
    {"pdf_page": 28, "printed_page": 60},
    {"pdf_page": 29, "printed_page": None},
    {"pdf_page": 30, "printed_page": 19},
    {"pdf_page": 31, "printed_page": 20},
]

tracker = PageNumberTracker()

# Phase 1: process all pages
for block in data:
    tracker.process(block["pdf_page"], block.get("printed_page"))

# Phase 2: finalize
offset = tracker.finalize()

# Phase 3: apply
results = []
for block in data:
    pdf_page = block["pdf_page"]
    detected = block.get("printed_page")

    if offset is not None:
        resolved = pdf_page + offset
    else:
        resolved = detected if detected is not None else pdf_page

    results.append({
        "pdf_page": pdf_page,
        "detected": detected,
        "resolved": resolved
    })

for r in results:
    print(r)