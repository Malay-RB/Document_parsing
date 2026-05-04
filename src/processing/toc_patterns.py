import re
from typing import Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIG
# All regex patterns, word maps, and hint lists live here as private defaults.
# They are NOT exposed as standalone globals — the only public interface is
# TOCConfig and DEFAULT_CONFIG.
# To customise for a specific book, pass a TOCConfig instance into
# robust_transform_logic() and it will flow through the entire pipeline.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Numeral maps ──────────────────────────────────────────────────────────────

_ROMAN_MAP = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100,  "C"), (90,  "XC"), (50,  "L"), (40,  "XL"),
    (10,   "X"), (9,   "IX"), (5,   "V"), (4,   "IV"), (1, "I"),
]

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}

_HINDI_WORD_NUMS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5,
    "पाँच": 5, "छः": 6, "छह": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12,
    "तेरह": 13, "चौदह": 14, "पन्द्रह": 15, "सोलह": 16,
    "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
}

_HINDI_KNOWN_SUBJECTS = {
    "इतिहास", "भूगोल", "नागरिकशास्त्र", "अर्थशास्त्र",
    "समाजिक विज्ञान", "सामाजिक विज्ञान", "राजनीति विज्ञान",
    "विज्ञान", "गणित", "हिंदी", "संस्कृत", "पर्यावरण अध्ययन",
    "राजनीतिशास्त्र", "समकालीन भारत", "लोकतांत्रिक राजनीति",
}

# ── Default regex patterns (private — use via TOCConfig, not directly) ────────

_D_ROMAN_RE = re.compile(
    r"^(M{0,4})(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)
_D_INDIAN_ID = re.compile(r"^(\d+)\.?\s+")
_D_SUBTOPIC_ID = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?\s+")
_D_ROMAN_SUBTOPIC_ID = re.compile(
    r"^([IVXLCDM]+)\.([IVXLCDM]+|\d+)\s+",
    re.IGNORECASE,
)
_D_UNNUMBERED_SUBTOPIC_ID = re.compile(
    r"^(?:\(([a-z])\)|([a-z])\.)\s+",
    re.IGNORECASE,
)
_D_ROMAN_ID = re.compile(r"^([IVXLCDM]+)\.?\s+", re.IGNORECASE)
_D_WORD_CH_ID = re.compile(
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड)\s*[-–]?\s*"
    r"(\d+|[a-z]+|[\u0900-\u097F]+)"
    r"\s*(?:[\.\:\-–])?\s*",
    re.IGNORECASE,
)
_D_STANDALONE_CH = re.compile(
    r"^(?:chapter|unit|section|part|अध्याय|इकाई|भाग|खंड|विभाग)\s*[-–]?\s*"
    r"(\d+|[IVXLCDM]+|[a-z]+)\s*$",
    re.IGNORECASE,
)
_D_DASH_UNIT_ID = re.compile(
    r"^(?:unit|इकाई|भाग|खंड)\s*-\s*(\d+)\s+",
    re.IGNORECASE,
)
_D_DASH_CHAPTER_ID = re.compile(
    r"^(?:chapter|अध्याय)\s*-\s*0*(\d+)\s+",
    re.IGNORECASE,
)
_D_PAGE_RANGE = re.compile(
    r"(\d+)\s*(?:[-–—]|to)\s*(\d+)\s*[\w\.\,\%\*]*\s*$",
    re.IGNORECASE,
)
_D_PAGE_SINGLE = re.compile(r'(?<!\d)(\d{1,4})\s*$')
_D_UNIT_HEADER = re.compile(
    r"^(?:unit|section|part|theme|इकाई|भाग|खंड|विषय)\s+(.+?)\s*[:\-–—]?\s*(.+)?$",
    re.IGNORECASE,
)
_D_THEME_HEADER = re.compile(
    r"^(?:theme|विषय)\s+([A-Za-z\u0900-\u097F])\s*[-–—]\s*(.+)$",
    re.IGNORECASE,
)
_D_TABLE_ROW_FULL = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d+)\.\s+(.+?)\s+(\d{1,3}[-–—]\d{1,3})\s*$'
)
_D_TABLE_ROW_CHAPTER_ONLY = re.compile(
    r'^(\d+)\.?\s+(.+?)\s+(\d{1,3}\s*[-–—]\s*\d{1,3})\s*$'
)
_D_TABLE_ROW_UNIT_ONLY = re.compile(
    r'^(\d+)\.\s+([A-Za-z][^\d]+?)\s*$'
)
_D_TABLE_ROW_FULL_NODOT = re.compile(
    r'^(\d+)\.\s+(.+?)\s+(\d+)\.?\s+(.+?)\s+(\d{1,3}\s*[-–—]\s*\d{1,3})\s*$'
)
_D_SUBJECT_HEADER_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Z\s\/\-&]{1,58}[A-Z]"
    r"|"
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D]"
    r"[\u0900-\u097F\u0902-\u0903\u093E-\u094D\s\/\-]*"
    r")$",
    re.UNICODE,
)
_D_BACKMATTER_RE = re.compile(
    r"^(?:glossary|answers?|index|foreword|appendix|images?\s+and|bibliography|"
    r"acknowledgements?|about\s+the|method\s+of|note\s+to|letter\s+to|"
    r"your\s+journey|preface|introduction|Learning Material Sheets|Vedic Ganit |"
    r"शब्दावली|उत्तर|अनुक्रमणिका|प्रस्तावना|परिशिष्ट|ग्रंथसूची|"
    r"आमुख|भूमिका|टिप्पणी|पत्र|"
    r"अभ्यास|प्रश्नावली|पुनरावृत्ति|सारांश|मानचित्र|"
    r"परियोजना|क्रियाकलाप|विषय-सूची)",
    re.IGNORECASE | re.UNICODE,
)
_D_OCR_ARTIFACT_RE = re.compile(
    r"\\?frac\d*\s*|\\[a-zA-Z]+\s*",
    re.IGNORECASE,
)
_D_LOOSE_TABLE_ROW = re.compile(
    r'^\d+\.\s+.{4,}\s+\d{1,3}\s*[-–—]\s*\d{1,3}\s*$'
)
_D_TABLE_CH_LINE = re.compile(
    r'^(\d+)[\.\-]\s+(.+?)\s+(\d{1,3}\s*[-–—]\s*\d{1,3})\s*$'
)
_D_TABLE_UNIT_ONLY = re.compile(r'^(\d+)\.\s+([^\d].+?)$')

