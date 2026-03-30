"""
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
# COMPILED PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

# --- Chapter / section ID patterns ---

# Indian:  "3." or "3 " at start
_Indian_ID    = re.compile(r"^(\d+)\.?\s+")

# Subtopic: "3.1" or "3.1.2" (must NOT be a plain float like 3.14)
_SUBTOPIC_ID  = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?\s+")

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
_ROMAN_ID     = re.compile(r"^([IVXLCDM]+)\.?\s+", re.IGNORECASE)

# FIX 1: \s+ → \s*  so "Chapter1" (no space, common OCR output) is matched.
# FIX 1b: digit-first alternation so "Chapter10" greedily captures "10" not "1".
_WORD_CH_ID   = re.compile(
    r"^(?:chapter|unit|section|part)\s*(\d+|[a-z]+)\s*(?:[\.\:\-–])?\s*",
    re.IGNORECASE,
)

# --- Page number / range at END of line ---
_PAGE_RANGE   = re.compile(
    r"(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*[\w\.\,\%\*]*\s*$",
    re.IGNORECASE,
)
_PAGE_SINGLE  = re.compile(r'(?<!\d)(\d{1,4})\s*$')

# --- Unit header line (standalone, no chapter number) ---
_UNIT_HEADER  = re.compile(
    r"^(?:unit|section|part)\s+(\d+|[IVXLCDM]+)\s*[:\-–]?\s*(.+)?$",
    re.IGNORECASE,
)

# FIX 2: \s+ → \s*  so "Chapter1" (no space) is detected as standalone too.
_STANDALONE_CH = re.compile(
    r"^(?:chapter|unit|section|part)\s*(\d+|[IVXLCDM]+|[a-z]+)\s*$",
    re.IGNORECASE,
)

# --- Table-style TOC row patterns ---
_TABLE_ROW_FULL = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
_TABLE_ROW_CHAPTER_ONLY = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
_TABLE_ROW_UNIT_ONLY = re.compile(
    r'^(\d+)\.\s+([A-Za-z][^\d]+?)\s*$'
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
    """Remove leader dots, dashes, underscores and trailing punctuation."""
    text = re.sub(r'[.\-_]{2,}', ' ', text)
    text = re.sub(r'[^\w\s\(\)\-\&\/]', '', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _safe_sanitize(text: str) -> str:
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'[^\w\s\-\&\(\)\/]', '', text, flags=re.UNICODE)
    return re.sub(r'\s{2,}', ' ', text).strip()


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags like <b>, </b>, <i>, <math>...</math> etc."""
    return re.sub(r'<[^>]+>', '', text).strip()

# ─────────────────────────────────────────────────────────────────────────────
# TABLE-STYLE TOC PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_table_row(cleaned: str):
    """
    Try to parse a line as a table-style TOC row.
    Returns a dict or None.
    """
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


def _parse_table_toc(all_lines: list) -> list:
    """Parser for table-layout TOCs."""
    structured_data = []
    active_unit_id   = None
    active_unit_name = None

    for raw_line in all_lines:
        cleaned = raw_line.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'\.{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        if not cleaned or len(cleaned) < 4:
            continue

        row = _parse_table_row(cleaned)
        if row is None:
            continue

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
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _merge_floating_page_numbers(lines: list) -> list:
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


def _merge_two_line_chapters(lines: list) -> list:
    """
    Merges two-line TOC entries where the chapter label appears alone on one
    line and the chapter name (and optional page) follows on the next.

    Also handles the case where a chapter's name wraps to a continuation line
    (no chapter keyword, no page number) — e.g. "WITH WHOLE NUMBER" after
    "Chapter 2  WHOLE NUMBER AND OPERATIONS  4-19".
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
                    page_line  = _strip_html(lines[i + 2].strip())
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

        # ── Case 2: continuation line — wraps from previous chapter name ──
        # Heuristic: line has no chapter keyword, no page number, and the
        # previous merged line already has a page number → append name fragment.
        elif (merged
              and not _WORD_CH_ID.match(current_clean)
              and not _Indian_ID.match(current_clean)
              and not _STANDALONE_CH.match(current_clean)
              and not re.fullmatch(r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?',
                                   current_clean, re.IGNORECASE)):
            sp, ep, _ = _extract_page_range(current_clean)
            prev_sp, prev_ep, _ = _extract_page_range(merged[-1])
            # Only treat as continuation if THIS line has no page number
            # and the previous line already has one (so the chapter is "done")
            # We skip it silently — it's a wrapped subtitle, not a new chapter.
            if sp is None and prev_sp is not None:
                print(f"      ⏭  Skipped continuation line: [{current_clean}]")
                i += 1
                continue

        merged.append(current_raw)
        i += 1
    return merged


def _detect_id_style(lines: list) -> str:
    """
    Scan lines and vote on the predominant chapter-ID style.

    FIX: Uses the updated _WORD_CH_ID (with \\s* instead of \\s+) so that
    "Chapter1" (no space, common in Surya OCR output) counts as a word-style
    vote rather than falling through to Indian by default.

    Returns: 'Indian' | 'roman' | 'word'
    """
    votes = {"Indian": 0, "roman": 0, "word": 0}
    for line in lines:
        line = _strip_html(line.strip())   # strip HTML before voting
        if _SUBTOPIC_ID.match(line) or _Indian_ID.match(line):
            votes["Indian"] += 1
        elif _WORD_CH_ID.match(line):      # uses the fixed pattern (\\s*)
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
    # Skipped for roman-style TOCs: single-letter Romans like "I." / "V." are
    # indistinguishable from unnumbered labels at this pattern level.
    # Roman subtopics use "I.1" notation, handled by _ROMAN_SUBTOPIC_ID above.
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

    # ── 2. Word chapter: "Chapter 1  ..." or "Chapter1  ..." ─────────────────
    #    Checked BEFORE Indian so that "Chapter 1 ..." is not matched by
    #    _Indian_ID when clean_text() has already stripped the "Chapter" keyword.
    #    We try word style regardless of detected id_style when the line starts
    #    with a chapter keyword — this makes the parser robust to clean_text
    #    implementations that strip or preserve the keyword differently.
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

    Key fixes vs. original:
      • _WORD_CH_ID uses \\s* so "Chapter1" (no space) is matched.
      • _STANDALONE_CH uses \\s* for the same reason.
      • _parse_line tries word-style match BEFORE Indian/Roman, making it
        robust regardless of whether clean_text() strips the chapter keyword.
      • _merge_two_line_chapters now also silently drops continuation lines
        (e.g. "WITH WHOLE NUMBER") that are wrapped subtitle fragments.
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

        # ── Fallback: unnumbered subtopic detection ───────────────────────────
        if entry is None and last_chapter_int > 0:
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
# PUBLIC API  — patch function & mixin
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