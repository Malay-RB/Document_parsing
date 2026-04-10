"""
page_number_patterns.py
─────────────────────────────────────────────────────────────
Centralised pattern library for printed page-number detection.

Used by:
  • page_strategy._extract_page_val()   → replace the leading ^(\d+) grab
  • SemanticClassifier.classify()       → replace the len<15 + any-digit block

Quick usage:
    from page_number_patterns import PageNumberPatterns
    _PNP = PageNumberPatterns()          # module-level singleton

    val = _PNP.extract(text)             # returns int or None
"""  # noqa: W605

import re
from typing import Optional


# ── 1. NOISE PATTERNS ────────────────────────────────────────────────────────
# Checked FIRST. Any match → immediately return None.

NOISE_PATTERNS = [
    # Figure / Table / Exercise / Q references
    re.compile(
        r'^\s*(?:fig(?:ure)?|table|ex(?:ercise)?|example|q(?:uestion)?'
        r'|ans(?:wer)?|activity|step|problem|no\.?)\s*[\.\:]?\s*\d+',
        re.IGNORECASE
    ),
    # Class / Grade / Standard labels  "Class 6",  "Grade VIII"
    re.compile(r'(?:class|grade|std\.?|standard)\s*[-–]?\s*(?:\d+|[ivxlIVXL]+)', re.IGNORECASE),


    # Chapter / Unit / Section headings
    re.compile(
        r'^\s*(?:chapter|unit|section|part|module|lesson|topic)\s*[-–]?\s*(?:\d+|[ivxlIVXL]+)',
        re.IGNORECASE
    ),
    # ISBN / ISSN
    re.compile(r'\b(?:ISBN|ISSN)\b', re.IGNORECASE),
    # Year ranges  "2020-21",  "2023–2024"
    re.compile(r'\b(19|20)\d{2}\s*[-–]\s*(?:\d{2}|\d{4})\b'),
    # Decimals / fractions
    re.compile(r'\b\d+\.\d+\b'),
    re.compile(r'\b\d+\s*/\s*\d+\b'),
    # Version / edition  "v2.0",  "2nd Edition"
    re.compile(r'\b(?:v\d|ver\.?\s*\d|ed(?:ition)?\.?\s*\d|\d+(?:st|nd|rd|th)\s+ed)', re.IGNORECASE),
    # Price / currency
    re.compile(r'[\$₹£€]\s*\d+|\b(?:Rs\.?|INR)\s*\d+', re.IGNORECASE),
    # Phone / PIN  (6+ consecutive digits)
    re.compile(r'\b\d{6,}\b'),
    # Roman numerals too long to be page numbers  "XXXVIII"
    re.compile(r'^\s*[IVXLCDM]{5,}\s*$'),
    # Answer-key style  "1. (b)",  "2. True"
    re.compile(r'^\s*\d+\s*[\.\)]\s*(?:[a-dA-D]\b|true|false)', re.IGNORECASE),
    # Body-text list item  "1. Some text follows"
    re.compile(r'^\s*\d{1,3}\s*\.\s+\S'),
    # Page-range references  "pp. 34"
    re.compile(r'\bpp?\.\s*\d+', re.IGNORECASE),
]


# ── 2. DEFINITE PATTERNS ──────────────────────────────────────────────────────
# Each tuple: (regex, capture_group, base)
# base = 10 → Arabic, base = "roman" → convert via helper

DEFINITE_PATTERNS = [
    # Bare integer  "142",  "  7  "
    (re.compile(r'^\s*(\d{1,4})\s*$'), 1, 10),
    # Dash-wrapped  "– 45 –",  "- 45 -"
    (re.compile(r'^[\s\-–—]+(\d{1,4})[\s\-–—]+$'), 1, 10),
    # Pipe-wrapped  "| 45 |"
    (re.compile(r'^\s*\|\s*(\d{1,4})\s*\|\s*$'), 1, 10),
    # Dot/bullet-wrapped  ". 45 ."
    (re.compile(r'^\s*[·•\.]\s*(\d{1,4})\s*[·•\.]\s*$'), 1, 10),
    # Bracket-wrapped  "[45]",  "(45)"
    (re.compile(r'^\s*[\[\(]\s*(\d{1,4})\s*[\]\)]\s*$'), 1, 10),
    # "Page 45",  "Pg. 12",  "पृष्ठ 45"
    (re.compile(r'^\s*(?:page|pg\.?|p\.?|पृष्ठ|पृ\.?)\s*(\d{1,4})\s*$', re.IGNORECASE), 1, 10),
    # Roman numerals for front-matter  "iv",  "xii"
    (re.compile(r'^\s*((?:x{0,3})(?:ix|iv|v?i{0,3}))\s*$', re.IGNORECASE), 1, 'roman'),
]


# ── 3. CONTEXT STRIP TOKENS ───────────────────────────────────────────────────
# Stripped from text before retrying DEFINITE patterns.
# Handles: "NCERT 142",  "Mathematics 45",  "Class 6 | 78"

STRIP_TOKENS = [
    re.compile(
        r'\b(?:ncert|cbse|icse|scert|rbse|cgbse|mpbse|state\s+board)\b', re.IGNORECASE
    ),
    re.compile(
        r'\b(?:mathematics|maths?|science|physics|chemistry|biology|english'
        r'|hindi|history|geography|civics|economics|sanskrit|evs|sst'
        r'|social\s+science|s\.?\s*s\.?\s*t\.?)\b',
        re.IGNORECASE
    ),
    re.compile(r'\b(?:class|grade|std\.?)\s*[-–]?\s*(?:\d+|[ivxlIVXL]+)\b', re.IGNORECASE),
    re.compile(r'\bby\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'),
    re.compile(r'[|•·©®™]+'),
    re.compile(r'^[\s,;\-–—]+|[\s,;\-–—]+$'),
]


