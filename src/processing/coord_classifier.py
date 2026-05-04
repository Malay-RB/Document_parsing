import re
from typing import Optional, Callable

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _log_section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

def _log_skip(reason: str, text: str):
    print(f"  ✗  Skip ({reason}): {text!r}")

def _log_unit(uid, name, page_range=None):
    pg = f"  [{page_range}]" if page_range else ""
    print(f"  📦 UNIT {uid}: {name}{pg}")

def _log_chapter(ch_id, name, start_p, end_p):
    pg = f"{start_p}–{end_p}" if end_p else str(start_p) if start_p else "?"
    print(f"  ⭐ Ch {ch_id:>2}: {name}  [{pg}]")

def _log_subtopic(sub_id, name, start_p):
    pg = str(start_p) if start_p else "?"
    print(f"       ↳ {sub_id}: {name}  [p.{pg}]")

def _log_backmatter(name, start_p):
    pg = str(start_p) if start_p else "?"
    print(f"  📎 Back-matter: {name}  [p.{pg}]")


# ─────────────────────────────────────────────────────────────────────────────
# COORDINATE CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def build_level_fn(all_lines: list) -> tuple:

    x_vals = [
        l["x"] for l in all_lines
        if isinstance(l, dict) and l.get("x") is not None
    ]

    print("\n  📍 RAW COORDINATES:")
    for l in all_lines:
        if isinstance(l, dict) and l.get("x") is not None:
            print(f"      x={l['x']:.1f}  →  {l['text'][:60]!r}")

    if not x_vals:
        return lambda x: None, 0

    min_x = min(x_vals)
    max_x = max(x_vals)
    span  = max_x - min_x if max_x != min_x else 1

    normed = sorted(set((x - min_x) / span for x in x_vals))
    diffs  = [normed[i] - normed[i - 1] for i in range(1, len(normed))]

    # 🔧 Slightly relaxed threshold (more robust, no behavior break)
    threshold = max(0.05, min(0.15, (sum(diffs) / len(diffs)) * 1.5)) if diffs else 0.08

    # ── Build clusters ─────────────────────────────────────────────
    raw_clusters: list[list[float]] = []
    for xn in normed:
        if not raw_clusters or xn - raw_clusters[-1][-1] > threshold:
            raw_clusters.append([xn])
        else:
            raw_clusters[-1].append(xn)

    # ── Noise filtering ────────────────────────────────────────────
    total_pts = len(x_vals)
    min_pts   = max(3, int(total_pts * 0.15))

    real_clusters = [c for c in raw_clusters if len(c) >= min_pts]

    if not real_clusters:
        real_clusters = [max(raw_clusters, key=len)]

    centers = [sum(c) / len(c) for c in real_clusters]
    num_real = len(centers)

    # ── Role mapping ───────────────────────────────────────────────
    # 🔧 FIX: single cluster → unknown (prevents wrong unit detection)
    if num_real == 1:
        role_map = {0: 'unknown'}
    elif num_real == 2:
        role_map = {0: 'unit', 1: 'chapter'}
    else:
        role_map = {0: 'unit', 1: 'chapter'}
        for i in range(2, num_real):
            role_map[i] = 'subtopic'

    # ── Logging ────────────────────────────────────────────────────
    _log_section(
        f"Coordinate clusters  (threshold={threshold:.3f}  "
        f"min_pts={min_pts}  raw={len(raw_clusters)}  kept={num_real})\n"
        + "\n".join(
            f"    [{role_map.get(i, 'unknown'):8s}] center={c:.3f}  "
            f"[{min(cl):.3f}–{max(cl):.3f}]  ({len(cl)} pts)"
            for i, (c, cl) in enumerate(zip(centers, real_clusters))
        )
    )

    # ── Level function ─────────────────────────────────────────────
    def level_fn(x: float | None) -> str | None:
        if x is None:
            return None

        xn = (x - min_x) / span
        dists = [abs(xn - c) for c in centers]

        min_dist = min(dists)

        # 🔧 Safety: ignore unreliable assignments
        if min_dist > 0.2:
            return None

        return role_map.get(dists.index(min_dist), None)

    return level_fn, num_real


# ─────────────────────────────────────────────────────────────────────────────
# LINE CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

# Back-matter keywords — lines matching these are never chapters/subtopics
_BACKMATTER_RE = re.compile(
    r"^(?:glossary|answers?\s*key?|index|foreword|appendix|images?\s+and|bibliography|"
    r"acknowledgements?|about\s+the|method\s+of|note\s+to|letter\s+to|"
    r"your\s+journey|preface|introduction|contents?|"
    r"शब्दावली|उत्तर|अनुक्रमणिका|प्रस्तावना|परिशिष्ट|ग्रंथसूची|"
    r"आमुख|भूमिका|टिप्पणी|पत्र|"
    r"अभ्यास|प्रश्नावली|पुनरावृत्ति|सारांश|मानचित्र|"
    r"परियोजना|क्रियाकलाप|विषय-सूची)",
    re.IGNORECASE | re.UNICODE,
)

BACKMATTER_HINTS = [
    "exercise", "summary", "map", "project", "activity",
    "question", "questions", "worksheet", "test",
    "assessment", "practice", "appendix", "glossary",
    "bibliography", "index", "answers", "answer key", "mcq",
    "self assessment", "competency", "hots", "model paper",
    "sample paper", "revision test", "lab manual",
    "अभ्यास", "प्रश्न", "प्रश्नावली", "पुनरावृत्ति", "सारांश",
    "मानचित्र", "परियोजना", "क्रियाकलाप", "कार्यपत्रक",
]


def classify_line(cleaned: str, role: str | None) -> str:
    if not cleaned or len(cleaned) < 2:
        return 'skip'
    if (_BACKMATTER_RE.match(cleaned)
            or any(w in cleaned.lower() for w in BACKMATTER_HINTS)):
        return 'backmatter'
    if re.fullmatch(r'\d{1,4}(\s*[-–—to]\s*\d{1,4})?', cleaned.strip(), re.IGNORECASE):
        return 'skip'
    if role is None:
        return 'unknown'
    return role   # already 'unit' | 'chapter' | 'subtopic'