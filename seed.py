import random
from datetime import datetime, timedelta

from db import get_db

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
    handle = n.split()[0].lower() + "@paytm"
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

# debt 1 (850) matches the first txn, 10 minutes ago; the rest are noise
amounts = [850, 420, 975, 1340, 60, 2510, 180, 730, 1999, 275, 640, 3100]
for i, amt in enumerate(amounts, 1):
    ts = now - timedelta(minutes=10) if i == 1 else now - timedelta(hours=random.randint(1, 72))
    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                 (i, amt, iso(ts), "".join(random.choices("0123456789", k=12)),
                  random.choice(names)[0].split()[0].lower() + "@paytm", "SUCCESS"))

conn.commit()
