"""Find the CEO among a call's management speakers.

Evidence, strongest first:
  title    - speaker's title / affiliation says CEO (Fool participant list, HF affiliation)
  intro    - an opening turn introduces "<Name>, (our) ... Chief Executive Officer / CEO"
  roster   - old-style header "Executives: <Name> - ... CEO"
  carry    - same company's previous call named this person CEO and they speak again
"""
import re

CEO_WORDS = r"(?:Chief Executive Officer\b|Chief Executive\b(?!\s+Officer)|CEO\b)"
# capitalised words incl. accented letters (André); a word may not end in "." unless it is a single initial,
# so a match never runs across a sentence end ("... Chief Executive Officer. Jacek Olczak")
_W = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿA-ZÀ-ÖØ-Þ'\-]+"
NAME = r"((?!Officer\b|Chief\b|Executive\b)" + _W + r"(?:\s+(?:[A-Z]\.|" + _W + r")){1,3})"
# "Tim Cook, our CEO" / "Tim Cook, Chairman and Chief Executive Officer"
PAT_AFTER = re.compile(NAME + r",?\s+(?:who is\s+)?(?:our|the|Apple's|\w+'s)?\s*(?:[A-Z][a-z]+(?:,| and| &)?\s+){0,4}" + CEO_WORDS)
# "our CEO, Tim Cook" / "Chief Executive Officer Jamie Dimon"
PAT_BEFORE = re.compile(CEO_WORDS + r"(?:\s+and\s+[A-Z][a-z]+)*,?\s+" + NAME + r"\b(?!\s*[-–])")
NOT_CEO = re.compile(r"(Deputy|Vice|Former|Interim CFO|Financial|Operating|Investment|Technology|Accounting|Risk|Marketing|People|Legal|Commercial|Medical|Scientific|Information|Digital|Strategy)\s+(?:Chief\s+)?(?:Executive )?Officer", re.I)
EXCLUDE_TOKENS = {"Officer", "Chief", "Executive", "Chairman", "President", "Our", "The", "And", "With", "Today", "Joining", "Me"}


def norm(n):
    n = re.sub(r"\[.*?\]|\(.*?\)", "", n or "").strip().lower()
    return re.sub(r"[^a-z ]", "", n)


def last(n):
    p = norm(n).split()
    return p[-1] if p else ""


def is_ceo_title(t):
    if not t:
        return False
    if re.search(r"\bCEO\b|Chief Executive", t, re.I) is None:
        return False
    # "Deputy CEO", "CEO of <segment>" still counts only if not obviously a sub-unit head
    if re.search(r"Deputy|Vice Chair(?!man and CEO)|Former|CEO of [A-Z]", t):
        return False
    return True


NAME_COMMA = re.compile(NAME + r"(?=\s*,)")
FILLER = re.compile(r"[,\s]*(?:(?:our|the|and|&|of|Board|Chairman|Chair|Chairwoman|President|Founder|Co-Founder|Group|Company|Corporation|Inc\.?|Directors|who is|is|[A-Z][A-Za-z]+'s|[A-Z][A-Za-z]+)[,\s]*)*")


def names_from_text(text, company=""):
    out = []
    co = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", company or "")[:2] if w.lower() not in ("the", "inc", "corp", "corporation", "company", "group", "holdings")]
    for m in re.finditer(CEO_WORDS, text):
        tail = text[m.end(): m.end() + 60]
        mo = re.match(r"\s+(?:of|for)\s+(?:the\s+)?([A-Z][\w&'.\- ]{2,40})", tail)
        if mo and not any(w in mo.group(1).lower() for w in co):
            continue
        # name closest before the CEO word, with only title filler in between
        win_start = max(0, m.start() - 110)
        cands = [c for c in NAME_COMMA.finditer(text, win_start, m.start())]
        for c in reversed(cands):
            between = text[c.end(): m.start()]
            if re.search(r"Financial|Operating|Accounting|Technology|Investment|Deputy|Vice|Former|;", between):
                break
            if FILLER.fullmatch(between):
                out.append(c.group(1))
                break
    for m in PAT_BEFORE.finditer(text):
        out.append(m.group(1))
    clean = []
    for n in out:
        toks = [t for t in n.split() if t not in EXCLUDE_TOKENS]
        if len(toks) >= 2:
            clean.append(" ".join(toks))
    return clean


def detect(turns, header_text="", prev_ceo=None, company=""):
    """turns: list of dicts with speaker, role, (title|affiliation), text. Returns (ceo_name, src)."""
    mgmt = {}
    for t in turns:
        if t.get("role") == "management" and t.get("speaker"):
            mgmt.setdefault(last(t["speaker"]), t["speaker"])
    if not mgmt:
        return None, None
    for t in turns:
        if t.get("role") == "management" and is_ceo_title(t.get("title") or t.get("affiliation")):
            return t["speaker"], "title"
    intro = " ".join((t.get("text") or "")[:3000] for t in turns[:6])
    for n in names_from_text(intro, company):
        if last(n) in mgmt:
            return mgmt[last(n)], "intro"
    if header_text:
        m = re.search(r"Executives?\s*[:\n](.{0,1500})", header_text, re.S)
        if m:
            for line in re.split(r"\n|(?<=[a-z])\s{2,}", m.group(1)):
                if re.search(r"\bCEO\b|Chief Executive", line) and not NOT_CEO.search(line):
                    nm = line.split(" - ")[0].split(",")[0].strip()
                    if last(nm) in mgmt:
                        return mgmt[last(nm)], "roster"
    if prev_ceo and last(prev_ceo) in mgmt:
        return mgmt[last(prev_ceo)], "carry"
    return None, None


def apply_current(calls, ceo_name, since):
    """FMP key-executives: current CEO and the date the title started."""
    if not ceo_name:
        return
    if not since:
        others = [c["date"][:10] for c in calls if c["ceo"] and c["ceo_src"] in ("title", "intro", "roster") and last(c["ceo"]) != last(ceo_name)]
        since = max(others) if others else "0000"
    for c in calls:
        if c["ceo"] and c["ceo_src"] in ("title", "intro", "roster"):
            continue
        if c["date"][:10] >= since and last(ceo_name) in c["mgmt"]:
            c["ceo"], c["ceo_src"] = c["mgmt"][last(ceo_name)], "fmp_current"


def propagate(calls):
    """calls: list of dicts (one symbol, sorted by date) with keys date, ceo, ceo_src, mgmt (set of last names -> speaker).
    Fill missing CEOs with a person directly identified as CEO on another call of the same company
    who also speaks on this call; nearest identified call in time wins. src='propagated'."""
    known = [(c["date"], c["ceo"]) for c in calls if c["ceo"] and c["ceo_src"] in ("title", "intro", "roster")]
    if not known:
        return
    for c in calls:
        if c["ceo"]:
            continue
        best = None
        for d, n in known:
            if last(n) in c["mgmt"]:
                gap = abs((_d(d) - _d(c["date"])))
                if best is None or gap < best[0]:
                    best = (gap, c["mgmt"][last(n)])
        if best and best[0] <= 3 * 365:
            c["ceo"], c["ceo_src"] = best[1], "propagated"


def _d(s):
    import datetime as dt
    return dt.date.fromisoformat(s[:10]).toordinal()
