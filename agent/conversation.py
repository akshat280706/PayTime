import re
from contextlib import closing
from datetime import date, datetime

from agent import llm
from agent.intents import classify
from agent.policy import CLOSED
from agent.state import apply_outcome
from db import get_db
from verify.matcher import match_feed_transaction, settle_debt

MERCHANT = "Sharma General Store"
LANGS = {"hi": "Hindi", "mr": "Marathi", "ta": "Tamil"}
TONE = {
    0: "GENTLE: just a reminder, 'whenever convenient'. No pressure.",
    1: "FIRM: state the amount and how many days it has been outstanding, and ask when they can pay. Stay polite.",
    2: "FINAL: say the shopkeeper will follow up personally. Nothing more severe than that.",
}
GUIDE = {
    "promise_to_pay": "They promised to pay by {date}. Thank them, repeat the date, close warmly.",
    "claims_paid": "They say they already paid. Thank them, do not question it, ask them to send a payment screenshot so it can be confirmed.",
    "dispute_amount": "They disagree with the amount. Acknowledge, say the shopkeeper will speak to them about it. Do not argue.",
    "refuse": "They declined. Stay polite, do not pressure, say the shopkeeper will be informed.",
    "callback_later": "They asked for a later call. Agree politely and close.",
    "unclear": "Intent not clear yet. If identity is unconfirmed, treat a yes as confirmation and then give the reminder in the stage's tone. Otherwise politely ask them to repeat.",
}
OPENING = {  # first sentence = automated-reminder disclosure, second = identity check. Never LLM-generated.
    "hi": "नमस्ते, यह {m} की ओर से एक स्वचालित रिमाइंडर कॉल है। क्या मेरी बात {n} जी से हो रही है?",
    "mr": "नमस्कार, हा {m} तर्फे आलेला एक स्वयंचलित रिमाइंडर कॉल आहे. मी {n} यांच्याशी बोलत आहे का?",
    "ta": "வணக்கம், இது {m} சார்பாக வரும் தானியங்கி நினைவூட்டல் அழைப்பு. நான் {n} அவர்களிடம் பேசுகிறேனா?",
}
CANNED = {
    "hi": {
        "ask0": "यह {a} रुपये के बकाया की एक छोटी याद दिलाने वाली कॉल है। जब आपको सुविधा हो, कृपया भुगतान कर दीजिए।",
        "ask1": "आपके {a} रुपये {d} दिन से बकाया हैं। कृपया बताइए, भुगतान कब तक हो पाएगा?",
        "ask2": "आपके {a} रुपये अब भी बकाया हैं। {m} के मालिक खुद आपसे बात करेंगे। धन्यवाद।",
        "promise": "ठीक है, {date} तक भुगतान की बात मैंने नोट कर ली है। धन्यवाद!",
        "claims_paid": "धन्यवाद। क्या आप भुगतान का स्क्रीनशॉट भेज सकते हैं? मैं जाँच कर लूँगी।",
        "dispute_amount": "मैं समझ गई। यह बात मालिक तक पहुँचा दी जाएगी, वे आपसे रकम पर बात करेंगे। धन्यवाद।",
        "refuse": "ठीक है, यह बात मालिक को बता दी जाएगी। धन्यवाद।",
        "wrong_number": "माफ़ कीजिए, गलत नंबर लग गया। आपका दिन शुभ हो।",
        "callback_later": "ठीक है, मैं बाद में फिर से कॉल करूँगी। धन्यवाद।",
        "unclear": "माफ़ कीजिए, क्या आप दोबारा बता सकते हैं?",
        "verified": "धन्यवाद, आपका {a} रुपये का भुगतान मिल गया है। अब आपको कोई रिमाइंडर नहीं आएगा।",
        "review": "धन्यवाद। मैं अभी इसकी पुष्टि नहीं कर पाई। मालिक इसे देखकर आपसे संपर्क करेंगे।",
    },
    "mr": {
        "ask0": "तुमचे {a} रुपये बाकी आहेत, याची ही छोटीशी आठवण. सोयीनुसार कृपया भरून टाका.",
        "ask1": "तुमचे {a} रुपये {d} दिवसांपासून बाकी आहेत. कृपया सांगा, पैसे कधी भरू शकाल?",
        "ask2": "तुमचे {a} रुपये अजूनही बाकी आहेत. {m} चे मालक स्वतः तुमच्याशी बोलतील. धन्यवाद.",
        "promise": "ठीक आहे, {date} पर्यंत पैसे भरण्याची नोंद केली आहे. धन्यवाद!",
        "claims_paid": "धन्यवाद. कृपया पेमेंटचा स्क्रीनशॉट पाठवू शकाल का? आम्ही तपासून घेऊ.",
        "dispute_amount": "समजले. ही गोष्ट मालकांना कळवली जाईल, ते तुमच्याशी बोलतील. धन्यवाद.",
        "refuse": "ठीक आहे, ही गोष्ट मालकांना कळवली जाईल. धन्यवाद.",
        "wrong_number": "माफ करा, चुकीचा नंबर लागला. तुमचा दिवस शुभ जावो.",
        "callback_later": "ठीक आहे, आम्ही नंतर पुन्हा कॉल करू. धन्यवाद.",
        "unclear": "माफ करा, कृपया पुन्हा सांगाल का?",
        "verified": "धन्यवाद, तुमचे {a} रुपयांचे पेमेंट मिळाले आहे. आता तुम्हाला कोणताही रिमाइंडर येणार नाही.",
        "review": "धन्यवाद. मला आत्ता याची खात्री करता आली नाही. मालक ते तपासून तुमच्याशी बोलतील.",
    },
    "ta": {
        "ask0": "{a} ரூபாய் நிலுவையில் உள்ளது என்பதற்கான சிறிய நினைவூட்டல். உங்களுக்கு வசதியான நேரத்தில் செலுத்துங்கள்.",
        "ask1": "உங்கள் {a} ரூபாய் {d} நாட்களாக நிலுவையில் உள்ளது. எப்போது செலுத்த முடியும் என்று சொல்லுங்கள்.",
        "ask2": "உங்கள் {a} ரூபாய் இன்னும் நிலுவையில் உள்ளது. {m} உரிமையாளர் நேரில் உங்களிடம் பேசுவார். நன்றி.",
        "promise": "சரி, {date} அன்று செலுத்துவதாக குறித்துக்கொண்டேன். நன்றி!",
        "claims_paid": "நன்றி. பணம் செலுத்தியதற்கான ஸ்கிரீன்ஷாட்டை அனுப்ப முடியுமா? நாங்கள் சரிபார்க்கிறோம்.",
        "dispute_amount": "புரிந்தது. இதை உரிமையாளரிடம் தெரிவிக்கிறோம், அவர் உங்களிடம் பேசுவார். நன்றி.",
        "refuse": "சரி, இதை உரிமையாளரிடம் தெரிவிக்கிறோம். நன்றி.",
        "wrong_number": "மன்னிக்கவும், தவறான எண். நல்ல நாளாக அமையட்டும்.",
        "callback_later": "சரி, பிறகு மீண்டும் அழைக்கிறோம். நன்றி.",
        "unclear": "மன்னிக்கவும், மீண்டும் சொல்ல முடியுமா?",
        "verified": "நன்றி, உங்கள் {a} ரூபாய் பணம் கிடைத்தது. இனி உங்களுக்கு நினைவூட்டல் வராது.",
        "review": "நன்றி. என்னால் இப்போது உறுதிப்படுத்த முடியவில்லை. உரிமையாளர் சரிபார்த்து உங்களிடம் பேசுவார்.",
    },
}
# Safety net behind the prompt rules: a reply that mentions any of these is replaced by a canned one.
UNSAFE = re.compile(r"legal|lawyer|court|police|\bfir\b|cibil|credit (?:score|report)|blacklist|arrest|notice|"
                    r"कोर्ट|पुलिस|कानून|वकील|सिबिल|नोटिस|நீதிமன்ற|காவல்", re.I)

