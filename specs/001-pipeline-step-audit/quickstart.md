# Quickstart: Validating the Step Audit Trail

## Prerequisites
- A reachable Redis; `REDIS_URL=redis://localhost:6379/0` in `.env.qa`
- `pip install -r requirements.txt`

## 1. Unit tests (no Redis needed)
`python -m unittest discover tests`; expect the new audit tests to pass.

## 2. End-to-end
1. `python main.py -c qa`
2. `redis-cli --scan --pattern 'callrail:audit:qa:*'`: expect 9 keys for the run, ordered by index.
3. `redis-cli get callrail:audit:qa:<run_id>:01-read_callrail_account`: expect `"inputs": {}` and an
   `output` equal to the "Read N Callrail accounts" console line.
4. `redis-cli ttl <key>`: expect about 2,592,000 (30 days).
5. Run again: expect a second set of keys; the first run's keys are untouched.

## 3. Redis unavailable
Set `REDIS_URL` to an unreachable host and run: the pipeline completes and saves data; warnings
appear in the log. With `REDIS_URL` empty, no audit output and no warnings.

## 4. PII check
`redis-cli get` any key: only counts and step names appear.
