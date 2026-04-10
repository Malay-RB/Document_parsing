import re
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# ROMAN NUMERAL UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

_ROMAN_MAP = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100,  "C"), (90,  "XC"), (50,  "L"), (40,  "XL"),
    (10,   "X"), (9,   "IX"), (5,   "V"), (4,   "IV"), (1, "I"),
]

_ROMAN_RE = re.compile(
    r"^(M{0,4})(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)

def roman_to_int(s: str) -> Optional[int]:
    """Return integer value of a Roman numeral string, or None if invalid."""
    s = s.strip().upper()
    if not s or not _ROMAN_RE.match(s):
        return None
    val = 0
    i = 0
    roman_vals = {"I": 1, "V": 5, "X": 10, "L": 50,
                  "C": 100, "D": 500, "M": 1000}
    while i < len(s):
        if i + 1 < len(s) and roman_vals.get(s[i], 0) < roman_vals.get(s[i + 1], 0):
            val += roman_vals[s[i + 1]] - roman_vals[s[i]]
            i += 2
        else:
            val += roman_vals.get(s[i], 0)
            i += 1
    return val if val > 0 else None

# ─────────────────────────────────────────────────────────────────────────────
# WORD-NUMBER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}

def word_to_int(s: str) -> Optional[int]:
    return _WORD_NUMS.get(s.strip().lower())

# ─────────────────────────────────────────────────────────────────────────────
# COMPILED PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

# Indian:  "3." or "3 " at start
_Indian_ID = re.compile(r"^(\d+)\.?\s+")

# Subtopic: "3.1" or "3.1.2"
_SUBTOPIC_ID = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?\s+")

# Roman subtopic: "I.1" or "II.3" or "i.ii" at start
_ROMAN_SUBTOPIC_ID = re.compile(
    r"^([IVXLCDM]+)\.([IVXLCDM]+|\d+)\s+",
    re.IGNORECASE
)

# Unnumbered subtopic: "(a)" or "(i)" or "a." or "i." at start
_UNNUMBERED_SUBTOPIC_ID = re.compile(
    r"^(?:\(([a-z])\)|([a-z])\.)\s+",
    re.IGNORECASE
)

# Roman:   "III." or "III " or "iii " at start
_ROMAN_ID = re.compile(r"^([IVXLCDM]+)\.?\s+", re.IGNORECASE)

# Word-style chapter: "Chapter 1" / "Chapter1" (\\s* handles missing space)
_WORD_CH_ID = re.compile(
    # r"^(?:chapter|unit|section|part)\s*(\d+|[a-z]+)\s*(?:[\.\:\-–])?\s*",
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड)\s*(\d+|[a-z]+|\d+)\s*(?:[\.\:\-–])?\s*",
    re.IGNORECASE,
)

# Page number / range at end of line
_PAGE_RANGE = re.compile(
    r"(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*[\w\.\,\%\*]*\s*$",
    re.IGNORECASE,
)
_PAGE_SINGLE = re.compile(r'(?<!\d)(\d{1,4})\s*$')

# Unit/theme header line (standalone, no chapter number)
# FIX: added "theme" to keyword list
_UNIT_HEADER = re.compile(
    # r"^(?:unit|section|part|theme)\s+(.+?)\s*[:\-–—]?\s*(.+)?$",
    r"^(?:unit|section|part|theme|इकाई|भाग|खंड|विषय)\s+(.+?)\s*[:\-–—]?\s*(.+)?$",

    re.IGNORECASE,
)

# "THEME A — India and the World…" style — letter ID + dash + name
_THEME_HEADER = re.compile(
    # r"^(?:theme)\s+([A-Za-z])\s*[-–—]\s*(.+)$",
    r"^(?:theme|विषय)\s+([A-Za-z\u0900-\u097F])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)

# Standalone chapter label with no name after it ("Chapter 1", "Chapter1")
_STANDALONE_CH = re.compile(
    # r"^(?:chapter|unit|section|part)\s*(\d+|[IVXLCDM]+|[a-z]+)\s*$",
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड)\s*(\d+|[IVXLCDM]+|[a-z]+)\s*$",
    re.IGNORECASE,
)

# Table-style TOC row patterns
_TABLE_ROW_FULL = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
_TABLE_ROW_CHAPTER_ONLY = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
_TABLE_ROW_UNIT_ONLY = re.compile(
    r'^(\d+)\.\s+([A-Za-z][^\d]+?)\s*$'
)

