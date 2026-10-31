"""LinUCB contextual bandit (one ridge regression per action). Myopic: it learns from same-day reward only."""
import numpy as np

from policy.simulator import ACTIONS, OUTCOMES

SCALE = 100.0  # rewards are divided by this so alpha is comparable across amounts
D = 7 + len(OUTCOMES) + 2 + 2


def features(ctx):
    amt, rec = ctx["amount"] / 3000, 0.85 ** ctx["days_since_last_contact"]  # recency: 1 = just contacted
    c = ctx["contacts_so_far"] / 30
    onehot = [float(ctx["last_outcome"] == o) for o in OUTCOMES]
    # amt*rec and amt*c: expected reward is amount x probability, which a plain linear model can't express
    return np.array([1, ctx["days_overdue"] / 90, amt, c, ctx["promises_made"] / 3, ctx["promises_kept"] / 3,
                     rec, *onehot, amt * rec, amt * c,
                     ctx["monthly_spend"] / 5000, ctx["amount"] / ctx["monthly_spend"] / 15])


class LinUCB:
    def __init__(self, alpha=1.0, lam=1.0):
        self.alpha = alpha
        self.A = np.stack([lam * np.eye(D) for _ in ACTIONS])
        self.b = np.zeros((len(ACTIONS), D))

    def values(self, x):
        """Estimated reward per action (in rupees), no exploration bonus."""
        return np.array([np.linalg.solve(A, b) @ x for A, b in zip(self.A, self.b)]) * SCALE

    def act(self, x, explore=True):
        bonus = np.array([np.sqrt(x @ np.linalg.solve(A, x)) for A in self.A]) * self.alpha if explore else 0
        return int(np.argmax(self.values(x) / SCALE + bonus))

    def update(self, x, a, reward):
        self.A[a] += np.outer(x, x)
        self.b[a] += reward / SCALE * x

    def save(self, path):
        np.savez(path, A=self.A, b=self.b)

    @classmethod
    def load(cls, path):
        z = np.load(path)
        m = cls(alpha=0)
        m.A, m.b = z["A"], z["b"]
        return m
