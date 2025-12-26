# Agent Self-Check Report

**Generated:** (Run `python tools/agent_check.py` to generate)

## Summary

| Scenario | Result |
|----------|--------|
| Scenario A: Single worker claim | PENDING |
| Scenario B: Two workers, no double-claim | PENDING |
| Scenario C: Lease expiry reclaim | PENDING |

## How to Run

From the `backend` folder:

```bash
# 1. Start the backend (in Terminal 1)
python -m uvicorn main:app --reload

# 2. Run the test harness (in Terminal 2)
python tools/agent_check.py
```

## Scenarios

### Scenario A: Single worker claim
- One pending task
- Expect: task_claimed → task_done
- Check: owner, claimed_at, lease_until, attempt fields set

### Scenario B: Two workers, no double-claim
- Two workers started concurrently
- Expect: exactly one owner for the same task_id while lease valid
- Violation if: both claim same task with overlapping leases

### Scenario C: Lease expiry reclaim
- Worker1 claims then is terminated before done
- Wait until lease expires
- Worker2 reclaims
- Expect: task_reclaimed event

## Rules Tested

- **R1:** State-Only Coordination (agent_id, timestamp, reason)
- **R2:** Task Claiming & Locking (claim, lease, status)
- **R3:** No Handwaving / Artifact-or-Fail (produce artifacts)

