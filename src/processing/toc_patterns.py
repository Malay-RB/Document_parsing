import re
from typing import Optional

# ── CHANGE 1/4: import coord classifier ──────────────────────────────────────
# Only addition at the top of the file. Everything else is unchanged.
try:
    from processing.coord_classifier import build_level_fn
    _COORD_AVAILABLE = True
except ImportError:
    _COORD_AVAILABLE = False
    def build_level_fn(lines):
        return lambda x: None, 0
# ─────────────────────────────────────────────────────────────────────────────

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
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड)\s*[-–]?\s*(\d+|[a-z]+|\d+)\s*(?:[\.\:\-–])?\s*",
    re.IGNORECASE,
)

# Page number / range at end of line
_PAGE_RANGE = re.compile(
    r"(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*[\w\.\,\%\*]*\s*$",
    re.IGNORECASE,
)
_PAGE_SINGLE = re.compile(r'(?<!\d)(\d{1,4})\s*$')

# Unit/theme header line (standalone, no chapter number)
_UNIT_HEADER = re.compile(
    r"^(?:unit|section|part|theme|इकाई|भाग|खंड|विषय)\s+(.+?)\s*[:\-–—]?\s*(.+)?$",
    re.IGNORECASE,
)

# "THEME A — India and the World…" style — letter ID + dash + name
_THEME_HEADER = re.compile(
    r"^(?:theme|विषय)\s+([A-Za-z\u0900-\u097F])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)

# Standalone chapter label with no name after it ("Chapter 1", "Chapter1")
_STANDALONE_CH = re.compile(
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड|विभाग)\s*[-–]?\s*(\d+|[IVXLCDM]+|[a-z]+)\s*$",
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
    r"your\s+journey|preface|introduction|Learning Material Sheets|"
    r"शब्दावली|उत्तर|अनुक्रमणिका|प्रस्तावना|परिशिष्ट|ग्रंथसूची|"
    r"आमुख|भूमिका|टिप्पणी|पत्र|"
    r"अभ्यास|प्रश्नावली|पुनरावृत्ति|सारांश|मानचित्र|" 
    r"परियोजना|क्रियाकलाप|विषय-सूची)",
    re.IGNORECASE | re.UNICODE,
)
BACKMATTER_HINTS = [
    "exercise", "summary", "map", "project", "activity",
    "question", "questions", "worksheet", "test", "revision",
    "assessment", "practice", "appendix", "glossary",
    "bibliography", "index", "answers", "mcq", "case study",
    "self assessment", "competency", "hots", "model paper",
    "sample paper", "revision test", "additional questions",
    "assertion", "reason", "lab manual",

    # Hindi
    "अभ्यास", "प्रश्न", "प्रश्नावली", "पुनरावृत्ति", "सारांश",
    "मानचित्र", "परियोजना", "क्रियाकलाप", "कार्यपत्रक",
    "परीक्षण", "मूल्यांकन", "अतिरिक्त", "उदाहरण",
    "प्रयोग", "स्वमूल्यांकन"
]

