"""python -m policy.train  -> policy/params.npz, policy/results.png and a summary table."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from policy.bandit import LinUCB, features
from policy.simulator import ACTIONS, HORIZON, rollout

HERE = Path(__file__).parent
TRAIN_N, EVAL_N = 4000, 2000
WAIT, GENTLE, FIRM = 0, 2, 3

BASELINES = {
    "never_contact": lambda ctx: WAIT,
    "fixed_schedule (every 3 days)": lambda ctx: GENTLE if ctx["days_since_last_contact"] >= 3 else WAIT,
    "aggressive (daily)": lambda ctx: FIRM,
}


def train(seed=0):
    """LinUCB trained on the return-to-go (this day's reward + everything after it in the episode), not the
    same-day reward: a myopic bandit never pays for the future an opt-out destroys and over-contacts.
    No bootstrapping or value function, so it stays a bandit with Monte-Carlo credit assignment."""
    bandit = LinUCB(alpha=float(sys.argv[1]) if len(sys.argv) > 1 else 0.5)
    for i in range(TRAIN_N):
        steps = []
        rollout(seed * 10**6 + i, lambda c: bandit.act(features(c)),
                lambda c, a, r: steps.append((features(c), a, r)))
        ret = 0.0
        for x, a, r in reversed(steps):
            ret += r
            bandit.update(x, a, ret)
    return bandit


def evaluate(choose):
    """Same debtors (seeds) for every policy. -> cumulative recovered/contacts per day, opt-outs."""
    runs = [rollout(10**7 + i, choose) for i in range(EVAL_N)]
    return sum(r[0] for r in runs), sum(r[1] for r in runs), sum(r[2] for r in runs)


if __name__ == "__main__":
    bandit = train()
    bandit.save(HERE / "params.npz")
    learned = lambda c: bandit.act(features(c), explore=False)
    results = {"learned (LinUCB)": evaluate(learned)} | {n: evaluate(f) for n, f in BASELINES.items()}

    print(f"\nSimulated debtors, not live data: {EVAL_N} held-out debtors, {HORIZON}-day episodes\n")
    print(f"{'policy':32}{'recovered':>12}{'contacts':>10}{'opt-outs':>10}{'Rs/contact':>12}")
    for name, (rec, con, opt) in results.items():
        print(f"{name:32}{rec[-1]:>12,.0f}{con[-1]:>10,.0f}{opt:>10}{rec[-1] / max(con[-1], 1):>12,.0f}")

    fig, ax = plt.subplots(figsize=(11, 7))
    colors = {"learned (LinUCB)": "#0b6e4f", "never_contact": "#888888",
              "fixed_schedule (every 3 days)": "#e08a00", "aggressive (daily)": "#c0392b"}
    for name, (rec, con, _) in results.items():
        ax.plot(np.r_[0, con], np.r_[0, rec] / 1000, lw=4 if name.startswith("learned") else 2.5,
                color=colors[name], label=name)
        ax.plot(con[-1], rec[-1] / 1000, "o", ms=11, color=colors[name])
    ax.set_xlabel("Total contacts made (simulated debtors, not live data)", fontsize=16)
    ax.set_ylabel("Total amount recovered (Rs thousands)", fontsize=16)
    ax.set_title("Amount recovered vs contacts made", fontsize=26, fontweight="bold", pad=38)
    ax.text(0.5, 1.02, f"Simulated debtors, not live data  |  {EVAL_N} debtors, {HORIZON} days each",
            transform=ax.transAxes, ha="center", fontsize=14, color="#444")
    ax.tick_params(labelsize=14)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=15, loc="lower right")
    fig.tight_layout()
    fig.savefig(HERE / "results.png", dpi=150)
    print("\nwrote policy/params.npz, policy/results.png")
