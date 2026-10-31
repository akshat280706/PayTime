# Run from repo root: python -m agent.test_amounts   (no LLM; uses a throwaway copy of state.db for the sentence checks)
import os, shutil, tempfile

shutil.copy("state.db", tmp := tempfile.mkdtemp())
os.chdir(tmp)

from agent.intake import amount_trace, parse_amount, parse_intake

FORMS = {  # amount -> written and spoken forms, Latin and Devanagari
    100: ["100", "१००", "sau", "ek sau", "सौ", "एक सौ", "1 sau"],
    150: ["150", "१५०", "ek sau pachaas", "एक सौ पचास", "dedh sau", "डेढ़ सौ", "1 sau 50"],
    850: ["850", "८५०", "aath sau pachaas", "आठ सौ पचास", "8 sau 50"],
    1200: ["1200", "१२००", "1,200", "barah sau", "bara sau", "बारह सौ", "12 sau", "१२ सौ",
           "ek hazaar do sau", "एक हज़ार दो सौ", "ek hazar do sau"],
    2000: ["2000", "२०००", "do hazaar", "दो हज़ार", "2 hazaar", "2k"],
    3000: ["3000", "३०००", "teen hazaar", "तीन हजार", "3 hazaar"],
    # the other Hindi number shapes: teens/tens words, sau after a 2-digit word, halves, lakh
    1500: ["pandrah sau", "पंद्रह सौ", "dedh hazaar", "डेढ़ हज़ार"], 2500: ["dhai hazaar", "do hazaar paanch sau"],
    350: ["sadhe teen sau", "साढ़े तीन सौ"], 50: ["pachaas", "पचास"], 125: ["sawa sau"], 100000: ["ek lakh"],
}
for want, forms in FORMS.items():
    for form in forms:
        for sentence in (form, f"Priya ko {form} ka reminder bhejo"):
            got = parse_amount(sentence)
            assert got == want, f"{sentence!r}: wanted {want}, got {got}\n" + "\n".join(amount_trace(sentence)["steps"])

# not amounts: a bare small number word is a verb or filler, never money
for text in ["Ramesh ko bhej do", "kar do", "ek baar bhej do", "Ramesh ko reminder bhejo", "teen log"]:
    assert parse_amount(text) is None, text
assert parse_amount("Das ko 500 ka reminder bhejo") == 500          # "das" is a name here, the digits win
assert parse_amount("bhej do 850 ka") == 850

# the report: "Priya ko 1200 ka reminder bhejo" became 100. Every way of saying it now lands on Priya Patil, 1200.
for said in ["Priya ko 1200 ka reminder bhejo", "प्रिया को १२०० का रिमाइंडर भेजो", "Priya ko barah sau ka reminder bhejo",
             "Priya ko bara sau ka reminder bhejo", "प्रिया को बारह सौ का रिमाइंडर भेजो", "Priya ko 12 sau ka reminder bhejo",
             "Priya ko ek hazaar do sau ka reminder bhejo"]:
    r = parse_intake(said)
    assert (r["contact_id"], r["amount"]) == (4, 1200), (said, r)
# Ramesh's 150 / 850 used to lose the part after "sau"
assert parse_intake("Ramesh ko ek sau pachaas ka reminder bhejo")["amount"] == 150
assert parse_intake("रमेश को आठ सौ पचास का रिमाइंडर भेजो")["amount"] == 850
assert parse_intake("रमेश को आठ सौ पचास का रिमाइंडर भेजो")["debt_id"] == 1   # and so it finds Ramesh's existing 850 debt
print("ok")