# ── 4. ROMAN NUMERAL HELPER ───────────────────────────────────────────────────

_ROMAN_VALUES = [
    ('m',1000),('cm',900),('d',500),('cd',400),('c',100),('xc',90),
    ('l',50),  ('xl',40), ('x',10), ('ix',9),  ('v',5),  ('iv',4), ('i',1),
]

def _roman_to_int(s: str) -> Optional[int]:
    s = s.lower().strip()
    result, i = 0, 0
    for sym, val in _ROMAN_VALUES:
        while s[i:i+len(sym)] == sym:
            result += val
            i += len(sym)
    return result if i == len(s) and result > 0 else None


# ── 5. MAIN CLASS ─────────────────────────────────────────────────────────────

class PageNumberPatterns:
    MIN_PAGE = 1
    MAX_PAGE = 2000

    def extract(self, text: str) -> Optional[int]:
        """Returns an integer page number, or None."""
        if not text:
            return None

        norm = self._normalise(text)

        if self._is_noise(norm):                    # Step 1: noise guard
            return None

        val = self._match_definite(norm)            # Step 2: definite match
        if val is not None:
            return val

        stripped = self._strip_context(norm)        # Step 3: strip metadata, retry
        if stripped and stripped != norm:
            if not self._is_noise(stripped):
                val = self._match_definite(stripped)
                if val is not None:
                    return val

        return self._fallback_isolated(norm)        # Step 4: last resort
 
    def extract_with_confidence(self, text: str) -> tuple[Optional[int], str]:
        """
        Returns (page_number, confidence) where confidence is:
        'HIGH'   - bare number, no stripping needed
        'MEDIUM' - number found after stripping context tokens
        'LOW'    - fallback isolated match
        'NONE'   - no page number found
        """
        if not text:
            return None, 'NONE'
        norm = self._normalise(text)
        if self._is_noise(norm):
            return None, 'NONE'
        val = self._match_definite(norm)
        if val is not None:
            return val, 'HIGH'
        stripped = self._strip_context(norm)
        if stripped and stripped != norm:
            if not self._is_noise(stripped):
                val = self._match_definite(stripped)
                if val is not None:
                    return val, 'MEDIUM'  # ← "Science, Class-10" lands here
        val = self._fallback_isolated(norm)
        if val is not None:
            return val, 'LOW'
        return None, 'NONE'    
    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(text: str) -> str:
        text = re.sub(r'<.*?>', '', text)
        text = ''.join(ch for ch in text if ch.isprintable())
        return re.sub(r'\s+', ' ', text).strip().strip('\'"')

    def _is_noise(self, text: str) -> bool:
        return any(p.search(text) for p in NOISE_PATTERNS)

    def _match_definite(self, text: str) -> Optional[int]:
        for pattern, group, base in DEFINITE_PATTERNS:
            m = pattern.match(text)
            if not m:
                continue
            raw = m.group(group)
            val = _roman_to_int(raw) if base == 'roman' else int(raw)
            if val and self.MIN_PAGE <= val <= self.MAX_PAGE:
                return val
        return None

    @staticmethod
    def _strip_context(text: str) -> str:
        for pat in STRIP_TOKENS:
            text = pat.sub('', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _fallback_isolated(self, text: str) -> Optional[int]:
        """Short text, exactly one number, no letter-digit adjacency."""
        if len(text) > 40 or re.search(r'[A-Za-z]\d|\d[A-Za-z]', text):
            return None
        numbers = re.findall(r'\b(\d{1,4})\b', text)
        if len(numbers) == 1:
            val = int(numbers[0])
            if self.MIN_PAGE <= val <= self.MAX_PAGE:
                return val
        return None


# ── 6. SELF-TEST ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pnp = PageNumberPatterns()
    cases = [
        ("142",               142),   ("  7  ",             7),
        ("– 45 –",            45),    ("| 45 |",            45),
        ("[45]",              45),    ("(45)",              45),
        ("Page 45",           45),    ("pg. 12",            12),
        ("iv",                4),     ("xii",               12),
        ("NCERT  142",        142),   ("Mathematics 45",    45),
        ("Class 6  |  78",    78),    ("SST  | 33 |",       33),
        ("Fig. 3",            None),  ("Figure 3.2",        None),
        ("Table 4",           None),  ("Ex. 5",             None),
        ("Class 6",           None),  ("Grade 8",           None),
        ("2020-21",           None),  ("3.14",              None),
        ("Chapter 3",         None),  ("Unit 2",            None),
        ("1. Some text here", None),  ("ISBN 978-0-12",     None),
        ("₹ 45",              None),  ("1234567",           None),
    ]
    passed = failed = 0
    for text, expected in cases:
        result = pnp.extract(text)
        ok = result == expected
        passed += ok; failed += not ok
        print(f"{'✅' if ok else '❌'} extract({text!r:35s}) = {str(result):>6}   {'(expected ' + str(expected) + ')' if not ok else ''}")
    print(f"\n{'━'*55}\n  {passed} passed   {failed} failed   / {len(cases)}")