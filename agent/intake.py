import re
import unicodedata
from difflib import SequenceMatcher

from indic_transliteration import sanscript

from agent.numwords import NUMWORDS, evaluate
from db import get_db

STOP = set("""ko ka ki ke se ne reminder remind bhejo bhej
send message msg sms call karo kar de rs rupees rupee rupaye rupay rupya inr for to of hai baki
baaki udhaar udhar ye the a please pls aur and tak paisa paise wapas mangna maango maang yaad
dilao dilana dila को का की के से रिमाइंडर भेजो रुपये रुपए""".split())
HONORIFICS = set("ji bhai sahab saab sahib madam mam sir ben जी भाई साहब साहेब मैडम बेन".split())

NEW_BELOW = 0.7  # best name score under this = nobody close, so a new person; at/above it we return candidates instead
NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize_digits(text):
    """Devanagari (and any Unicode) digits -> ASCII, 1,200 -> 1200."""
    text = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def tokens(text):
    return re.findall(r"\d+(?:\.\d+)?|[^\s\d₹.,!?;:()\"'\-/]+", normalize_digits(text).lower())


def parse_amount(text, trace=None):
    """The amount in the text: digits ('1200', '१२००'), spoken Hindi ('barah sau', 'बारह सौ') or a mix ('12 sau').
    Pass a list as trace to collect every step; see agent.numwords.evaluate for the rules."""
    return evaluate(tokens(text), trace)


def amount_trace(text):
    """Everything the amount parser saw and did, for debugging a mis-heard or mis-parsed amount."""
    steps = []
    amount = parse_amount(text, steps)
    return {"raw": text, "normalized": normalize_digits(text), "tokens": tokens(text), "steps": steps, "amount": amount}


def to_latin(word):
    """Devanagari -> ITRANS, lowercased; Latin passes through unchanged."""
    return sanscript.transliterate(word, sanscript.DEVANAGARI, sanscript.ITRANS).lower()


def _spoken_name(raw, latin):
    """Title-cased Latin name from the spoken words; Devanagari is transliterated (dropping ITRANS's trailing schwa)."""
    out = []
    for r, l in zip(raw, latin):
        if r != l and "\u0915" <= r[-1] <= "\u0939" and l.endswith("a"):
            l = l[:-1]
        out.append(l.title())
    return " ".join(out)


def _score(words, parts, full):
    sim = lambda a, b: SequenceMatcher(None, a, b).ratio()
    # rstrip("a"): ITRANS keeps the inherent schwa (रमेश -> ramesha)
    s = max((max(sim(w, p), sim(w.rstrip("a"), p)) for w in words for p in parts), default=0)
    if len(words) > 1:
        s = max(s, sim(" ".join(words), full))
    return s


def parse_intake(text):
    """-> {contact_id, amount, confidence, candidates, debt_id, new_name}. contact_id is None unless one name clearly wins.
    debt_id is an existing open/promised debt for that contact with the same amount, else None."""
    amount = parse_amount(text)
    raw = [t for t in tokens(text)
           if not NUM.fullmatch(t) and t not in STOP and t not in NUMWORDS and len(t) > 1]
    latin = [to_latin(w) for w in raw]
    passes = [raw, latin,  # raw, transliterated, transliterated + honorifics stripped
              [l for r, l in zip(raw, latin) if r not in HONORIFICS and l not in HONORIFICS]]
    db = get_db()
    contacts = db.execute("SELECT id, name FROM contacts").fetchall()
    scored = []
    for c in contacts:
        full = c["name"].lower()
        scored.append((max(_score(w, full.split(), full) for w in passes), c))
    scored.sort(key=lambda x: -x[0])
    top = scored[0][0] if scored else 0
    runner_up = scored[1][0] if len(scored) > 1 else 0
    confident = top >= 0.8 and top - runner_up >= 0.1
    contact_id = scored[0][1]["id"] if confident else None
    pairs = [(r, l) for r, l in zip(raw, latin) if r not in HONORIFICS and l not in HONORIFICS]
    new_name = None  # nobody close, an amount was given, and it looks like a name (1-3 words): a new debtor
    if not confident and amount is not None and 0 < len(pairs) <= 3 and top < NEW_BELOW:
        new_name = _spoken_name(*zip(*pairs))
    existing = None
    if contact_id and amount is not None:
        existing = db.execute("SELECT id FROM debts WHERE contact_id=? AND amount=? AND status IN ('open','promised')"
                              " ORDER BY id LIMIT 1", (contact_id, amount)).fetchone()
    db.close()
    return {
        "contact_id": contact_id,
        "amount": amount,
        "confidence": round(top, 2),
        "debt_id": existing["id"] if existing else None,
        "new_name": new_name,
        "candidates": [] if confident else
        [{"contact_id": c["id"], "name": c["name"], "score": round(s, 2)} for s, c in scored[:3] if s >= 0.5],
    }