_D_BACKMATTER_HINTS = [
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
    "प्रयोग", "स्वमूल्यांकन",
]

# ── TOCConfig — single source of truth for all patterns ──────────────────────
# Override any field to customise parsing for a specific book type.
# Pass your instance into robust_transform_logic(raw_pages, config=my_config).

class TOCConfig:
    def __init__(self):
        # Regex patterns
        self.roman_re = _D_ROMAN_RE
        self.indian_id = _D_INDIAN_ID
        self.subtopic_id = _D_SUBTOPIC_ID
        self.roman_subtopic_id = _D_ROMAN_SUBTOPIC_ID
        self.unnumbered_subtopic_id = _D_UNNUMBERED_SUBTOPIC_ID
        self.roman_id = _D_ROMAN_ID
        self.word_ch_id = _D_WORD_CH_ID
        self.standalone_ch = _D_STANDALONE_CH
        self.dash_unit_id = _D_DASH_UNIT_ID
        self.dash_chapter_id = _D_DASH_CHAPTER_ID

        # Page patterns
        self.page_range = _D_PAGE_RANGE
        self.page_single = _D_PAGE_SINGLE

        # Headers
        self.unit_header = _D_UNIT_HEADER
        self.theme_header = _D_THEME_HEADER
        self.subject_header_re = _D_SUBJECT_HEADER_RE

        # Table patterns
        self.table_row_full = _D_TABLE_ROW_FULL
        self.table_row_chapter_only = _D_TABLE_ROW_CHAPTER_ONLY
        self.table_row_unit_only = _D_TABLE_ROW_UNIT_ONLY
        self.table_row_full_nodot = _D_TABLE_ROW_FULL_NODOT
        self.loose_table_row = _D_LOOSE_TABLE_ROW
        self.table_ch_line = _D_TABLE_CH_LINE
        self.table_unit_only = _D_TABLE_UNIT_ONLY

        # Other patterns
        self.backmatter_re = _D_BACKMATTER_RE
        self.ocr_artifact_re = _D_OCR_ARTIFACT_RE

        # Collections (copy to avoid mutation issues)
        self.backmatter_hints = list(_D_BACKMATTER_HINTS)
        self.hindi_known_subjects = set(_HINDI_KNOWN_SUBJECTS)
        self.word_nums = dict(_WORD_NUMS)
        self.hindi_word_nums = dict(_HINDI_WORD_NUMS)