# ponytail: in-memory per-call transcript, lost on restart (the DB log still has every turn). Persist if multi-worker.
CALLS = {}


def _fmt_amount(a):
    return str(int(a)) if a == int(a) else str(a)


def load_context(debt_id):
    with closing(get_db()) as db:
        row = db.execute("SELECT d.*, c.name, c.language, c.phone FROM debts d JOIN contacts c ON c.id=d.contact_id"
                         " WHERE d.id=?", (debt_id,)).fetchone()
        if row is None:
            raise LookupError(f"debt {debt_id} not found")
        logs = db.execute("SELECT ts, channel, stage, transcript, outcome FROM contact_log WHERE debt_id=?"
                          " ORDER BY ts, id", (debt_id,)).fetchall()
        promises = db.execute("SELECT promised_date, made_at, kept FROM promises WHERE debt_id=? ORDER BY id",
                              (debt_id,)).fetchall()
    ctx = dict(row)
    ctx["days_overdue"] = max(0, (date.today() - datetime.fromisoformat(ctx["due_date"]).date()).days)
    ctx["logs"], ctx["promises"] = [dict(l) for l in logs], [dict(p) for p in promises]
    ctx["lang"] = ctx["language"] if ctx["language"] in LANGS else "hi"
    return ctx


def build_system_prompt(ctx, intent=None, promised_date=None):
    history = "\n".join(f"- {l['ts']} {l['channel']} stage {l['stage']} [{l['outcome']}]: {l['transcript']}"
                        for l in ctx["logs"]) or "- none, this is the first contact"
    promises = "\n".join(f"- promised {p['promised_date']} (made {p['made_at']}, kept={bool(p['kept'])})"
                         for p in ctx["promises"]) or "- none"
    guide = GUIDE.get(intent, "").format(date=promised_date)
    return f"""You are a voice agent making a debt-reminder phone call for the shopkeeper of {MERCHANT}.
Debtor: {ctx['name']}. Amount owed: Rs {_fmt_amount(ctx['amount'])}. Days overdue: {ctx['days_overdue']}.
Current stage: {ctx['stage']}. Tone: {TONE[min(ctx['stage'], 2)]}
Speak {LANGS[ctx['lang']]} in its native script (it goes to a text-to-speech engine). Keep every reply under 40 words, this is a phone call.
You are a woman. In Hindi ALWAYS use feminine verb forms for yourself, consistently through the whole call: मैं बोल रही हूँ, मैं कर लूँगी, मैं समझ गई, never रहा हूँ / लूँगा / गया.

HARD RULES (never break them):
1. The call's first sentence is always a disclosure that this is an automated reminder on behalf of {MERCHANT}, then you confirm who you are speaking to. That opening has already been spoken.
2. Never threaten legal action, credit or credit-score consequences, or public disclosure. Never mention police, courts, notices or shaming.
3. If the person says they are not {ctx['name']}, say NOTHING about the debt and end the call politely.
4. Never accuse anyone of lying about payment. If they say they paid, thank them and ask for a screenshot to confirm.

Previous contacts for this debt:
{history}
Promises:
{promises}

Detected intent of the person's last message: {intent or 'unknown'}. {guide}"""


