import re
import unicodedata
from difflib import SequenceMatcher

from indic_transliteration import sanscript

from db import get_db

UNITS = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
         "chah": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "dedh": 1.5, "dhai": 2.5,
         "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7,
         "आठ": 8, "नौ": 9, "दस": 10, "डेढ़": 1.5, "ढाई": 2.5}
MULT = {"sau": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000, "k": 1000,
        "lakh": 100000, "lac": 100000, "सौ": 100, "हज़ार": 1000, "हजार": 1000, "लाख": 100000}
STOP = set("""ko ka ki ke se ne reminder remind bhejo bhej
send message msg sms call karo kar de rs rupees rupee rupaye rupay rupya inr for to of hai baki
baaki udhaar udhar ye the a please pls aur and tak paisa paise wapas mangna maango maang yaad
dilao dilana dila को का की के से रिमाइंडर भेजो रुपये रुपए""".split())
HONORIFICS = set("ji bhai sahab saab sahib madam mam sir ben जी भाई साहब साहेब मैडम बेन".split())

NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize_digits(text):
    """Devanagari (and any Unicode) digits -> ASCII, 1,200 -> 1200."""
    text = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def tokens(text):
    return re.findall(r"\d+(?:\.\d+)?|[^\s\d₹.,!?;:()\"'\-/]+", normalize_digits(text).lower())


def parse_amount(text):
    """First run of digits / number words ('paanch sau', '2 hazaar', '1.5k'); a bare unit word is not an amount."""
    out, total, cur, sig = [], 0.0, None, False

    def end_run():
        nonlocal total, cur, sig
        if sig:
            out.append(total + (cur or 0))
        total, cur, sig = 0.0, None, False  # always reset, so a stray unit word can't leak into a later run

    for t in tokens(text):
        if NUM.fullmatch(t):
            end_run()  # two numbers in a row are separate runs
            cur, sig = float(t), True
        elif t in UNITS:
            if sig:
                end_run()
            cur = UNITS[t]
        elif t in MULT and (cur is not None or t != "k"):
            total += (cur if cur is not None else 1) * MULT[t]
            cur, sig = None, True
        else:
            end_run()
    end_run()
    if not out:
        return None
    return int(out[0]) if out[0] == int(out[0]) else out[0]


def to_latin(word):
    """Devanagari -> ITRANS, lowercased; Latin passes through unchanged."""
    return sanscript.transliterate(word, sanscript.DEVANAGARI, sanscript.ITRANS).lower()


def _score(words, parts, full):
    sim = lambda a, b: SequenceMatcher(None, a, b).ratio()
    # rstrip("a"): ITRANS keeps the inherent schwa (रमेश -> ramesha)
    s = max((max(sim(w, p), sim(w.rstrip("a"), p)) for w in words for p in parts), default=0)
    if len(words) > 1:
        s = max(s, sim(" ".join(words), full))
    return s


def parse_intake(text):
    """-> {contact_id, amount, confidence, candidates, debt_id}. contact_id is None unless one name clearly wins.
    debt_id is an existing open/promised debt for that contact with the same amount, else None."""
    amount = parse_amount(text)
    raw = [t for t in tokens(text)
           if not NUM.fullmatch(t) and t not in STOP and t not in UNITS and t not in MULT and len(t) > 1]
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
        "candidates": [] if confident else
        [{"contact_id": c["id"], "name": c["name"], "score": round(s, 2)} for s, c in scored[:3] if s >= 0.5],
    }