DEFAULT_CONFIG = TOCConfig()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — PURE HELPERS
# Stateless utility functions. Every function that needs a pattern receives
# config explicitly — no global pattern reads anywhere in this section.
# ═══════════════════════════════════════════════════════════════════════════════

def roman_to_int(s: str, config: TOCConfig = DEFAULT_CONFIG) -> Optional[int]:
    """Return integer value of a Roman numeral string, or None if invalid."""
    s = s.strip().upper()
    if not s or not config.roman_re.match(s):
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


def word_to_int(s: str, config: TOCConfig = DEFAULT_CONFIG) -> Optional[int]:
    return config.word_nums.get(s.strip().lower())


def hindi_word_to_int(s: str, config: TOCConfig = DEFAULT_CONFIG) -> Optional[int]:
    return config.hindi_word_nums.get(s.strip())


def _extract_page_range(text: str, config: TOCConfig = DEFAULT_CONFIG):
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
    text = re.sub(r'^\(\s*\d{1,3}\s*\)\s*\d*\s*', '', text).strip()
    text = re.sub(r'^(\d+\s+){1,3}', '', text).strip()
    text = re.sub(r'([\u0900-\u097F])(\d)$', r'\1-\2', text).strip()
    return re.sub(r'\s{2,}', ' ', text).strip()


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags like <b>, </b>, <i>, <math>…</math> etc."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _strip_ocr_artifacts(text: str, config: TOCConfig = DEFAULT_CONFIG) -> str:
    """Remove known OCR math-rendering artifacts (frac12, lone 11, LaTeX cmds)."""
    cleaned = config.ocr_artifact_re.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _jump_ok(ch_int: int, last: int, max_jump: int) -> bool:
    """Return True if the chapter ID is a plausible successor."""
    if ch_int < 1:
        return False
    if last == 0:
        return True
    return 0 < ch_int - last <= max_jump or ch_int == last


def _to_int(token: str, style: str, config: TOCConfig = DEFAULT_CONFIG) -> Optional[int]:
    token = token.strip()
    if style in ("Indian", "dash_chapter"):
        return int(token) if token.isdigit() else None
    if style == "roman":
        return roman_to_int(token, config)
    if style == "word":
        v = word_to_int(token, config)
        if v is not None:
            return v
        h = hindi_word_to_int(token, config)
        if h is not None:
            return h
        return int(token) if token.isdigit() else None
    return None


def _has_chapter_after_unit(text: str) -> bool:
    tokens = text.split()
    if len(tokens) > 3:
        for tok in tokens[2:]:
            if re.match(r'^\d+$', tok):
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PARSERS
# Line pre-processing, single-line parsing, and the table-TOC parser.
# Every function receives config and uses config.pattern — no global reads.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Line pre-processing ───────────────────────────────────────────────────────

def _merge_floating_page_numbers(lines: list, config: TOCConfig = DEFAULT_CONFIG) -> list:
    """
    Two jobs in one pass: attach orphaned page numbers and orphaned chapter-ID
    tokens to their neighbours.
    """
    # Pass 1: merge orphan "N." forward onto the next line
    pre = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.fullmatch(r'\d{1,3}\.', stripped) and i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            if not re.match(r'^\d+\.?\s', next_stripped):
                merged_fwd = stripped + " " + next_stripped
                pre.append(merged_fwd)
                print(f"      🔗 Merged orphan ID forward: [{stripped}] + [{next_stripped}]")
                i += 2
                continue
        pre.append(lines[i])
        i += 1

    # Pass 2: merge orphan bare numbers/ranges backward onto previous line
    merged = []
    for line in pre:
        stripped = line.strip()
        is_num = re.fullmatch(
            r'\d{1,4}(\s*(?:-|–|—|to)\s*\d{1,4})?', stripped, re.IGNORECASE
        )
        if is_num and merged and merged[-1].strip():
            merged[-1] = merged[-1].strip() + " " + stripped
        else:
            merged.append(line)
    return merged


