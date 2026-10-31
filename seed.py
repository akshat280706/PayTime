import random
from datetime import datetime, timedelta

from db import get_db
from verify.matcher import match_feed_transaction

random.seed(7)
now = datetime.now()
iso = lambda d: d.isoformat(timespec="seconds")

conn = get_db()
for t in ("contacts", "debts", "contact_log", "promises", "transactions"):
    conn.execute(f"DROP TABLE IF EXISTS {t}")
conn.executescript(open("schema.sql").read())

names = [
    ("Ramesh Kumar", "hi"), ("Sunita Devi", "hi"), ("Amit Sharma", "hi"),
    ("Priya Patil", "mr"), ("Sachin Jadhav", "mr"), ("Anita Deshmukh", "mr"),
    ("Vijay Shinde", "mr"), ("Lakshmi Iyer", "ta"), ("Murugan Selvam", "ta"),
    ("Kavitha Rajan", "ta"), ("Senthil Kumar", "ta"), ("Pooja Verma", "hi"),
    ("Rajesh Gupta", "hi"), ("Meena Kulkarni", "mr"), ("Arjun Nair", "ta"),
]
for i, (n, lang) in enumerate(names, 1):
    handle = None if i == 1 else n.split()[0].lower() + "@paytm"  # Ramesh (debt 1): no payment seen yet, handle unknown
    conn.execute("INSERT INTO contacts VALUES (?,?,?,?,?)",
                 (i, n, f"+91 9{random.randint(100000000, 999999999)}", lang, handle))

# (contact_id, amount, days_ago, stage, status)
debts = [
    (1, 850, 30, 1, "open"), (4, 1200, 45, 2, "promised"), (8, 300, 10, 0, "open"),
    (2, 3000, 60, 3, "escalated"), (5, 150, 5, 0, "open"), (9, 2200, 20, 1, "settled"),
]
for i, (c, amt, ago, stage, status) in enumerate(debts, 1):
    created = now - timedelta(days=ago)
    conn.execute("INSERT INTO debts VALUES (?,?,?,?,?,?,?,?)",
                 (i, c, amt, iso(created), iso(created + timedelta(days=7)),
                  stage, status, iso(now + timedelta(days=1))))

# debt 2 and 3 have chase history; debt 1 stays clean for the demo
logs = [
    (2, 6, 1, "Ring ring... koi jawab nahi mila, call cut gaya.", "no_answer"),
    (2, 4, 2, "Agent: Namaste Priya ji, Sharma Kirana se bol rahi hoon, 1200 rupaye udhaar baaki hai. "
              "Priya: Haan haan, yaad hai, is hafte thoda tight hai. Parson tak kar dungi, pakka.", "promise_to_pay"),
    (2, 1, 2, "Agent: Priya ji, parson ka wada yaad dilana tha. "
              "Priya: Haan, abhi bahar hoon, kal shaam ko call karna, tab bata dungi.", "callback_later"),
    (3, 5, 0, "Ring ring... phone switch off aa raha hai.", "no_answer"),
    (3, 2, 0, "Agent: Vanakkam Lakshmi, 300 rupaye baaki hai. "
              "Lakshmi: Ippo busy, aap thodi der baad call pannunga.", "callback_later"),
]
for d, ago, stage, text, outcome in logs:
    conn.execute("INSERT INTO contact_log (debt_id, ts, channel, stage, transcript, outcome) VALUES (?,?,?,?,?,?)",
                 (d, iso(now - timedelta(days=ago)), "call", stage, text, outcome))
conn.execute("INSERT INTO promises (debt_id, promised_date, made_at) VALUES (2,?,?)",
             (iso(now + timedelta(days=2)), iso(now - timedelta(days=4))))

# Noise: amounts that match no open debt, so the matcher is not trivially correct.
amounts = [420, 975, 1340, 60, 2510, 180, 730, 1999, 275, 640, 3100]
for i, amt in enumerate(amounts, 1):
    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                 (i, amt, iso(now - timedelta(hours=random.randint(1, 72))), "".join(random.choices("0123456789", k=12)),
                  random.choice(names)[0].split()[0].lower() + "@paytm", "SUCCESS"))

# The verification ladder, one rung per demo debt:
#   debt 1  Ramesh  payment present, contact handle NULL            -> settles HIGH and learns ramesh@paytm
#   debt 2  Priya   payment present, contact handle already set     -> settles CERTAIN
#   debt 3  Lakshmi no payment at all                               -> honest "can't see it yet"
# (POST /api/demo/payment {debt_id} can still land a payment live mid-call.)
priya = conn.execute("SELECT payer_handle FROM contacts WHERE id=4").fetchone()[0]
for tid, amt, handle, minutes in [(len(amounts) + 1, 850, "ramesh@paytm", 10), (len(amounts) + 2, 1200, priya, 15)]:
    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                 (tid, amt, iso(now - timedelta(minutes=minutes)), "".join(random.choices("0123456789", k=12)),
                  handle, "SUCCESS"))

conn.commit()

# What is demoable, straight from the real matcher (nothing is settled here).
print(f"\nSeeded {conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]} contacts, "
      f"{conn.execute('SELECT COUNT(*) FROM debts').fetchone()[0]} debts, "
      f"{conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]} transactions\n")
print(f"{'debt':<5}{'customer':<18}{'amount':>8}  {'status':<10}{'lang':<6}matching payment")
for d in conn.execute("SELECT d.id, c.name, c.language, c.payer_handle, d.amount, d.status FROM debts d "
                      "JOIN contacts c ON c.id = d.contact_id ORDER BY d.id").fetchall():
    m = match_feed_transaction(conn, debt_id=d["id"])
    if d["status"] in ("settled", "opted_out"):
        verdict = "n/a (closed)"
    elif not m:
        verdict = "none: agent says it can't see the payment yet"
    elif m["confidence"] == "certain":
        verdict = f"YES: settles CERTAIN (handle {d['payer_handle']} already known)"
    elif m["confidence"] == "high":
        verdict = f"YES: settles HIGH, will learn {m['transaction']['payer_handle']}"
    else:
        verdict = "ambiguous: goes to merchant review"
    print(f"{d['id']:<5}{d['name']:<18}{'₹' + format(d['amount'], ',.0f'):>8}  {d['status']:<10}{d['language']:<6}{verdict}")
print("\nLand a payment live: POST /api/demo/payment {\"debt_id\": N}")