# FIX (Bug 3): back-matter keyword guard — these lines must never become subtopics
_BACKMATTER_RE = re.compile(
    r"^(?:glossary|answers?|index|foreword|appendix|images?\s+and|bibliography|"
    r"acknowledgements?|about\s+the|method\s+of|note\s+to|letter\s+to|"
    r"your\s+journey|preface|introduction|"
    r"शब्दावली|उत्तर|अनुक्रमणिका|प्रस्तावना|परिशिष्ट|ग्रंथसूची|"
    r"आमुख|भूमिका|टिप्पणी|पत्र|"
    r"अभ्यास|प्रश्नावली|पुनरावृत्ति|सारांश|मानचित्र|" 
    r"परियोजना|क्रियाकलाप|विषय-सूची)",
    re.IGNORECASE | re.UNICODE,
)

# Subject/section header in table-style TOCs — standalone ALL-CAPS line with
# no page number and no chapter-ID prefix.
# e.g. "HISTORY", "CIVICS", "SOCIAL SCIENCE", "GEOGRAPHY AND ENVIRONMENT"
# Rules: all tokens are alpha-only (no digits), 1–5 words, total length < 60.
_SUBJECT_HEADER_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Z\s\/\-&]{1,58}[A-Z]"           # English ALL-CAPS (unchanged)
    r"|"
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D]"  # Devanagari: at least 1 char
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D\s\/\-]*"  # followed by 0+ more
    r")$",
    re.UNICODE
)   # all-caps, 2+ chars, no digits


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_page_range(text: str):
    """Return (start_page, end_page, text_before_page) from a line."""
    m = re.search(r'(\d+)\s*(?:-|–|—|to)\s*(\d+)(?!.*\d+\s*(?:-|–|—|to)\s*\d+)', text)
    if m:
        return int(m.group(1)), int(m.group(2)), text[:m.start()].strip()
    m = re.search(r'(?<!\d)(\d{1,4})\s*$', text)
    if m:
        before = text[:m.start()].strip()
        if before:
            return int(m.group(1)), None, before
    return None, None, text.strip()


