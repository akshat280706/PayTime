"""Spoken Hindi/Hinglish numbers -> a number. Hindi 11-99 are all irregular words, so they are listed, not computed."""
import re

_NUM = re.compile(r"\d+(?:\.\d+)?")

# value: every spelling we expect from speech-to-text, Devanagari and Latin
_WORDS = {
    1: "एक ek", 2: "दो do", 3: "तीन teen", 4: "चार char chaar", 5: "पांच पाँच paanch panch", 6: "छह छः छे chhe chah chhah",
    7: "सात saat sat", 8: "आठ aath ath", 9: "नौ nau", 10: "दस das",
    11: "ग्यारह gyarah gyaarah giyarah", 12: "बारह barah baarah bara", 13: "तेरह terah tera", 14: "चौदह chaudah choudah",
    15: "पंद्रह पन्द्रह pandrah pandra", 16: "सोलह solah sola", 17: "सत्रह satrah satra", 18: "अठारह atharah athaarah athara",
    19: "उन्नीस unnis unnees unis", 20: "बीस bees bis", 21: "इक्कीस ikkis ikkees", 22: "बाईस baais baaees bais",
    23: "तेईस teis teees", 24: "चौबीस chaubis", 25: "पच्चीस pachchis pachis pacchis", 26: "छब्बीस chhabbis",
    27: "सत्ताईस sattais", 28: "अट्ठाईस अठाईस atthais athais", 29: "उनतीस untis", 30: "तीस tees tis",
    31: "इकतीस ikattis", 32: "बत्तीस battis", 33: "तैंतीस taintis", 34: "चौंतीस chauntis", 35: "पैंतीस paintis",
    36: "छत्तीस chhattis", 37: "सैंतीस saintis", 38: "अड़तीस adtis artis", 39: "उनतालीस untalis",
    40: "चालीस chalis chaalis", 41: "इकतालीस iktalis", 42: "बयालीस bayalis", 43: "तैंतालीस taintalis",
    44: "चौवालीस chauvalis chavalis", 45: "पैंतालीस paintalis", 46: "छियालीस chhiyalis", 47: "सैंतालीस saintalis",
    48: "अड़तालीस adtalis", 49: "उनचास unchas", 50: "पचास pachas pachaas", 51: "इक्यावन ikyavan",
    52: "बावन bawan baavan", 53: "तिरपन tirpan tirepan", 54: "चौवन chauwan chauvan", 55: "पचपन pachpan",
    56: "छप्पन chhappan", 57: "सत्तावन sattawan", 58: "अट्ठावन अठावन atthawan", 59: "उनसठ unsath",
    60: "साठ saath sath", 61: "इकसठ iksath", 62: "बासठ baasath basath", 63: "तिरसठ tirsath", 64: "चौंसठ chaunsath",
    65: "पैंसठ painsath", 66: "छियासठ chhiyasath", 67: "सड़सठ sadsath", 68: "अड़सठ adsath", 69: "उनहत्तर unhattar",
    70: "सत्तर sattar", 71: "इकहत्तर ikhattar", 72: "बहत्तर bahattar", 73: "तिहत्तर tihattar", 74: "चौहत्तर chauhattar",
    75: "पचहत्तर pachhattar", 76: "छिहत्तर chhihattar", 77: "सतहत्तर sathattar", 78: "अठहत्तर athhattar",
    79: "उन्यासी unyasi", 80: "अस्सी assi", 81: "इक्यासी ikyasi", 82: "बयासी bayasi", 83: "तिरासी tirasi",
    84: "चौरासी chaurasi", 85: "पचासी pachasi", 86: "छियासी chhiyasi", 87: "सत्तासी sattasi", 88: "अट्ठासी atthasi",
    89: "नवासी navasi", 90: "नब्बे nabbe", 91: "इक्यानवे ikyanave", 92: "बानवे banave", 93: "तिरानवे tiranave",
    94: "चौरानवे chauranave", 95: "पंचानवे panchanave", 96: "छियानवे chhiyanave", 97: "सत्तानवे sattanave",
    98: "अट्ठानवे atthanave", 99: "निन्यानवे ninyanave",
    1.25: "सवा sawa sava", 1.5: "डेढ़ dedh", 2.5: "ढाई dhai adhai", 0.75: "पौन paun",
}
WORDS = {w: v for v, spellings in _WORDS.items() for w in spellings.split()}
MULTS = {"sau": 100, "सौ": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000, "हज़ार": 1000, "हजार": 1000,
         "lakh": 100000, "lac": 100000, "लाख": 100000, "crore": 10**7, "करोड़": 10**7}
HALF = {"साढ़े", "साड़े", "sadhe", "saade", "saadhe"}  # "sadhe teen sau" = 3.5 x 100
K = "k"
NUMWORDS = set(WORDS) | set(MULTS) | HALF | {K}


def evaluate(toks, trace=None):
    """Value of the best number in the tokens, or None. A number is a run of digits/number words, e.g.
    'aath sau pachaas' = 850, 'barah sau' = 1200, 'do hazaar paanch sau' = 2500. Runs with a digit beat runs with
    sau/hazaar, which beat bare words; a bare word under 10 ('bhej do') is never an amount. Earliest wins ties."""
    log = trace.append if trace is not None else (lambda *_: None)
    runs, state = [], {"total": 0.0, "cur": 0.0, "digit": False, "mult": False, "any": False, "prev": False, "half": False}

    def close():
        s = state
        if s["any"]:
            value = s["total"] + s["cur"]
            rank = 2 if s["digit"] else 1 if s["mult"] else 0
            keep = value > 0 and (rank > 0 or value >= 10)
            log(f"  run closed: value={value:g} rank={rank} {'kept' if keep else 'dropped'}")
            if keep:
                runs.append((rank, value))
        state.update(total=0.0, cur=0.0, digit=False, mult=False, any=False, prev=False, half=False)

    for t in toks:
        s = state
        if _NUM.fullmatch(t) or t in WORDS:
            if s["prev"]:
                close()  # two numbers in a row are separate runs
            n = float(t) if _NUM.fullmatch(t) else float(WORDS[t])
            if s["half"]:
                n, s["half"] = n + 0.5, False
            s["cur"] += n
            s["digit"] |= bool(_NUM.fullmatch(t))
            s["any"], s["prev"] = True, True
            log(f"{t!r}: number {n:g} -> group={s['cur']:g} total={s['total']:g}")
        elif t in MULTS or (t == K and s["any"] and s["cur"]):
            m = MULTS.get(t, 1000)
            if m == 100:
                s["cur"] = (s["cur"] or 1) * 100
            else:
                s["total"] += (s["cur"] or 1) * m
                s["cur"] = 0.0
            s["mult"], s["any"], s["prev"] = True, True, False
            log(f"{t!r}: x{m} -> group={s['cur']:g} total={s['total']:g}")
        elif t in HALF:
            s["half"] = True
            log(f"{t!r}: half marker, the next number gets +0.5")
        else:
            close()
    close()
    if not runs:
        return None
    best = max(runs, key=lambda r: r[0])[1]  # max() keeps the first of equal ranks
    return int(best) if best == int(best) else best