def opening(ctx):
    return OPENING[ctx["lang"]].format(m=MERCHANT, n=ctx["name"])


def start_call(debt_id):
    ctx = load_context(debt_id)
    if ctx["status"] in CLOSED:
        raise PermissionError(f"debt is {ctx['status']}, contact not allowed")
    text = opening(ctx)
    CALLS[debt_id] = [{"role": "user", "content": "(call connected)"}, {"role": "assistant", "content": text}]
    return text


def _canned(ctx, intent, promised_date, first_reply):
    c = CANNED[ctx["lang"]]
    if intent == "no_answer":
        return ""
    if intent == "unclear" and first_reply:  # most likely "yes, speaking": now give the reminder
        key = f"ask{min(ctx['stage'], 2)}"
    else:
        key = {"promise_to_pay": "promise"}.get(intent, intent)
    pd = date.fromisoformat(promised_date).strftime("%d %b") if promised_date else ""
    return c[key].format(a=_fmt_amount(ctx["amount"]), d=ctx["days_overdue"], m=MERCHANT, date=pd)


def _reply(ctx, msgs, intent, promised_date):
    if intent == "wrong_number" or ctx["status"] == "opted_out":
        return CANNED[ctx["lang"]]["wrong_number"]  # deterministic: must never mention the debt
    if not llm.FALLBACK and intent != "no_answer":
        try:
            text = llm.complete(build_system_prompt(ctx, intent, promised_date), msgs).strip()
            if text and not UNSAFE.search(text) and len(text.split()) <= 40:
                return text
            print("[conversation] LLM reply rejected (unsafe or >40 words); using canned reply")
        except Exception as e:
            print(f"[conversation] LLM call failed ({e}); using canned reply")
    return _canned(ctx, intent, promised_date, first_reply=len(msgs) <= 3)


