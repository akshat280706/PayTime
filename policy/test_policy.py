# Run from repo root: python -m policy.test_policy   (uses a throwaway copy of state.db)
import os, shutil, tempfile
from datetime import datetime

shutil.copy("state.db", tmp := tempfile.mkdtemp())
os.chdir(tmp)

import policy.infer as infer
from agent import policy as rule_policy
from policy.simulator import ACTIONS, rollout

# environment: same seed -> same episode; over-contact opts people out; not contacting never does
assert (rollout(1, lambda c: 3)[0] == rollout(1, lambda c: 3)[0]).all()
firm = [rollout(i, lambda c: 3) for i in range(300)]
assert sum(r[2] for r in firm) > 0 and sum(r[2] for r in [rollout(i, lambda c: 0) for i in range(300)]) == 0
assert all(r[1].max() <= 30 for r in firm)

ctx = {"days_overdue": 20, "amount": 800, "contacts_so_far": 0, "promises_made": 0, "promises_kept": 0,
       "days_since_last_contact": 30, "last_outcome": "none"}
out = infer.learned_next_action(ctx)
assert out["action"] in ACTIONS and out["reason"]

debt = {"id": 3, "status": "open", "stage": 0, "next_action_at": None}
noon = datetime.now().replace(hour=12)
assert rule_policy.next_action(debt, noon)["action"] in ACTIONS
assert rule_policy.next_action({**debt, "status": "opted_out"}, noon)["action"] == "wait"  # guards beat the bandit

infer.PARAMS, infer._model = infer.PARAMS.with_name("missing.npz"), None  # missing params: clear error, rule fallback
try:
    infer.learned_next_action(ctx)
    raise SystemExit("expected FileNotFoundError")
except FileNotFoundError as e:
    assert "policy.train" in str(e)
assert rule_policy.next_action({**debt, "id": 5, "next_action_at": None}, noon)["action"] == "call_gentle"
print("ok")
