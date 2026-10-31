import json
import re
from datetime import date, timedelta

from agent import llm
from agent.intake import normalize_digits

INTENTS = ("promise_to_pay", "claims_paid", "dispute_amount", "refuse", "wrong_number",
           "callback_later", "no_answer", "unclear")  # 'unclear' = e.g. "haan boliye", no intent yet

WEEKDAYS = {"monday": 0, "somvar": 0, "somwar": 0, "सोमवार": 0, "tuesday": 1, "mangalvar": 1, "mangalwar": 1,
            "मंगलवार": 1, "wednesday": 2, "budhvar": 2, "budhwar": 2, "बुधवार": 2, "thursday": 3, "guruvar": 3,
            "brihaspativar": 3, "veervar": 3, "गुरुवार": 3, "friday": 4, "shukravar": 4, "shukrawar": 4,
            "शुक्रवार": 4, "saturday": 5, "shanivar": 5, "shaniwar": 5, "शनिवार": 5, "sunday": 6, "ravivar": 6,
            "itwar": 6, "इतवार": 6, "रविवार": 6}


def _has(text, *words):
    return any(re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", text) for w in words)


def resolve_date(text, today=None):
    """Relative/named date in the utterance -> 'YYYY-MM-DD', else None."""
    today = today or date.today()
    t = normalize_digits(text).lower()
    plus = lambda n: (today + timedelta(days=n)).isoformat()
    if m := re.search(r"(\d+)\s*(?:din|days?|दिन)", t):
        return plus(int(m.group(1)))
    if m := re.search(r"(\d{1,2})\s*(?:tarikh|tareekh|date|तारीख)", t):
        day = int(m.group(1))
        for add in (0, 1, 2):  # this month, else next (skips months too short)
            y, mo = divmod(today.month - 1 + add, 12)
            try:
                d = date(today.year + y, mo + 1, day)
            except ValueError:
                continue
            if d > today:
                return d.isoformat()
    for w, wd in WEEKDAYS.items():
        if _has(t, w):
            return plus((wd - today.weekday()) % 7 or 7)
    if _has(t, "parson", "परसों", "day after tomorrow"):
        return plus(2)
    if _has(t, "kal", "कल", "tomorrow", "tmrw"):
        return plus(1)
    if _has(t, "aaj", "आज", "today"):
        return plus(0)
    if re.search(r"agle\s+(?:hafte|week)|next\s+week|अगले\s+(?:हफ्ते|सप्ताह)", t):
        return plus(7)
    return None


def _keyword_intent(t):
    t = normalize_digits(t).lower()
    if _has(t, "wrong number", "wrong person", "galat number", "rong number", "गलत नंबर", "रॉन्ग नंबर", "yahan koi nahi") \
            or re.search(r"(main|mai|mein)\s+(wo|woh|vo)\s+nahi", t):
        return "wrong_number"
    if _has(t, "paid", "bhej diya", "de diya", "kar diya", "kar di", "transfer kar", "भेज दिया", "दे दिया", "कर दिया"):
        return "claims_paid"
    if _has(t, "nahi dunga", "nahi dungi", "can't pay", "cannot pay", "not paying", "i refuse", "nahi doonga", "nahin dena", "nahi dena", "mat karo", "won't pay",
            "wont pay", "refuse", "नहीं दूंगा", "नहीं दूँगी", "नहीं दूंगी", "नहीं देना"):
        return "refuse"
    if _has(t, "wrong amount", "don't owe", "do not owe", "galat amount", "amount galat", "itna nahi", "itne nahi", "itne kab", "hisaab galat", "dispute",
            "zyada hai", "ज्यादा है", "गलत हिसाब"):
        return "dispute_amount"
    if _has(t, "i'll pay", "i will pay", "pay tomorrow", "kar dunga", "kar dungi", "de dunga", "de dungi", "bhej dunga", "bhej dungi", "denge", "dunga",
            "dungi", "will pay", "pay kar", "pakka", "कर दूंगा", "कर दूँगी", "दे दूंगा", "दे दूंगी", "देंगे"):
        return "promise_to_pay"
    if _has(t, "baad mein", "baad me", "call me later", "not now", "later", "busy", "abhi nahi", "thodi der", "call back", "callback",
            "call karna", "call karo", "बाद में", "अभी नहीं"):
        return "callback_later"
    if resolve_date(t):
        return "promise_to_pay"
    return "unclear"


def _llm_intent(utterance, context, today):
    system = f"""You label one utterance from a debtor on a payment-reminder call. Today is {today.isoformat()}.
Reply with JSON only, no prose: {{"intent": <one of {list(INTENTS)}>, "promised_date": "YYYY-MM-DD" or null}}.
promise_to_pay=gives a date/time they will pay; claims_paid=says already paid; dispute_amount=disagrees with the amount;
refuse=will not pay; wrong_number=is not the debtor; callback_later=asks to be called later; unclear=anything else
(greetings, confirming who they are). promised_date only for promise_to_pay; resolve kal/parson/weekday/agle hafte from today.
Last thing the agent said: {(context or {}).get('last_agent_reply', '')!r}"""
    raw = llm.complete(system, [{"role": "user", "content": utterance}])
    data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    if data["intent"] not in INTENTS:
        raise ValueError(f"bad intent {data['intent']!r}")
    return data


def classify(utterance, context=None):
    """-> {"intent": ..., "promised_date": 'YYYY-MM-DD' | None}. Date rules are deterministic; the LLM only labels."""
    today = date.today()
    if not (utterance or "").strip():
        return {"intent": "no_answer", "promised_date": None}
    res = None
    if not llm.FALLBACK:
        try:
            res = _llm_intent(utterance, context, today)
        except Exception as e:
            print(f"[intents] LLM classify failed ({e}); using keyword rules")
    if res is None:
        res = {"intent": _keyword_intent(utterance), "promised_date": None}
    if res["intent"] != "promise_to_pay":
        return {"intent": res["intent"], "promised_date": None}
    pd = resolve_date(utterance, today) or res.get("promised_date")
    try:
        pd = date.fromisoformat(pd).isoformat() if pd else None
    except ValueError:
        pd = None
    return {"intent": "promise_to_pay", "promised_date": pd}