def _verify(debt_id):
    """Feed check for a 'paid' claim. Settles on certain/high; ambiguous and no-match are left open."""
    with closing(get_db()) as db:
        m = match_feed_transaction(db, debt_id=debt_id)
        if not m:
            return {"verified": False, "confidence": None}
        txn = m["transaction"]
        if m["confidence"] == "ambiguous":
            return {"verified": False, "confidence": "ambiguous", "candidate_ref": txn["ref"]}
        try:
            learned = settle_debt(db, debt_id, txn, confidence=m["confidence"])
        except ValueError:  # closed or reference already used meanwhile
            return {"verified": False, "confidence": None}
        return {"verified": True, "confidence": m["confidence"], "amount": txn["amount"],
                "transaction_ref": txn["ref"], "payer_handle_learned": learned}


def turn(debt_id, utterance):
    ctx = load_context(debt_id)
    if debt_id not in CALLS:
        start_call(debt_id)
    msgs = CALLS[debt_id]
    msgs.append({"role": "user", "content": utterance or "(silence)"})
    res = classify(utterance, {"last_agent_reply": msgs[-2]["content"]})
    # "I paid": the ledger decides, not the claim. No match keeps the normal reply (asks for a screenshot).
    settled = ctx["status"] == "settled"
    verification = _verify(debt_id) if res["intent"] == "claims_paid" and not settled else None
    canned = CANNED[ctx["lang"]]
    if settled and res["intent"] == "claims_paid":  # already confirmed earlier: say so, don't ask for a screenshot again
        text = canned["verified"].format(a=_fmt_amount(ctx["amount"]))
    elif verification and verification["verified"]:
        text = canned["verified"].format(a=_fmt_amount(ctx["amount"]))
    elif verification and verification["confidence"] == "ambiguous":
        text = canned["review"]
    else:
        text = _reply(ctx, msgs, res["intent"], res["promised_date"])
    msgs.append({"role": "assistant", "content": text})
    outcome = apply_outcome(debt_id, res["intent"], {
        "promised_date": res["promised_date"],
        "transcript": f"Customer: {utterance}\nAgent: {text}"})
    if verification:
        outcome["verification"] = verification
        if verification["confidence"] == "ambiguous":
            outcome["needs_merchant"] = True  # a transaction exists but can't be tied to this customer
    return {"reply_text": text, "intent": res["intent"], "outcome": outcome, "language": ctx["lang"]}


if __name__ == "__main__":
    # Fake call against debt 1. Runs on a throwaway copy of state.db so the real demo debt stays clean.
    import os, shutil, tempfile
    tmp = tempfile.mkdtemp()
    shutil.copy("state.db", tmp)
    os.chdir(tmp)
    print("AGENT:", start_call(1))
    for line in ["haan, main bol raha hoon", "abhi paise nahi hain, parson tak kar dunga", "paisa bhej diya hai"]:
        print("\nCUSTOMER:", line)
        r = turn(1, line)
        print("AGENT:", r["reply_text"])
        print("  ->", r["intent"], r["outcome"])