def _is_continuation_line(text: str, config: TOCConfig = DEFAULT_CONFIG) -> bool:
    if config.word_ch_id.match(text):
        return False
    if config.standalone_ch.match(text):
        return False
    if config.indian_id.match(text):
        return False
    if config.theme_header.match(text):
        return False
    if config.backmatter_re.match(text):
        return False
    if re.fullmatch(r'\d{1,3}\.?', text.strip()):
        return False
    sp, _, _ = _extract_page_range(text, config)
    if sp is not None:
        return False
    if len(text) > 80:
        return False
    if text.isupper() and len(text.split()) <= 3:
        return False
    return True


def _merge_two_line_chapters(lines: list, config: TOCConfig = DEFAULT_CONFIG) -> list:
    merged = []
    i = 0
    while i < len(lines):
        current_raw   = lines[i].strip()
        current_clean = _strip_html(current_raw)

        if config.standalone_ch.match(current_clean) and i + 1 < len(lines):
            next_raw   = lines[i + 1].strip()
            next_clean = _strip_html(next_raw)
            if not config.standalone_ch.match(next_clean):
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

        if merged and _is_continuation_line(current_clean, config):
            prev_sp, prev_ep, _ = _extract_page_range(merged[-1], config)
            if prev_sp is None:
                merged[-1] = merged[-1].strip() + " " + current_clean
                print(f"      🔗 Appended continuation: [{current_clean}] → merged into previous")
            else:
                print(f"      ⏭  Skipped orphan continuation: [{current_clean}]")
            i += 1
            continue

        merged.append(current_raw)
        i += 1
    return merged


# ── ID-style detection ────────────────────────────────────────────────────────

def _detect_id_style(lines: list, config: TOCConfig = DEFAULT_CONFIG) -> str:
    """
    Vote on the predominant chapter-ID style.
    Returns: 'Indian' | 'roman' | 'word' | 'dash_chapter'
    """
    votes = {"Indian": 0, "roman": 0, "word": 0, "dash_chapter": 0}
    for line in lines:
        line = _strip_html(line.strip())
        if re.fullmatch(r'\d{1,4}(\s*[-–—]\s*\d{1,4})?', line):
            continue
        if config.dash_chapter_id.match(line) or config.dash_unit_id.match(line):
            votes["dash_chapter"] += 1
            continue
        if config.subtopic_id.match(line) or config.indian_id.match(line):
            votes["Indian"] += 1
        elif config.word_ch_id.match(line):
            votes["word"] += 1
        elif config.roman_id.match(line):
            tok = line.split()[0].rstrip(".")
            if roman_to_int(tok, config) is not None:
                votes["roman"] += 1
    if votes["dash_chapter"] > max(votes["Indian"], votes["roman"], votes["word"]):
        return "dash_chapter"
    del votes["dash_chapter"]
    return max(votes, key=lambda k: (votes[k], k == "Indian"))


# ── Single-line parser ────────────────────────────────────────────────────────

