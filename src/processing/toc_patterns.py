"""
toc_patterns.py  — Drop-in extension for TOCProcessorAPI
=========================================================
Import this module and call `patch_toc_processor(api_instance)` after creating
your TOCProcessorAPI object, OR use TOCPatternMixin as a mixin.

NO changes are required to your existing toc_extractor.py.

Supports all patterns:
  • Numbered chapters   (1, 2, 3 …)
  • Roman-numeral chapters (I, II, III … / i, ii, iii …)
  • Unnumbered / word chapters  ("Chapter One", "Chapter Two" …)
  • With or without units
  • With or without subtopics (1.1, 1.2 …)
  • Page ranges  (12 – 34)
  • Trailing junk after page numbers (marks, periods, percentages …)
  • Various column layouts (#1 – #8 from the spec)
  • Table-style TOCs (Unit | Chapter | Page columns)

Usage A – monkey-patch an existing instance
--------------------------------------------
    from toc_patterns import patch_toc_processor
    api = TOCProcessorAPI()
    patch_toc_processor(api)
    results, frames = api.run_api(images)

Usage B – subclass (zero changes to toc_extractor.py)
------------------------------------------------------
    from toc_patterns import RobustTOCProcessor
    api = RobustTOCProcessor()
    results, frames = api.run_api(images)
"""

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
# COMPILED PATTERNS  (all used inside the patched transform_logic)
# ─────────────────────────────────────────────────────────────────────────────

# --- Chapter / section ID patterns ---

# Arabic:  "3." or "3 " at start
_ARABIC_ID    = re.compile(r"^(\d+)\.?\s+")

# Subtopic: "3.1" or "3.1.2" (must NOT be a plain float like 3.14)
_SUBTOPIC_ID  = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?\s+")

# Roman:   "III." or "III " or "iii " at start
_ROMAN_ID     = re.compile(r"^([IVXLCDM]+)\.?\s+", re.IGNORECASE)

# Word:    "Chapter One" / "CHAPTER 1" / "Unit Two" / "Chapter 1 : Name"
_WORD_CH_ID   = re.compile(
    r"^(?:chapter|unit|section|part)\s+([a-z]+|\d+)\s*(?:[\.\:\-–])?\s*",
    re.IGNORECASE,
)

# --- Page number / range at END of line ---
# Handles: 12  |  12-34  |  12 – 34  |  12 to 34
# Followed optionally by junk: marks, periods, %, letters
_PAGE_RANGE   = re.compile(
    r"(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*[\w\.\,\%\*]*\s*$",
    re.IGNORECASE,
)
# FIX: anchored to end, won't eat digits inside chapter names
_PAGE_SINGLE  = re.compile(
    r'(?<!\d)(\d{1,4})\s*$'
)

# --- Unit header line (standalone, no chapter number) ---
# e.g. "UNIT 1  Introduction to Biology"
_UNIT_HEADER  = re.compile(
    r"^(?:unit|section|part)\s+(\d+|[IVXLCDM]+)\s*[:\-–]?\s*(.+)?$",
    re.IGNORECASE,
)

# --- Standalone chapter-label line (two-line TOC format) ---
# Matches lines that are ONLY a chapter label with no name after them
# e.g. "Chapter 1"  /  "Chapter One"  /  "CHAPTER IV"
_STANDALONE_CH = re.compile(
    r"^(?:chapter|unit|section|part)\s+(\d+|[IVXLCDM]+|[a-z]+)\s*$",
    re.IGNORECASE,
)