# Subject/section header in table-style TOCs — standalone ALL-CAPS line with
# no page number and no chapter-ID prefix.
_SUBJECT_HEADER_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Z\s\/\-&]{1,58}[A-Z]"
    r"|"
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D]"
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D\s\/\-]*"
    r")$",
    re.UNICODE
)


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
    text = re.sub(r'[.\-_]{2,}', ' ', text)
    text = re.sub(r'[^\u0900-\u097F\w\s\(\)\-\&\/]', '', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _safe_sanitize(text: str) -> str:
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags like <b>, </b>, <i>, <math>…</math> etc."""
    return re.sub(r'<[^>]+>', '', text).strip()


# ── CHANGE 2/4: _is_bare_token helper ────────────────────────────────────────
# Prevents _merge_floating_page_numbers from chaining two orphan tokens
# together (e.g. "1." + "1." → "1. 1.", or "7." + "167-182" → "7. 167-182").
# This was the cause of the "list index out of range" crash.
def _is_bare_token(text: str) -> bool:
    """Return True if text is a bare orphan that must never be a merge target."""
    stripped = text.strip()
    if re.fullmatch(r'\d{1,3}\.', stripped):
        return True   # another bare chapter-ID orphan: "2.", "10."
    if re.fullmatch(r'\d{1,4}\s*(?:-|–|—|to)\s*\d{1,4}', stripped, re.IGNORECASE):
        return True   # bare page range: "167-182"
    if re.fullmatch(r'\d{1,4}', stripped):
        return True   # bare single page number: "45"
    return False
# ─────────────────────────────────────────────────────────────────────────────


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
    text = text.strip()
    if text in _HINDI_KNOWN_SUBJECTS:
        return True
    if not _SUBJECT_HEADER_RE.match(text):
        return False
    if re.search(r'\d', text):
        return False
    sp, _, _ = _extract_page_range(text)
    if sp is not None:
        return False
    if len(text.split()) > 6:
        return False
    is_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if not is_devanagari and not text.isupper():
        return False
    return True


def _parse_table_toc(all_lines: list) -> list:
    structured_data   = []
    active_unit_id    = None
    active_unit_name  = None
    unit_counter      = 0
    global_ch_offset  = 0

    for raw_line in all_lines:
        # Handle both plain string (old path) and dict (new path)
        cleaned = raw_line["text"] if isinstance(raw_line, dict) else raw_line
        cleaned = cleaned.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'\.{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        if not cleaned or len(cleaned) < 2:
            continue

        if _is_subject_header(cleaned):
            unit_counter     += 1
            active_unit_id    = unit_counter
            active_unit_name  = cleaned if re.search(r'[\u0900-\u097F]', cleaned) else cleaned.title()
            if structured_data:
                global_ch_offset = structured_data[-1]["global_chapter_id"]
            print(f"      📦 Subject: {active_unit_id} – {active_unit_name}")
            continue

        if len(cleaned) < 4:
            continue

        row = _parse_table_row(cleaned)
        if row is None:
            continue

        if row["unit_id"] is not None:
            pass
        else:
            row["unit_id"]   = active_unit_id
            row["unit_name"] = active_unit_name

        local_ch_id = row["chapter_id"]
        row["chapter_id"]        = local_ch_id
        row["global_chapter_id"] = global_ch_offset + local_ch_id

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
    Job 2 — attach orphaned bare chapter-ID tokens ("2.", "10.") to the NEXT line.

    CHANGE vs original: Pass 1 now calls _is_bare_token() to prevent merging
    an orphan ID onto another bare token (another ID, a page range, or a bare
    number). Without this guard, two-column math TOCs produce "1. 1." and
    "7. 167-182" which crash downstream parsing.

    Everything else is identical to the original.
    """
    # ── Pass 1: merge orphan "N." forward onto the next line ────────────────
    pre = []
    i = 0
    while i < len(lines):
        curr      = lines[i]
        curr_text = curr["text"] if isinstance(curr, dict) else curr
        stripped  = curr_text.strip()

        if re.fullmatch(r'\d{1,3}\.', stripped) and i + 1 < len(lines):
            next_line     = lines[i + 1]
            next_text     = next_line["text"] if isinstance(next_line, dict) else next_line
            next_stripped = next_text.strip()

            # Original guard: next must not already be a complete chapter line
            already_complete = bool(re.match(r'^\d+\.?\s', next_stripped))
            # CHANGE: new guard — next must not be another bare token
            next_is_bare = _is_bare_token(next_stripped)

            if not already_complete and not next_is_bare:
                merged_text = stripped + " " + next_stripped
                # Preserve x from the orphan ID line (it has the indent position)
                merged_entry = {
                    "text": merged_text,
                    "x": curr["x"] if isinstance(curr, dict) else None
                }
                pre.append(merged_entry)
                print(f"      🔗 Merged orphan ID forward: [{stripped}] + [{next_stripped}]")
                i += 2
                continue
            else:
                print(f"      ⚠️  Skipped bad forward merge: [{stripped}] + [{next_stripped}]")

        pre.append(curr)
        i += 1

    # ── Pass 2: merge orphan bare numbers/ranges backward onto previous line ─
    # Identical to original, just handles both dict and plain string.
    merged = []
    for line in pre:
        text     = line["text"] if isinstance(line, dict) else line
        stripped = text.strip()
        is_num   = re.fullmatch(
            r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE
        )
        if is_num and merged:
            prev      = merged[-1]
            prev_text = prev["text"] if isinstance(prev, dict) else prev
            if prev_text.strip():
                if isinstance(prev, dict):
                    merged[-1]["text"] = prev_text.strip() + " " + stripped
                else:
                    merged[-1] = prev_text.strip() + " " + stripped
                continue
        merged.append(line)
    return merged


def _is_continuation_line(text: str) -> bool:
    """
    Return True if a line looks like the wrapped tail of a chapter name.
    UNCHANGED from original.
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
    if re.fullmatch(r'\d{1,3}\.?', text.strip()):
        return False
    sp, _, _ = _extract_page_range(text)
    if sp is not None:
        return False
    if len(text) > 80:
        return False
    if text.isupper() and len(text.split()) <= 3:
        return False
    return True


def _merge_two_line_chapters(lines: list) -> list:
    """
    Merges multi-line TOC entries into single lines.
    UNCHANGED from original except: handles both dict and plain string input,
    and preserves x coordinate from the first line through merges.
    """
    merged = []
    i = 0
    while i < len(lines):
        curr         = lines[i]
        current_text = (curr["text"] if isinstance(curr, dict) else curr).strip()
        current_clean = _strip_html(current_text)

        # ── Case 1: standalone label only ────────────────────────────────────
        if _STANDALONE_CH.match(current_clean) and i + 1 < len(lines):
            next_line  = lines[i + 1]
            next_text  = (next_line["text"] if isinstance(next_line, dict) else next_line).strip()
            next_clean = _strip_html(next_text)

            if not _STANDALONE_CH.match(next_clean):
                if i + 2 < len(lines):
                    next2      = lines[i + 2]
                    next2_text = (next2["text"] if isinstance(next2, dict) else next2).strip()
                    next2_clean = _strip_html(next2_text)

                    if re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?',
                                    next2_clean, re.IGNORECASE):
                        merged_line = current_clean + " " + next_clean + " " + next2_clean
                        merged.append({
                            "text": merged_line,
                            "x": curr["x"] if isinstance(curr, dict) else None
                        })
                        print(f"      🔗 Merged three-line chapter: [{current_clean}] + "
                              f"[{next_clean}] + [{next2_clean}]")
                        i += 3
                        continue

                merged_line = current_clean + " " + next_clean
                merged.append({
                    "text": merged_line,
                    "x": curr["x"] if isinstance(curr, dict) else None
                })
                print(f"      🔗 Merged two-line chapter: [{current_clean}] + [{next_clean}]")
                i += 2
                continue

        # ── Case 2 & 3: continuation / orphan line ───────────────────────────
        if merged and _is_continuation_line(current_clean):
            prev      = merged[-1]
            prev_text = prev["text"] if isinstance(prev, dict) else prev
            prev_sp, _, _ = _extract_page_range(prev_text)

            if prev_sp is None:
                if isinstance(merged[-1], dict):
                    merged[-1]["text"] = merged[-1]["text"].strip() + " " + current_clean
                else:
                    merged[-1] = merged[-1].strip() + " " + current_clean
                print(f"      🔗 Appended continuation: [{current_clean}] → merged into previous")
            else:
                print(f"      ⏭  Skipped orphan continuation: [{current_clean}]")
            i += 1
            continue

        merged.append(curr)
        i += 1
    return merged


def _detect_id_style(lines: list) -> str:
    """
    Vote on the predominant chapter-ID style.
    UNCHANGED from original except: handles dict format.
    """
    votes = {"Indian": 0, "roman": 0, "word": 0}
    for line in lines:
        text = line["text"] if isinstance(line, dict) else line
        text = _strip_html(text.strip())
        if re.fullmatch(r'\d{1,4}(\s*[-–—]\s*\d{1,4})?', text):
            continue
        if _SUBTOPIC_ID.match(text) or _Indian_ID.match(text):
            votes["Indian"] += 1
        elif _WORD_CH_ID.match(text):
            votes["word"] += 1
        elif _ROMAN_ID.match(text):
            tok = text.split()[0].rstrip(".")
            if roman_to_int(tok) is not None:
                votes["roman"] += 1
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
    UNCHANGED from original.
    """
    if re.fullmatch(r'\d{1,4}(\s*[-–—to]\s*\d{1,4})?', cleaned.strip()):
        return None

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

    return None


def _jump_ok(ch_int: int, last: int, max_jump: int) -> bool:
    """UNCHANGED from original."""
    if ch_int < 1:
        return False
    if last == 0:
        return True
    return 0 < ch_int - last <= max_jump or ch_int == last

# ─────────────────────────────────────────────────────────────────────────────
# CORE ROBUST TRANSFORM LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def robust_transform_logic(self, raw_pages: list) -> list:
    print("🧠 [TOC_TRANSFORM] Converting lines to structured JSON (ROBUST MODE)…")

    # ── collect all lines across pages ──────────────────────────────────────
    all_lines = []
    for page in raw_pages:
        lines  = page.get("lines", [])
        merged = _merge_floating_page_numbers(lines)
        merged = _merge_two_line_chapters(merged)
        all_lines.extend(merged)

    # ── CHANGE 3/4: build coord level function once, safely ──────────────────
    # Called AFTER merges so page-number elements are already absorbed.
    # Wrapped in try/except so any clustering failure is a silent no-op —
    # the rest of the pipeline is completely unaffected.
    try:
        level_fn, num_levels = build_level_fn(all_lines)
        if num_levels > 1:
            print(f"      📍 Coord clustering: {num_levels} indent levels detected")
        else:
            print(f"      📍 Coord clustering: flat layout, coord assist disabled")
            level_fn = lambda x: None   # flat → coords can't help with hierarchy
    except Exception as e:
        print(f"      ⚠️  Coord clustering skipped ({e})")
        level_fn = lambda x: None
    # ─────────────────────────────────────────────────────────────────────────

    # ── detect dominant ID style ─────────────────────────────────────────────
    id_style = _detect_id_style(all_lines)
    print(f"      📐 Detected chapter-ID style: {id_style.upper()}")

    # ── detect if this is a TABLE-style TOC ─────────────────────────────────
    table_hits = sum(
        1 for l in all_lines
        if _TABLE_ROW_FULL.match(
            (l["text"] if isinstance(l, dict) else l).strip()
        ) or _TABLE_ROW_CHAPTER_ONLY.match(
            (l["text"] if isinstance(l, dict) else l).strip()
        )
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
        # Extract text and x — handles both dict and plain string
        text = line["text"] if isinstance(line, dict) else line
        x    = line.get("x") if isinstance(line, dict) else None

        if self.is_header_or_footer(text):
            continue
        cleaned = self.clean_text(text)
        if not cleaned or len(cleaned) < self.min_line_length:
            continue

        # ── Theme header ─────────────────────────────────────────────────────
        theme_m = _THEME_HEADER.match(cleaned)
        if theme_m:
            active_unit_id   = theme_m.group(1).upper()
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

        # ── CHANGE 4/4: coord fallback — only when regex found nothing ────────
        # Fires ONLY when:
        #   1. _parse_line returned None (regex found no chapter/subtopic)
        #   2. coord clustering found multiple levels (num_levels > 1)
        #   3. this line's x-position maps to 'unit' level
        #   4. the line has no page number (pure label, not a data row)
        # Use case: plain-text unit headers with no keyword, e.g. "HISTORY",
        # "भूगोल" — regex can't match them, but they sit visually further left.
        if entry is None and level_fn(x) == "unit":
            sp, _, _ = _extract_page_range(cleaned)
            if sp is None:
                # No page number + unit-level indent = plain unit header
                active_unit_name = _safe_sanitize(cleaned)
                active_unit_id   = (
                    active_unit_id if isinstance(active_unit_id, int) else 0
                ) + 1
                print(f"      📦 [COORD] Unit detected: {active_unit_name}")
            # Always skip this line regardless — coord said unit level,
            # it cannot be a chapter entry even if it has a page number
            continue
        # ─────────────────────────────────────────────────────────────────────

        # ── Fallback: horizontal subtopics ───────────────────────────────────
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
            is_backmatter = (
                _BACKMATTER_RE.match(cleaned)
                or any(word in cleaned.lower() for word in BACKMATTER_HINTS)
            )

            if is_backmatter:
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

    # ── back-fill end pages (UNCHANGED) ─────────────────────────────────────
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