def _parse_line(
    cleaned: str,
    id_style: str,
    last_chapter_int: int,
    max_jump: int,
    config: TOCConfig = DEFAULT_CONFIG,
) -> Optional[tuple]:
    """
    Try to parse a single cleaned line into
    (ch_int, ch_name, start_p, end_p, is_subtopic, raw_subtopic_id).
    Returns None if the line does not match any known pattern.
    """
    # Dash-style: "Chapter-03 Name"
    if id_style == "dash_chapter":
        dash_ch_m = config.dash_chapter_id.match(cleaned)
        if dash_ch_m:
            ch_int = int(dash_ch_m.group(1))
            if not _jump_ok(ch_int, last_chapter_int, max_jump):
                return None
            rest = cleaned[dash_ch_m.end():]
            start_p, end_p, name_raw = _extract_page_range(rest, config)
            name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
            if not name:
                return None
            return (ch_int, name, start_p, end_p, False, None)
        if config.dash_unit_id.match(cleaned):
            return None

    # Guard: reject bare numbers / page ranges
    if re.fullmatch(r'\d{1,4}(\s*[-–—to]\s*\d{1,4})?', cleaned.strip()):
        return None

    # 0. Roman subtopic: "I.1" or "II.3"
    rom_sub_m = config.roman_subtopic_id.match(cleaned)
    if rom_sub_m:
        parent_id  = roman_to_int(rom_sub_m.group(1), config) or 0
        sub_id_str = rom_sub_m.group(1) + "." + rom_sub_m.group(2)
        rest = cleaned[rom_sub_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest, config)
        name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
        if not name:
            return None
        return (parent_id, name, start_p, end_p, True, sub_id_str)

    # 0b. Unnumbered subtopic: "(a)" or "a."
    unnum_m = config.unnumbered_subtopic_id.match(cleaned) if id_style != "roman" else None
    if unnum_m:
        label   = (unnum_m.group(1) or unnum_m.group(2)).lower()
        sub_int = ord(label) - ord('a') + 1
        rest = cleaned[unnum_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest, config)
        name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
        if not name:
            return None
        return (sub_int, name, start_p, end_p, True, label)

    # 1. Subtopic: "1.1" or "1.1.2"
    sub_m = config.subtopic_id.match(cleaned)
    if sub_m:
        parent_id  = int(sub_m.group(1))
        sub_id_str = sub_m.group(1) + "." + sub_m.group(2)
        if sub_m.group(3):
            sub_id_str += "." + sub_m.group(3)
        rest = cleaned[sub_m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest, config)
        name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (parent_id, name, start_p, end_p, True, sub_id_str)

    # 2. Word chapter: "Chapter 1  …" or "Chapter1  …"
    word_m = config.word_ch_id.match(cleaned)
    if word_m:
        num_tok = word_m.group(1)
        ch_int  = (int(num_tok) if num_tok.isdigit()
                   else word_to_int(num_tok, config) or hindi_word_to_int(num_tok, config))
        if ch_int is not None and _jump_ok(ch_int, last_chapter_int, max_jump):
            rest = cleaned[word_m.end():].strip()
            start_p, end_p, name_raw = _extract_page_range(rest, config)
            name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
            name = re.sub(r"^\d{1,3}\s+", "", name).strip()
            name = re.sub(r"^\(\s*\d{1,3}\s*\)\s*\d*\s*", "", name).strip()
            name = re.sub(rf"^{ch_int}\s+", "", name).strip()
            if name:
                return (ch_int, name, start_p, end_p, False, None)

    # 3. Indian chapter: "3 Chapter Name  45"
    if id_style == "Indian":
        m = config.indian_id.match(cleaned)
        if not m:
            return None
        ch_int = int(m.group(1))
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest, config)
        name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    # 4. Roman numeral chapter: "III  Cell Biology  45"
    if id_style == "roman":
        m = config.roman_id.match(cleaned)
        if not m:
            return None
        tok    = m.group(1)
        ch_int = roman_to_int(tok, config)
        if ch_int is None:
            return None
        if not _jump_ok(ch_int, last_chapter_int, max_jump):
            return None
        rest = cleaned[m.end():]
        start_p, end_p, name_raw = _extract_page_range(rest, config)
        name = _safe_sanitize(_strip_trailing_junk(_strip_ocr_artifacts(name_raw, config)))
        if not name:
            print(f"      ⚠️  Dropped (empty name after sanitize): [{cleaned}]")
            return None
        return (ch_int, name, start_p, end_p, False, None)

    return None


# ── Table-style TOC parser ────────────────────────────────────────────────────

def _is_subject_header(text: str, config: TOCConfig = DEFAULT_CONFIG) -> bool:
    """
    Return True if a line is a standalone subject/section header in a
    table-style TOC, e.g. "HISTORY", "CIVICS", "SOCIAL SCIENCE".
    """
    text = text.strip()

    if text.strip().lower() in {"content", "contents", "table of contents"}:
        return False

    if text in config.hindi_known_subjects:
        return True
    if not config.subject_header_re.match(text):
        return False
    if re.search(r'\d', text):
        return False
    sp, _, _ = _extract_page_range(text, config)
    if sp is not None:
        return False
    if len(text.split()) > 6:
        return False
    is_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if not is_devanagari and not text.isupper():
        return False
    return True