def _strip_trailing_junk(text: str) -> str:
    """Remove leader dots, dashes, underscores and trailing punctuation."""
    text = re.sub(r'[.\-_]{2,}', ' ', text)
    text = re.sub(r'[^\w\s\(\)\-\&\/]', '', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _safe_sanitize(text: str) -> str:
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'[^\w\s\-\&\(\)\/]', '', text, flags=re.UNICODE)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags like <b>, </b>, <i>, <math>…</math> etc."""
    return re.sub(r'<[^>]+>', '', text).strip()

# ─────────────────────────────────────────────────────────────────────────────
# TABLE-STYLE TOC PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_table_row(cleaned: str):
    m = _TABLE_ROW_FULL.match(cleaned)
    if m:
        unit_id   = int(m.group(1))
        unit_name = _safe_sanitize(m.group(2))
        ch_id     = int(m.group(3))
        ch_name   = _safe_sanitize(m.group(4))
        start_p, end_p, _ = _extract_page_range(m.group(5))
        return dict(unit_id=unit_id, unit_name=unit_name,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    m = _TABLE_ROW_CHAPTER_ONLY.match(cleaned)
    if m:
        ch_id   = int(m.group(1))
        ch_name = _safe_sanitize(m.group(2))
        start_p, end_p, _ = _extract_page_range(m.group(3))
        return dict(unit_id=None, unit_name=None,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    return None


_HINDI_KNOWN_SUBJECTS = {
    "इतिहास", "भूगोल", "नागरिकशास्त्र", "अर्थशास्त्र",
    "समाजिक विज्ञान", "सामाजिक विज्ञान", "राजनीति विज्ञान",
    "विज्ञान", "गणित", "हिंदी", "संस्कृत", "पर्यावरण अध्ययन",
    "राजनीतिशास्त्र", "समकालीन भारत", "लोकतांत्रिक राजनीति",
}
def _is_subject_header(text: str) -> bool:
    """
    Return True if a line is a standalone subject/section header in a
    table-style TOC, e.g. "HISTORY", "CIVICS", "SOCIAL SCIENCE".

    Criteria:
      - Matches _SUBJECT_HEADER_RE (all-caps, no digits, 2–60 chars)
      - No page number embedded
      - Word count 1–6
      - Not a known back-matter keyword (those are handled separately)
    """
    text = text.strip()

    if text in _HINDI_KNOWN_SUBJECTS:
        return True
    if not _SUBJECT_HEADER_RE.match(text):
        return False
    if re.search(r'\d', text):
        return False                      # digits → not a pure header
    sp, _, _ = _extract_page_range(text)
    if sp is not None:
        return False                      # has a page number → data row
    if len(text.split()) > 6:
        return False
    # For Devanagari text, skip the isupper() check (no case concept)
    is_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if not is_devanagari and not text.isupper():
        return False 
    return True


def _parse_table_toc(all_lines: list) -> list:
    """
    Parser for table-layout TOCs where chapters are listed as numbered rows,
    optionally preceded by standalone subject/section headers.

    Improvements vs. original:
      • Detects standalone ALL-CAPS subject headers ("HISTORY", "CIVICS")
        and stores them as active_unit_name, so every chapter row beneath
        them gets the correct unit context.
      • Generates globally-unique chapter IDs by prefixing the unit counter
        when chapter numbers restart under a new subject (e.g. Civics Ch 1
        becomes chapter_id=11 if History had 10 chapters, or stores
        subject_chapter_id for the original number).
      • Carries active unit context forward across chapter-only rows
        (unchanged behaviour for single-subject table TOCs).
    """
    structured_data   = []
    active_unit_id    = None       # increments each time a new subject header is seen
    active_unit_name  = None
    unit_counter      = 0          # counts subject sections seen so far
    global_ch_offset  = 0         # added to local chapter numbers for global uniqueness

    for raw_line in all_lines:
        cleaned = raw_line.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)      # strip HTML
        cleaned = re.sub(r'\.{2,}', ' ', cleaned)      # strip leader dots
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        if not cleaned or len(cleaned) < 2:
            continue
        
        # ── Subject header detection ─────────────────────────────────────────
        # Must run BEFORE _parse_table_row so headers aren't silently skipped.
        if _is_subject_header(cleaned):
            unit_counter     += 1
            active_unit_id    = unit_counter
            active_unit_name = cleaned if re.search(r'[\u0900-\u097F]', cleaned) else cleaned.title() # "HISTORY" → "History"
            # Track global offset using the last entry's global_chapter_id
            # so the next subject's chapter numbers stay globally sequential.
            if structured_data:
                global_ch_offset = structured_data[-1]["global_chapter_id"]
            print(f"      📦 Subject: {active_unit_id} – {active_unit_name}")
            continue

        # ── Try to parse as a data row ───────────────────────────────────────
        if len(cleaned) < 4:
            continue

        row = _parse_table_row(cleaned)
        if row is None:
            continue

        # Attach current subject context
        if row["unit_id"] is not None:
            # Full row already carries unit info (rare in this TOC style)
            pass
        else:
            row["unit_id"]   = active_unit_id
            row["unit_name"] = active_unit_name

        # chapter_id  = subject-local number (1, 2, 3… within each subject)
        #               This is what goes into metadata and is shown to users.
        # global_chapter_id = sequential across the whole book (never resets)
        #               Use this only for internal DB keys / page-range lookups.
        local_ch_id = row["chapter_id"]                        # already set by _parse_table_row
        row["chapter_id"]        = local_ch_id                 # keep as-is: subject-local
        row["global_chapter_id"] = global_ch_offset + local_ch_id  # sequential across book

        is_sub = row.get("is_subtopic", False)
        print(f"      {'  ↳' if is_sub else '⭐'} "
              f"Ch {row['chapter_id']} (global #{row['global_chapter_id']}) – {row['chapter_name']} "
              f"[Unit: {row['unit_name']}] [Page: {row['start_page']}–{row['end_page']}]")

        structured_data.append(row)

    return structured_data

# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _merge_floating_page_numbers(lines: list) -> list:
    """
    Two jobs in one pass:

    Job 1 — attach orphaned bare page numbers/ranges to the PREVIOUS line.
      e.g. ["Locating Places on the Earth", "7"]
           → ["Locating Places on the Earth 7"]
      FIX: appends to ANY non-empty previous line (old code only matched
      digit-start lines, which excluded chapter-name lines).

    Job 2 — attach orphaned bare chapter-ID tokens ("2.", "10.") to the
      NEXT line (the chapter name), so they don't corrupt the previous entry.
      e.g. ["1. Name 7", "2.", "Oceans and Continents", "27"]
           → ["1. Name 7", "2. Oceans and Continents", "27"]
      This happens when OCR splits "2.  Oceans" into two separate bounding
      boxes placed on different lines.
    """
    # ── Pass 1: merge orphan "N." forward onto the next line ────────────────
    pre = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        # Bare chapter-ID token: just "2." or "10." with nothing else
        if re.fullmatch(r'\d{1,3}\.', stripped) and i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            # Only merge forward if the next line is NOT already a complete
            # chapter line (i.e. it has no leading digit prefix itself)
            if not re.match(r'^\d+\.?\s', next_stripped):
                merged_fwd = stripped + " " + next_stripped
                pre.append(merged_fwd)
                print(f"      🔗 Merged orphan ID forward: [{stripped}] + [{next_stripped}]")
                i += 2
                continue
        pre.append(lines[i])
        i += 1

    # ── Pass 2: merge orphan bare numbers/ranges backward onto previous line ─
    merged = []
    for line in pre:
        stripped = line.strip()
        is_num = re.fullmatch(
            r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE
        )
        # Append to ANY previous non-empty line, not just digit-start lines
        if is_num and merged and merged[-1].strip():
            merged[-1] = merged[-1].strip() + " " + stripped
        else:
            merged.append(line)
    return merged


def _is_continuation_line(text: str) -> bool:
    """
    Return True if a line looks like the wrapped tail of a chapter name,
    e.g. "in Rural Areas" or "WITH WHOLE NUMBER".

    Criteria:
      - does NOT start with a chapter keyword
      - does NOT start with a digit or "N." (Indian-style ID or orphan number)
      - does NOT look like a bare chapter-number token ("2.", "10.")
      - does NOT contain a page number of its own
      - is relatively short (<= 80 chars) — long lines are likely new entries
      - is NOT all-caps short token (watermark / stamp like "NCERT")
    """
    if _WORD_CH_ID.match(text):
        return False
    if _STANDALONE_CH.match(text):
        return False
    if _Indian_ID.match(text):
        return False
    if _THEME_HEADER.match(text):
        return False
    if _BACKMATTER_RE.match(text):
        return False
    # Reject bare orphan chapter-number tokens: "2." / "10." / "2" alone
    # These are Indian-style ID fragments split off by OCR — not name tails.
    if re.fullmatch(r'\d{1,3}\.?', text.strip()):
        return False
    sp, _, _ = _extract_page_range(text)
    if sp is not None:
        return False          # has its own page number → new entry
    if len(text) > 80:
        return False          # too long to be a mere continuation
    # Reject ALL-CAPS short tokens — likely watermarks/stamps ("NCERT", "DRAFT")
    if text.isupper() and len(text.split()) <= 3:
        return False
    return True


def _merge_two_line_chapters(lines: list) -> list:
    """
    Merges multi-line TOC entries into single lines.

    Handles three cases:
      1. Standalone label ("Chapter 1") followed by name + optional page line.
      2. Chapter name that wraps onto the next line ("in Rural Areas" after
         "11. Grassroots Democracy — Part 2: Local Government  163").
         FIX (Bug 1b): these continuation lines are now APPENDED to the
         previous merged line instead of being skipped silently — so the full
         chapter name is preserved.
      3. "WITH WHOLE NUMBER" style orphan after a chapter that already has its
         page number — silently dropped (it duplicates info already merged).
    """
    merged = []
    i = 0
    while i < len(lines):
        current_raw   = lines[i].strip()
        current_clean = _strip_html(current_raw)

        # ── Case 1: standalone label only (e.g. "Chapter 1" with no name) ──
        if _STANDALONE_CH.match(current_clean) and i + 1 < len(lines):
            next_raw   = lines[i + 1].strip()
            next_clean = _strip_html(next_raw)
            if not _STANDALONE_CH.match(next_clean):
                # Also grab next-next if it's just a page number
                if (i + 2 < len(lines) and
                    re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?',
                                 _strip_html(lines[i + 2].strip()), re.IGNORECASE)):
                    page_line   = _strip_html(lines[i + 2].strip())
                    merged_line = current_clean + " " + next_clean + " " + page_line
                    merged.append(merged_line)
                    print(f"      🔗 Merged three-line chapter: [{current_clean}] + "
                          f"[{next_clean}] + [{page_line}]")
                    i += 3
                    continue
                merged_line = current_clean + " " + next_clean
                merged.append(merged_line)
                print(f"      🔗 Merged two-line chapter: [{current_clean}] + [{next_clean}]")
                i += 2
                continue

        # ── Case 2 & 3: possible continuation / orphan line ─────────────────
        if merged and _is_continuation_line(current_clean):
            prev_sp, prev_ep, _ = _extract_page_range(merged[-1])

            if prev_sp is None:
                # Previous line has NO page yet → append this fragment to it
                # e.g. "11. Grassroots Democracy Part 2 Local Government" + "in Rural Areas 163"
                merged[-1] = merged[-1].strip() + " " + current_clean
                print(f"      🔗 Appended continuation: [{current_clean}] → merged into previous")
            else:
                # Previous line already has a page (chapter is "done") →
                # this is a wrapped subtitle duplicate, drop it silently
                print(f"      ⏭  Skipped orphan continuation: [{current_clean}]")
            i += 1
            continue

        merged.append(current_raw)
        i += 1
    return merged


def _detect_id_style(lines: list) -> str:
    """
    Vote on the predominant chapter-ID style.
    Returns: 'Indian' | 'roman' | 'word'
    """
    votes = {"Indian": 0, "roman": 0, "word": 0}
    for line in lines:
        line = _strip_html(line.strip())
        # Skip bare page numbers — they must not influence the style vote
        if re.fullmatch(r'\d{1,4}(\s*[-–—]\s*\d{1,4})?', line):
            continue
        if _SUBTOPIC_ID.match(line) or _Indian_ID.match(line):
            votes["Indian"] += 1
        elif _WORD_CH_ID.match(line):
            votes["word"] += 1
        elif _ROMAN_ID.match(line):
            tok = line.split()[0].rstrip(".")
            if roman_to_int(tok) is not None:
                votes["roman"] += 1
    # Indian wins ties (most common in Indian textbooks)
    return max(votes, key=lambda k: (votes[k], k == "Indian"))


def _to_int(token: str, style: str) -> Optional[int]:
    token = token.strip()
    if style == "Indian":
        return int(token) if token.isdigit() else None
    if style == "roman":
        return roman_to_int(token)
    if style == "word":
        v = word_to_int(token)
        if v is not None:
            return v
        return int(token) if token.isdigit() else None
    return None


def _has_chapter_after_unit(text: str) -> bool:
    tokens = text.split()
    if len(tokens) > 3:
        for tok in tokens[2:]:
            if re.match(r'^\d+$', tok):
                return True
    return False


def _parse_line(
    cleaned: str,
    id_style: str,
    last_chapter_int: int,
    max_jump: int,
) -> Optional[tuple]:
    """
    Try to parse a single cleaned line into
    (ch_int, ch_name, start_p, end_p, is_subtopic, raw_subtopic_id).
    Returns None if the line does not match any known pattern.
    """
    # Guard: reject bare numbers / page ranges — never a chapter entry
    if re.fullmatch(r'\d{1,4}(\s*[-–—to]\s*\d{1,4})?', cleaned.strip()):
        return None

    # ── 0. Roman subtopic: "I.1" or "II.3" ──────────────────────────────────
    rom_sub_m = _ROMAN_SUBTOPIC_ID.match(cleaned)
    if rom_sub_m:
        parent_raw = rom_sub_m.group(1)
        parent_id  = roman_to_int(parent_raw) or 0
        sub_id_str = rom_sub_m.group(1) + "." + rom_sub_m.group(2)
        rest = cleaned[rom_sub_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            return None
        return (parent_id, name, start_p, end_p, True, sub_id_str)

    # ── 0b. Unnumbered subtopic: "(a)" or "a." ───────────────────────────────
    unnum_m = _UNNUMBERED_SUBTOPIC_ID.match(cleaned) if id_style != "roman" else None
    if unnum_m:
        label   = (unnum_m.group(1) or unnum_m.group(2)).lower()
        sub_int = ord(label) - ord('a') + 1
        rest = cleaned[unnum_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            return None
        return (sub_int, name, start_p, end_p, True, label)

    # ── 1. Subtopic pattern:  "1.1" or "1.1.2" ──────────────────────────────
    sub_m = _SUBTOPIC_ID.match(cleaned)
    if sub_m:
        parent_id  = int(sub_m.group(1))
        sub_id_str = sub_m.group(1) + "." + sub_m.group(2)
        if sub_m.group(3):
            sub_id_str += "." + sub_m.group(3)
        rest = cleaned[sub_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (parent_id, name, start_p, end_p, True, sub_id_str)

    # ── 2. Word chapter: "Chapter 1  …" or "Chapter1  …" ────────────────────
    # Tried BEFORE Indian/Roman so lines starting with "Chapter" are never
    # mis-parsed as Indian-style even if id_style was wrongly detected.
    word_m = _WORD_CH_ID.match(cleaned)
    if word_m:
        num_tok = word_m.group(1)
        ch_int  = int(num_tok) if num_tok.isdigit() else word_to_int(num_tok)
        if ch_int is not None and _jump_ok(ch_int, last_chapter_int, max_jump):
            rest = cleaned[word_m.end():]
            start_p, end_p, name_raw = _extract_page_range(rest)
            name = _safe_sanitize(_strip_trailing_junk(name_raw))
            if name:
                return (ch_int, name, start_p, end_p, False, None)

    # ── 3. Indian chapter: "3 Chapter Name  45" ──────────────────────────────
    if id_style == "Indian":
        m = _Indian_ID.match(cleaned)
        if not m:
            return None
        ch_int = int(m.group(1))
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    # ── 4. Roman numeral chapter: "III  Cell Biology  45" ────────────────────
    if id_style == "roman":
        m = _ROMAN_ID.match(cleaned)
        if not m:
            return None
        tok    = m.group(1)
        ch_int = roman_to_int(tok)
        if ch_int is None:
            return None
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    # id_style == "word" was already tried above (word_m block)
    return None


def _jump_ok(ch_int: int, last: int, max_jump: int) -> bool:
    """Return True if the chapter ID is a plausible successor."""
    if ch_int < 1:
        return False
    if last == 0:
        return True
    return 0 < ch_int - last <= max_jump or ch_int == last

# ─────────────────────────────────────────────────────────────────────────────
# CORE ROBUST TRANSFORM LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def robust_transform_logic(self, raw_pages: list) -> list:
    """
    Replacement for TOCProcessorAPI.transform_logic that handles all TOC patterns.

    Fixes applied in this version:
      • _merge_floating_page_numbers attaches orphaned numbers to ANY previous
        line, not just digit-start lines (fixes Ch 1 page=None).
      • _merge_two_line_chapters APPENDS continuation lines (e.g. "in Rural
        Areas") to the previous entry instead of dropping them, preserving the
        full chapter name for Ch 11 / Ch 12 style entries.
      • _THEME_HEADER and _UNIT_HEADER now recognise "Theme A — …" patterns,
        populating active_unit_id / active_unit_name for theme-grouped TOCs.
      • _BACKMATTER_RE prevents Glossary, Answers, Images etc. from being
        classified as subtopics of the last chapter.
      • _detect_id_style skips bare page-number tokens before voting.
      • _parse_line guards against bare numbers at the top before any match.
    """
    print("🧠 [TOC_TRANSFORM] Converting lines to structured JSON (ROBUST MODE)…")

    # ── collect all lines across pages ──────────────────────────────────────
    all_lines = []
    for page in raw_pages:
        lines  = page.get("lines", [])
        merged = _merge_floating_page_numbers(lines)
        merged = _merge_two_line_chapters(merged)
        all_lines.extend(merged)

    # ── detect dominant ID style ─────────────────────────────────────────────
    id_style = _detect_id_style(all_lines)
    print(f"      📐 Detected chapter-ID style: {id_style.upper()}")

    # ── detect if this is a TABLE-style TOC ─────────────────────────────────
    table_hits = sum(
        1 for l in all_lines
        if _TABLE_ROW_FULL.match(l.strip()) or _TABLE_ROW_CHAPTER_ONLY.match(l.strip())
    )
    if table_hits >= 3:
        print(f"      📊 Table-style TOC detected ({table_hits} matching rows) "
              f"— switching to table parser")
        return _parse_table_toc(all_lines)

    # ── parse lines ─────────────────────────────────────────────────────────
    structured_data   = []
    active_unit_id    = None
    active_unit_name  = None
    last_chapter_int  = 0
    subtopic_counters = {}

    for line in all_lines:
        if self.is_header_or_footer(line):
            continue
        cleaned = self.clean_text(line)
        if not cleaned or len(cleaned) < self.min_line_length:
            continue

        # ── Theme header: "Theme A — India and the World…" ──────────────────
        theme_m = _THEME_HEADER.match(cleaned)
        if theme_m:
            active_unit_id   = theme_m.group(1).upper()   # "A", "B", "C"…
            active_unit_name = _safe_sanitize(theme_m.group(2))
            print(f"      📦 Theme: {active_unit_id} – {active_unit_name}")
            continue

        # ── Unit-header-only lines ───────────────────────────────────────────
        unit_m = _UNIT_HEADER.match(cleaned)
        if unit_m and not _has_chapter_after_unit(cleaned):
            uid_raw = unit_m.group(1)
            uid_int = (_to_int(uid_raw, "Indian") or
                       _to_int(uid_raw, "roman") or
                       _to_int(uid_raw, "word"))
            active_unit_id   = uid_int
            active_unit_name = _safe_sanitize(unit_m.group(2) or "")
            print(f"      📦 Unit: {active_unit_id} – {active_unit_name}")
            continue

        # ── Attempt to parse as a structured entry ───────────────────────────
        entry = _parse_line(cleaned, id_style, last_chapter_int, self.max_chapter_jump)

        # ── Fallback: horizontal subtopics (comma-separated on one line) ─────
        if entry is None and last_chapter_int > 0 and ',' in cleaned:
            parts = [p.strip() for p in cleaned.split(',')]
            if len(parts) >= 3:
                print(f"      📋 Horizontal subtopics detected for Ch {last_chapter_int}")
                for part in parts:
                    part = part.strip().rstrip('.')
                    if not part:
                        continue
                    start_p, end_p, name_raw = _extract_page_range(part)
                    name = _safe_sanitize(_strip_trailing_junk(name_raw))
                    if not name or len(name) < 3:
                        continue
                    if re.match(r'^[A-Z][A-Z\s\.]+$', name):
                        continue
                    subtopic_counters[last_chapter_int] = (
                        subtopic_counters.get(last_chapter_int, 0) + 1
                    )
                    sub_id = f"{last_chapter_int}.{subtopic_counters[last_chapter_int]}"
                    entry_dict = {
                        "unit_id":       active_unit_id,
                        "unit_name":     active_unit_name,
                        "chapter_id":    last_chapter_int,
                        "chapter_name":  structured_data[-1]["chapter_name"] if structured_data else None,
                        "start_page":    start_p,
                        "end_page":      end_p,
                        "is_subtopic":   True,
                        "subtopic_id":   sub_id,
                        "subtopic_name": name,
                    }
                    print(f"        ↳ Subtopic {sub_id} – {name} [Page: {start_p}]")
                    structured_data.append(entry_dict)
            continue

        # ── Fallback: unnumbered subtopic / back-matter detection ─────────────
        if entry is None and last_chapter_int > 0:
            # FIX (Bug 3): back-matter lines must never become subtopics.
            # Store them as appendix entries with chapter_id=None instead.
            if _BACKMATTER_RE.match(cleaned):
                sp, ep, _ = _extract_page_range(cleaned)
                bm_name = _safe_sanitize(_strip_trailing_junk(
                    re.sub(r'\d+', '', cleaned).strip()
                )) or cleaned.split()[0].capitalize()
                entry_dict = {
                    "unit_id":      None,
                    "unit_name":    None,
                    "chapter_id":   None,
                    "chapter_name": _safe_sanitize(cleaned[:cleaned.rfind(str(sp))].strip()) if sp else _safe_sanitize(cleaned),
                    "start_page":   sp,
                    "end_page":     ep,
                    "is_appendix":  True,
                }
                print(f"      📎 Back-matter: {entry_dict['chapter_name']} [Page: {sp}]")
                structured_data.append(entry_dict)
                continue

            # Regular unnumbered subtopic
            start_p, end_p, name_raw = _extract_page_range(cleaned)
            name = _safe_sanitize(_strip_trailing_junk(name_raw))
            if start_p is not None and name and len(name) > 3:
                if not name.isupper() and not re.match(r'^[A-Z][A-Z\s\.]+$', name):
                    subtopic_counters[last_chapter_int] = (
                        subtopic_counters.get(last_chapter_int, 0) + 1
                    )
                    sub_id = f"{last_chapter_int}.{subtopic_counters[last_chapter_int]}"
                    entry_dict = {
                        "unit_id":       active_unit_id,
                        "unit_name":     active_unit_name,
                        "chapter_id":    last_chapter_int,
                        "chapter_name":  structured_data[-1]["chapter_name"] if structured_data else None,
                        "start_page":    start_p,
                        "end_page":      end_p,
                        "is_subtopic":   True,
                        "subtopic_id":   sub_id,
                        "subtopic_name": name,
                    }
                    print(f"        ↳ Subtopic {sub_id} – {name} [Page: {start_p}]")
                    structured_data.append(entry_dict)
            continue

        if entry is None:
            continue

        ch_int, ch_name, start_p, end_p, is_subtopic, raw_subtopic_id = entry

        if is_subtopic:
            entry_dict = {
                "unit_id":      active_unit_id,
                "unit_name":    active_unit_name,
                "chapter_id":   ch_int,
                "chapter_name": structured_data[-1]["chapter_name"] if structured_data else None,
                "start_page":   start_p,
                "end_page":     end_p,
            }
        else:
            entry_dict = {
                "unit_id":      active_unit_id,
                "unit_name":    active_unit_name,
                "chapter_id":   ch_int,
                "chapter_name": ch_name,
                "start_page":   start_p,
                "end_page":     end_p,
            }

        if is_subtopic:
            if raw_subtopic_id:
                subtopic_id = raw_subtopic_id
            else:
                subtopic_counters[ch_int] = subtopic_counters.get(ch_int, 0) + 1
                subtopic_id = f"{ch_int}.{subtopic_counters[ch_int]}"
            entry_dict["is_subtopic"]   = True
            entry_dict["subtopic_id"]   = subtopic_id
            entry_dict["subtopic_name"] = ch_name

        display_id = entry_dict.get("subtopic_id", ch_int) if is_subtopic else ch_int
        print(f"      {'  ↳' if is_subtopic else '⭐'} "
              f"{'Subtopic' if is_subtopic else 'Ch'} {display_id} – {ch_name} "
              f"[Page: {start_p}]")

        structured_data.append(entry_dict)

        if not is_subtopic:
            last_chapter_int = ch_int

    # ── back-fill end pages ──────────────────────────────────────────────────
    for i in range(len(structured_data) - 1):
        if structured_data[i]["end_page"] is None:
            current_is_subtopic = structured_data[i].get("is_subtopic", False)
            if current_is_subtopic:
                next_start = structured_data[i + 1]["start_page"]
                if next_start:
                    structured_data[i]["end_page"] = next_start - 1
            else:
                for j in range(i + 1, len(structured_data)):
                    if not structured_data[j].get("is_subtopic", False):
                        next_ch_start = structured_data[j]["start_page"]
                        if next_ch_start:
                            structured_data[i]["end_page"] = next_ch_start - 1
                        break

    return structured_data

# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API  — patch function & subclass factory
# ─────────────────────────────────────────────────────────────────────────────

def patch_toc_processor(api_instance):
    import types
    api_instance.transform_logic = types.MethodType(robust_transform_logic, api_instance)
    print("✅ [toc_patterns] Robust transform_logic patched successfully.")


class RobustTOCProcessor:

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __new__(cls, *args, **kwargs):
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        try:
            from modules.toc_extractor import TOCProcessorAPI
        except ImportError:
            import importlib.util, pathlib
            spec = importlib.util.spec_from_file_location(
                "toc_extractor",
                pathlib.Path(__file__).parent / "toc_extractor.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            TOCProcessorAPI = mod.TOCProcessorAPI

        instance = TOCProcessorAPI.__new__(TOCProcessorAPI)
        TOCProcessorAPI.__init__(instance, *args, **kwargs)
        patch_toc_processor(instance)
        instance.__class__ = type(
            "RobustTOCProcessor",
            (TOCProcessorAPI,),
            {"transform_logic": robust_transform_logic}
        )
        return instance