# --- Table-style TOC row patterns ---
# Full row:    "1. Algebra 1. Polynomials 01-28"  (unit + chapter + page on same OCR line)
_TABLE_ROW_FULL = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
# Chapter-only row: "2. Linear Equation in two variables 29-64"  (unit cell was empty in table)
_TABLE_ROW_CHAPTER_ONLY = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
# Unit-only row: "1. Algebra"  (chapter cell was empty — rare)
_TABLE_ROW_UNIT_ONLY = re.compile(
    r'^(\d+)\.\s+([A-Za-z][^\d]+?)\s*$'
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_page_range(text: str):
    """Return (start_page, end_page, text_before_page) from a line."""
    # Range: grab the LAST occurrence of N–M
    m = re.search(r'(\d+)\s*(?:-|–|—|to)\s*(\d+)(?!.*\d+\s*(?:-|–|—|to)\s*\d+)', text)
    if m:
        return int(m.group(1)), int(m.group(2)), text[:m.start()].strip()

    # FIX: Single page anchored to true end of string.
    # Requires a non-digit character before it so we don't eat "Algebra 1".
    m = re.search(r'(?<!\d)(\d{1,4})\s*$', text)
    if m:
        before = text[:m.start()].strip()
        if before:  # there must still be a name before this number
            return int(m.group(1)), None, before

    return None, None, text.strip()


def _strip_trailing_junk(text: str) -> str:
    """Remove leader dots, dashes, underscores and trailing punctuation."""
    text = re.sub(r'[.\-_]{2,}', ' ', text)      # leader dots/dashes
    text = re.sub(r'[^\w\s\(\)\-\&\/]', '', text) # non-word chars except useful ones
    return re.sub(r'\s{2,}', ' ', text).strip()


def _safe_sanitize(text: str) -> str:
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'[^\w\s\-\&\(\)\/]', '', text, flags=re.UNICODE)
    return re.sub(r'\s{2,}', ' ', text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# TABLE-STYLE TOC PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_table_row(cleaned: str):
    """
    Try to parse a line as a table-style TOC row.
    Returns a dict with keys: unit_id, unit_name, chapter_id, chapter_name, start_page, end_page
    Returns None if not a table row.
    """
    # Full row: unit + chapter + page
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

    # Chapter-only row (unit cell was blank in the table)
    m = _TABLE_ROW_CHAPTER_ONLY.match(cleaned)
    if m:
        ch_id   = int(m.group(1))
        ch_name = _safe_sanitize(m.group(2))
        start_p, end_p, _ = _extract_page_range(m.group(3))
        return dict(unit_id=None, unit_name=None,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    return None


def _parse_table_toc(all_lines: list) -> list:
    """
    Parser for table-layout TOCs where OCR reads rows as flat lines like:
      "1. Algebra 1. Polynomials 01-28"        ← unit + chapter + page
      "2. Linear Equation in two variables 29-64"  ← chapter-only (unit cell empty)
    Unit context is carried forward across chapter-only rows.
    """
    structured_data = []
    active_unit_id   = None
    active_unit_name = None

    for raw_line in all_lines:
        cleaned = raw_line.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)        # strip HTML
        cleaned = re.sub(r'\.{2,}', ' ', cleaned)        # strip leader dots
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        if not cleaned or len(cleaned) < 4:
            continue

        row = _parse_table_row(cleaned)
        if row is None:
            continue

        # Carry forward unit context when unit cell was blank
        if row["unit_id"] is not None:
            active_unit_id   = row["unit_id"]
            active_unit_name = row["unit_name"]
        else:
            row["unit_id"]   = active_unit_id
            row["unit_name"] = active_unit_name

        is_sub = row.get("is_subtopic", False)
        print(f"      {'  ↳' if is_sub else '⭐'} "
              f"Ch {row['chapter_id']} – {row['chapter_name']} "
              f"[Unit: {row['unit_id']}] [Page: {row['start_page']}–{row['end_page']}]")

        structured_data.append(row)

    return structured_data


# ─────────────────────────────────────────────────────────────────────────────
# CORE ROBUST TRANSFORM LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def robust_transform_logic(self, raw_pages: list) -> list:
    """
    Replacement for TOCProcessorAPI.transform_logic that handles all TOC patterns.

    Detects the dominant chapter-ID style (arabic / roman / word) on the first
    pass and then uses the matching extractor.  Falls back gracefully if the
    style cannot be determined.
    """
    print("🧠 [TOC_TRANSFORM] Converting lines to structured JSON (ROBUST MODE)…")

    # ── collect all lines across pages ──────────────────────────────────────
    all_lines = []
    for page in raw_pages:
        lines = page.get("lines", [])
        merged = _merge_floating_page_numbers(lines)
        merged = _merge_two_line_chapters(merged)   # ← handles "Chapter 1\nName pg" format
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
        print(f"      📊 Table-style TOC detected ({table_hits} matching rows) — switching to table parser")
        return _parse_table_toc(all_lines)

    # ── parse lines ─────────────────────────────────────────────────────────
    structured_data = []
    active_unit_id   = None
    active_unit_name = None
    last_chapter_int = 0   # always keep as integer for jump-check
    subtopic_counters = {}  # {chapter_int: count} for 1.1, 1.2 ...

    for line in all_lines:
        if self.is_header_or_footer(line):
            continue
        cleaned = self.clean_text(line)
        if not cleaned or len(cleaned) < self.min_line_length:
            continue
        # print(f"      🔍 ALL LINES: {all_lines}")  #****  
        # ── Unit-header-only lines (no chapter number on same line) ────── 
        unit_m = _UNIT_HEADER.match(cleaned)
        if unit_m and not _has_chapter_after_unit(cleaned):
            uid_raw = unit_m.group(1)
            uid_int = (_to_int(uid_raw, "arabic") or 
                    _to_int(uid_raw, "roman") or 
                    _to_int(uid_raw, "word"))
            active_unit_id   = uid_int
            active_unit_name = _safe_sanitize(unit_m.group(2) or "")
            print(f"      📦 Unit: {active_unit_id} – {active_unit_name}")
            continue

        # ── Attempt to parse as a structured entry ───────────────────────
        entry = _parse_line(cleaned, id_style, last_chapter_int, self.max_chapter_jump)
        if entry is None:
            continue

        ch_int, ch_name, start_p, end_p, is_subtopic, raw_subtopic_id = entry

        # Attach current unit context
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

            entry_dict["is_subtopic"] = True
            entry_dict["subtopic_id"] = subtopic_id
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
            next_start = structured_data[i + 1]["start_page"]
            if next_start:
                structured_data[i]["end_page"] = next_start - 1
    
    return structured_data
    


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _merge_floating_page_numbers(lines: list) -> list:
    """Same logic as the original but extracted for reuse."""
    merged = []
    for line in lines:
        stripped = line.strip()
        is_num = re.fullmatch(
            r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE
        )
        if is_num and merged and re.match(r'^\d+', merged[-1].strip()):
            merged[-1] = merged[-1].strip() + " " + stripped
        else:
            merged.append(line)
    return merged


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags like <b>, </b>, <i>, <math>...</math> etc."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _merge_two_line_chapters(lines: list) -> list:
    """
    Handles TOCs where the chapter label and chapter name are on separate lines:

        <b>Chapter 1</b>          ← standalone label line (possibly with HTML tags)
        Large Numbers Around Us 1 ← name + page on next line

    Merges them into a single line:
        Chapter 1 Large Numbers Around Us 1
    """
    merged = []
    i = 0
    while i < len(lines):
        current_raw = lines[i].strip()
        current_clean = _strip_html(current_raw)

        # Check if this line is ONLY a chapter label (no name after it)
        if _STANDALONE_CH.match(current_clean) and i + 1 < len(lines):
            next_raw = lines[i + 1].strip()
            next_clean = _strip_html(next_raw)
            if not _STANDALONE_CH.match(next_clean):
                # Also grab next-next line if it's just a page number
                if (i + 2 < len(lines) and 
                    re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', 
                                _strip_html(lines[i + 2].strip()), re.IGNORECASE)):
                    page_line = _strip_html(lines[i + 2].strip())
                    merged_line = current_clean + " " + next_clean + " " + page_line
                    merged.append(merged_line)
                    print(f"      🔗 Merged three-line chapter: [{current_clean}] + [{next_clean}] + [{page_line}]")
                    i += 3
                    continue
                merged_line = current_clean + " " + next_clean
                merged.append(merged_line)
                print(f"      🔗 Merged two-line chapter: [{current_clean}] + [{next_clean}]")
                i += 2
                continue
        merged.append(current_raw)
        i += 1
    return merged