def _parse_table_row(cleaned: str, config: TOCConfig = DEFAULT_CONFIG):
    m = config.table_row_full.match(cleaned)
    if m:
        unit_id   = int(m.group(1))
        unit_name = _safe_sanitize(m.group(2))
        ch_id     = int(m.group(3))
        ch_name   = _safe_sanitize(m.group(4))
        start_p, end_p, _ = _extract_page_range(m.group(5), config)
        return dict(unit_id=unit_id, unit_name=unit_name,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    m = config.table_row_full_nodot.match(cleaned)
    if m:
        unit_id   = int(m.group(1))
        unit_name = _safe_sanitize(m.group(2))
        ch_id     = int(m.group(3))
        ch_name   = _safe_sanitize(m.group(4))
        start_p, end_p, _ = _extract_page_range(m.group(5), config)
        return dict(unit_id=unit_id, unit_name=unit_name,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    m = config.table_row_chapter_only.match(cleaned)
    if m:
        ch_id   = int(m.group(1))
        ch_name = _safe_sanitize(m.group(2))
        start_p, end_p, _ = _extract_page_range(m.group(3), config)
        return dict(unit_id=None, unit_name=None,
                    chapter_id=ch_id, chapter_name=ch_name,
                    start_page=start_p, end_page=end_p)

    return None


def _parse_table_toc(all_lines: list, config: TOCConfig = DEFAULT_CONFIG) -> list:
    structured_data   = []
    active_unit_id    = None
    active_unit_name  = None
    unit_counter      = 0
    global_ch_counter = 0

    for raw_line in all_lines:
        cleaned = raw_line.strip()
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'\.{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        if not cleaned or len(cleaned) < 4:
            continue

        # Subject header
        if _is_subject_header(cleaned, config):
            unit_counter    += 1
            active_unit_id   = unit_counter
            active_unit_name = cleaned
            print(f"      📦 Subject: {active_unit_id} – {active_unit_name}")
            continue

        # Try full row first (unit + chapter on one line)
        row = _parse_table_row(cleaned, config)
        if row:
            if row["unit_id"] is not None:
                active_unit_id   = row["unit_id"]
                active_unit_name = row["unit_name"]
            else:
                row["unit_id"]   = active_unit_id
                row["unit_name"] = active_unit_name
            global_ch_counter       += 1
            row["global_chapter_id"] = global_ch_counter
            print(f"      ⭐ Ch {row['chapter_id']} (global #{row['global_chapter_id']}) – {row['chapter_name']}")
            structured_data.append(row)
            continue

        # Standalone chapter line "N. Name  start-end"
        ch_m = config.table_ch_line.match(cleaned)
        if ch_m:
            ch_id   = int(ch_m.group(1))
            ch_name = _safe_sanitize(ch_m.group(2))
            start_p, end_p, _ = _extract_page_range(ch_m.group(3), config)
            global_ch_counter += 1
            row = dict(
                unit_id=active_unit_id,
                unit_name=active_unit_name,
                chapter_id=ch_id,
                chapter_name=ch_name,
                start_page=start_p,
                end_page=end_p,
                global_chapter_id=global_ch_counter,
            )
            print(f"      ⭐ Ch {ch_id} (global #{global_ch_counter}) – {ch_name} [Unit: {active_unit_name}]")
            structured_data.append(row)
            continue

        # Unit-only row "N. UnitName" (no page range) → update context
        unit_m = config.table_unit_only.match(cleaned)
        if unit_m:
            uid   = int(unit_m.group(1))
            uname = _safe_sanitize(unit_m.group(2))
            sp, _, _ = _extract_page_range(cleaned, config)
            if sp is None:
                active_unit_id   = uid
                active_unit_name = uname
                print(f"      📦 Unit row: {uid} – {uname}")

    return structured_data


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — ENTRY POINT
# robust_transform_logic() is the single method that drives the full pipeline.
# It receives config and passes it to every function it calls.
# No pattern is read directly here — all access is via config.
# ═══════════════════════════════════════════════════════════════════════════════

def robust_transform_logic(
    self,
    raw_pages: list,
    config: TOCConfig = DEFAULT_CONFIG,
) -> list:
    """
    Main entry point. Converts raw OCR page lines into a structured JSON list
    of chapter/subtopic entries.

    Pipeline:
        1. Collect all lines across pages
        2. Pre-process: merge floating page numbers & split chapter lines
        3. Detect predominant chapter-ID style (Indian / roman / word / dash)
        4. Detect table-style TOC and delegate if found
        5. Parse each line into a structured entry
        6. Back-fill missing end pages

    To customise patterns for a specific book:
        my_config = TOCConfig(word_ch_id=re.compile(r"my_pattern"))
        processor.transform_logic(raw_pages, config=my_config)
    """
    print("🧠 [TOC_TRANSFORM] Converting lines to structured JSON (ROBUST MODE)…")

    # ── 1. Collect all lines across pages ────────────────────────────────────
    all_lines = []
    for page in raw_pages:
        lines  = page.get("lines", [])
        merged = _merge_floating_page_numbers(lines, config)
        merged = _merge_two_line_chapters(merged, config)
        all_lines.extend(merged)

    # ── 2. Detect dominant ID style ──────────────────────────────────────────
    id_style = _detect_id_style(all_lines, config)
    print(f"      📐 Detected chapter-ID style: {id_style.upper()}")

    # ── 3. Detect table-style TOC ─────────────────────────────────────────────
    table_hits = sum(
        1 for l in all_lines
        if (config.table_row_full.match(l.strip())
            or config.table_row_chapter_only.match(l.strip())
            or config.loose_table_row.match(l.strip()))
    )
    print(f"      📊 table_hits = {table_hits}")
    if table_hits >= 3:
        print(f"      📊 Table-style TOC detected ({table_hits} matching rows) "
              f"— switching to table parser")
        return _parse_table_toc(all_lines, config)

    # ── 4. Parse lines ────────────────────────────────────────────────────────
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

        # UNIT-N header in dash_chapter mode
        if id_style == "dash_chapter":
            dash_unit_m = config.dash_unit_id.match(cleaned)
            if dash_unit_m:
                uid_int = int(dash_unit_m.group(1))
                rest = cleaned[dash_unit_m.end():]
                _, _, unit_name_raw = _extract_page_range(rest, config)
                active_unit_id   = uid_int
                active_unit_name = (_safe_sanitize(_strip_ocr_artifacts(unit_name_raw, config))
                                    or f"Unit {uid_int}")
                print(f"      📦 Unit : {active_unit_id} – {active_unit_name}")
                continue

        # Theme header: "Theme A — India and the World…"
        theme_m = config.theme_header.match(cleaned)
        if theme_m:
            active_unit_id   = theme_m.group(1).upper()
            active_unit_name = _safe_sanitize(theme_m.group(2))
            print(f"      📦 Theme: {active_unit_id} – {active_unit_name}")
            continue

        # Unit-header-only lines
        unit_m = config.unit_header.match(cleaned)
        if unit_m and not _has_chapter_after_unit(cleaned):
            uid_raw = unit_m.group(1)
            uid_int = (_to_int(uid_raw, "Indian", config) or
                       _to_int(uid_raw, "roman",  config) or
                       _to_int(uid_raw, "word",   config))
            active_unit_id   = uid_int
            active_unit_name = _safe_sanitize(unit_m.group(2) or "")
            print(f"      📦 Unit: {active_unit_id} – {active_unit_name}")
            continue

        # Attempt to parse as a structured entry
        entry = _parse_line(cleaned, id_style, last_chapter_int,
                            self.max_chapter_jump, config)

        # Fallback: horizontal subtopics (comma-separated on one line)
        if entry is None and last_chapter_int > 0 and ',' in cleaned:
            parts = [p.strip() for p in cleaned.split(',')]
            if len(parts) >= 3:
                print(f"      📋 Horizontal subtopics detected for Ch {last_chapter_int}")
                for part in parts:
                    part = part.strip().rstrip('.')
                    if not part:
                        continue
                    start_p, end_p, name_raw = _extract_page_range(part, config)
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

        # Fallback: unnumbered subtopic / back-matter detection
        if entry is None and last_chapter_int > 0:
            is_backmatter = (
                config.backmatter_re.match(cleaned)
                or any(word in cleaned.lower() for word in config.backmatter_hints)
            )
            if is_backmatter:
                sp, ep, _ = _extract_page_range(cleaned, config)
                entry_dict = {
                    "unit_id":      None,
                    "unit_name":    None,
                    "chapter_id":   None,
                    "chapter_name": (_safe_sanitize(cleaned[:cleaned.rfind(str(sp))].strip())
                                     if sp else _safe_sanitize(cleaned)),
                    "start_page":   sp,
                    "end_page":     ep,
                    "is_appendix":  True,
                }
                print(f"      📎 Back-matter: {entry_dict['chapter_name']} [Page: {sp}]")
                structured_data.append(entry_dict)
                continue

            # Regular unnumbered subtopic
            start_p, end_p, name_raw = _extract_page_range(cleaned, config)
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

    # ── 5. Back-fill missing end pages ───────────────────────────────────────
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
