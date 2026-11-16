# Generated Kanban clone

Generated from `spec.json`. Runs on a single FastAPI process with a local SQLite DB and bundled browser frontend; no Node build required.

```bash
pip install -r requirements.txt
python server.py
```

Open http://localhost:8000. Verification/reset endpoints require `X-Verifier-Key` (defaults to `local-dev-verifier`; override `VERIFIER_KEY`). Do not expose this local demo service on the public internet. To run separately, use `PORT=8002 python server.py`.

The generated clone implements the task/board schema from `spec.json`. It is **not a byte-for-byte or full feature clone** of Kanboard, and does not replay unknown Kanboard internal APIs.