def _detect_id_style(lines: list) -> str:
    """
    Scan lines and vote on the predominant chapter-ID style.
    Returns: 'arabic' | 'roman' | 'word'
    """
    votes = {"arabic": 0, "roman": 0, "word": 0}
    for line in lines:
        line = line.strip()
        if _SUBTOPIC_ID.match(line) or _ARABIC_ID.match(line):
            votes["arabic"] += 1
        elif _WORD_CH_ID.match(line):
            votes["word"] += 1
        elif _ROMAN_ID.match(line):
            tok = line.split()[0].rstrip(".")
            if roman_to_int(tok) is not None:
                votes["roman"] += 1
    # arabic wins ties (most common)
    return max(votes, key=lambda k: (votes[k], k == "arabic"))


def _to_int(token: str, style: str) -> Optional[int]:
    """Convert a token to integer given the style."""
    token = token.strip()
    if style == "arabic":
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
    """True if the line contains a chapter number after the unit keyword."""
    # e.g. "Unit 1  3  Cell Biology  12"  — has extra numeric token
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
    Try to parse a single cleaned line into (ch_int, ch_name, start_p, end_p, is_subtopic).
    Returns None if the line does not match any known pattern.
    """

    # ── 1. Subtopic pattern:  "1.1" or "1.1.2" ───────────────────────────
    sub_m = _SUBTOPIC_ID.match(cleaned)
    if sub_m:
        parent_id = int(sub_m.group(1))
        sub_id_str = sub_m.group(1) + "." + sub_m.group(2)
        if sub_m.group(3):
            sub_id_str += "." + sub_m.group(3)
        rest = cleaned[sub_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}] → rest=[{rest}] name_raw=[{name_raw}]")
            return None
        # Use parent chapter id as integer, store dotted string separately
        return (parent_id, name, start_p, end_p, True, sub_id_str)

    # ── 2. Arabic chapter: "3 Chapter Name  45" ──────────────────────────
    if id_style == "arabic":
        m = _ARABIC_ID.match(cleaned)
        if not m:
            return None
        ch_int = int(m.group(1))
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}] → rest=[{rest}] name_raw=[{name_raw}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    # ── 3. Roman numeral chapter: "III  Cell Biology  45" ────────────────
    if id_style == "roman":
        m = _ROMAN_ID.match(cleaned)
        if not m:
            return None
        tok = m.group(1)
        ch_int = roman_to_int(tok)
        if ch_int is None:
            return None
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}] → rest=[{rest}] name_raw=[{name_raw}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    # ── 4. Word chapter: "Chapter One  Cell Biology  45" ─────────────────
    if id_style == "word":
        m = _WORD_CH_ID.match(cleaned)
        if not m:
            return None
        num_tok = m.group(1)
        ch_int = word_to_int(num_tok)
        if ch_int is None:
            ch_int = int(num_tok) if num_tok.isdigit() else None
        if ch_int is None:
            return None
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest)
        name = _safe_sanitize(_strip_trailing_junk(name_raw))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}] → rest=[{rest}] name_raw=[{name_raw}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    return None


def _jump_ok(ch_int: int, last: int, max_jump: int) -> bool:
    """Return True if the chapter ID is a plausible successor."""
    if ch_int < 1:
        return False
    if last == 0:
        return True   # first chapter — accept anything reasonable
    return 0 < ch_int - last <= max_jump or ch_int == last


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API  — patch function & mixin
# ─────────────────────────────────────────────────────────────────────────────

def patch_toc_processor(api_instance):
    """
    Monkey-patch an existing TOCProcessorAPI instance so that
    transform_logic uses the robust multi-pattern implementation.

    Call this immediately after creating your api object:

        api = TOCProcessorAPI()
        patch_toc_processor(api)
    """
    import types
    api_instance.transform_logic = types.MethodType(robust_transform_logic, api_instance)
    print("✅ [toc_patterns] Robust transform_logic patched successfully.")


class RobustTOCProcessor:
    """
    Convenience subclass: same as TOCProcessorAPI but uses robust_transform_logic
    automatically.  Import and use instead of TOCProcessorAPI — zero other changes.

    from toc_patterns import RobustTOCProcessor
    api = RobustTOCProcessor()
    results, frames = api.run_api(images)
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __new__(cls, *args, **kwargs):
        # Late import to avoid circular dependency
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        try:
            from modules.toc_extractor import TOCProcessorAPI
        except ImportError:
            # Fallback: try same directory
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
        # Make instance look like RobustTOCProcessor
        instance.__class__ = type(
            "RobustTOCProcessor",
            (TOCProcessorAPI,),
            {"transform_logic": robust_transform_logic}
        )
        return instance