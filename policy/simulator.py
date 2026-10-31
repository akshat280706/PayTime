"""Synthetic debtors for training the escalation bandit. Simulated, not live data."""
import numpy as np

ACTIONS = ["wait", "sms", "call_gentle", "call_firm"]
OUTCOMES = ["none", "no_answer", "engaged", "promise", "broken"]
HORIZON = 30

REACH = {"sms": 0.5, "call_gentle": 1.0, "call_firm": 0.9}   # x response_propensity = chance they engage
GAIN = {"sms": 0.6, "call_gentle": 1.0, "call_firm": 1.6}    # x base_pay_probability when engaged
ANNOY = {"sms": 0.5, "call_gentle": 1.0, "call_firm": 2.0}   # x fatigue_rate added per contact
OPT = {"sms": 0.5, "call_gentle": 1.0, "call_firm": 2.0}     # x opt-out probability
THRESHOLD, DECAY = 1.0, 0.85  # annoyance above THRESHOLD hurts; it decays 15% a day without contact
PROMISE_CHANCE, PROMISE_KEPT = 0.3, 0.65


class Debtor:
    def __init__(self, rng):
        self.rng = rng
        self.propensity = rng.uniform(0.1, 0.9)
        self.base_pay = rng.uniform(0.05, 0.4)
        self.fatigue = rng.uniform(0.05, 0.3)
        self.amount = float(rng.integers(150, 3001))
        self.overdue0 = int(rng.integers(0, 60))
        self.monthly_spend = float(rng.integers(200, 5001))  # independent of the debt: what the customer buys
        self.day, self.annoy, self.engage = 0, 0.0, 0.0
        self.contacts, self.last_contact = 0, None
        self.promises_made = self.promises_kept = 0
        self.pending = None  # day a promised payment is due
        self.last_outcome = "none"

    def context(self):
        since = HORIZON if self.last_contact is None else self.day - self.last_contact
        return {"days_overdue": self.overdue0 + self.day, "amount": self.amount, "monthly_spend": self.monthly_spend, "contacts_so_far": self.contacts,
                "promises_made": self.promises_made, "promises_kept": self.promises_kept,
                "days_since_last_contact": since, "last_outcome": self.last_outcome}

    def step(self, action):
        """One day. -> (reward, paid, opted_out, contacted)."""
        rng, r, paid = self.rng, 0.0, False
        self.annoy *= DECAY
        if self.pending == self.day:
            self.pending = None
            if rng.random() < PROMISE_KEPT:
                paid, r = True, r + self.amount
                self.promises_kept += 1
            else:
                self.last_outcome = "broken"
        contacted = action != "wait"
        if contacted and not paid:
            r -= 1
            self.contacts += 1
            self.last_contact = self.day
            over = self.annoy >= THRESHOLD
            self.annoy += self.fatigue * ANNOY[action] * (1.5 if over and action == "call_firm" else 1)
            p_opt = OPT[action] * min(0.8, 0.005 + 0.4 * max(0.0, self.annoy - THRESHOLD))
            if rng.random() < p_opt:
                return r - (self.amount + 6 * self.monthly_spend), False, True, True  # lose the debt and the customer
            if rng.random() < min(0.95, self.propensity * REACH[action]) * (0.5 if over else 1):
                self.last_outcome = "engaged"
                fatigue_mult = 1.0 if self.annoy < THRESHOLD else max(0.05, 1 - 1.5 * (self.annoy - THRESHOLD))
                if rng.random() < self.base_pay * GAIN[action] * (1 + self.engage) * fatigue_mult:
                    paid, r = True, r + self.amount
                else:
                    self.engage = min(1.0, self.engage + 0.15)
                    if self.pending is None and rng.random() < PROMISE_CHANCE:
                        self.pending = self.day + int(rng.integers(2, 6))
                        self.promises_made += 1
                        self.last_outcome = "promise"
            else:
                self.last_outcome = "no_answer"
        elif not paid and rng.random() < self.base_pay * 0.03:  # some people just pay eventually
            paid, r = True, r + self.amount
        self.day += 1
        return r, paid, False, contacted


def rollout(seed, choose, learn=None):
    """Run one 30-day episode. choose(ctx)->action index into ACTIONS; learn(ctx, action, reward) is called each step.
    -> per-day arrays (recovered, contacts) padded after the episode ends, the opt-out flag, and the total reward."""
    d = Debtor(np.random.default_rng(seed))
    recovered, contacts, opted, total = np.zeros(HORIZON), np.zeros(HORIZON), False, 0.0
    for t in range(HORIZON):
        ctx = d.context()
        a = choose(ctx)
        r, paid, opted, contacted = d.step(ACTIONS[a])
        total += r
        if learn:
            learn(ctx, a, r)
        recovered[t:], contacts[t:] = recovered[t:] + (d.amount if paid else 0), contacts[t:] + contacted
        if paid or opted:
            break
    return recovered, contacts, opted, total
