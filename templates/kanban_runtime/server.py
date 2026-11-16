"""Generated clone runtime: Kanban task domain.

All application labels, columns, priority values, and initial records come from
spec.json. Only this bounded task domain is implemented in milestone 1.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "spec.json").read_text(encoding="utf-8"))
DB_PATH = Path(os.environ.get("CLONE_DB_PATH", str(ROOT / "clone.sqlite3")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
VERIFIER_KEY = os.environ.get("VERIFIER_KEY", "local-dev-verifier")
COLUMN_IDS = [c["id"] for c in SPEC["columns"]]
PRIORITIES = SPEC["priorities"]
_LOCK = threading.RLock()

app = FastAPI(title=f'{SPEC["title"]} — Clone', version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    with _LOCK:
        db = sqlite3.connect(str(DB_PATH), timeout=15, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def create_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL,
            column_name TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            action TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


def reset_db(db):
    db.execute("DELETE FROM tasks")
    db.execute("DELETE FROM events")
    db.execute("DELETE FROM sqlite_sequence WHERE name IN ('tasks','events')")
    stamp = utcnow()
    for item in SPEC.get("initial_tasks", []):
        db.execute(
            "INSERT INTO tasks(title,description,priority,column_name,tags_json,is_active,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                item["title"], item.get("description", ""),
                item.get("priority", SPEC["default_priority"]),
                item.get("column", SPEC["default_column"]),
                json.dumps(item.get("tags", [])), int(item.get("is_active", True)), stamp, stamp,
            ),
        )
    db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('initialized','1')")


with connection() as db:
    create_tables(db)
    if db.execute("SELECT value FROM meta WHERE key='initialized'").fetchone() is None:
        reset_db(db)


def require_verifier(key: Optional[str]):
    if key is None or key != VERIFIER_KEY:
        raise HTTPException(403, "Verifier access required")


def get_task(db, task_id: int):
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Task not found")
    return row


def serialize(row):
    return {
        "id": row["id"], "title": row["title"], "description": row["description"],
        "priority": row["priority"], "column": row["column_name"],
        "tags": json.loads(row["tags_json"]), "is_active": bool(row["is_active"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def log_event(db, task_id, action, details):
    db.execute("INSERT INTO events(task_id,action,details_json,timestamp) VALUES(?,?,?,?)",
               (task_id, action, json.dumps(details), utcnow()))


def check_fields(data: dict):
    if "title" in data:
        if not isinstance(data["title"], str) or not data["title"].strip():
            raise HTTPException(422, "A nonempty title is required")
        if len(data["title"]) > 200:
            raise HTTPException(422, "Title too long")
        data["title"] = data["title"].strip()
    if "column" in data and data["column"] not in COLUMN_IDS:
        raise HTTPException(422, "Unknown board column")
    if "priority" in data and data["priority"] not in PRIORITIES:
        raise HTTPException(422, "Unknown priority")
    if "tags" in data:
        if not isinstance(data["tags"], list) or any(not isinstance(x, str) for x in data["tags"]):
            raise HTTPException(422, "Tags must be strings")
        data["tags"] = [x.strip() for x in data["tags"] if x.strip()][:20]
    return data


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    priority: Optional[str] = None
    column: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class TaskPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    column: Optional[str] = None
    tags: Optional[list[str]] = None


class Goal(BaseModel):
    task: dict = Field(default_factory=dict)
    count: Optional[int] = None


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "app_id": SPEC["app_id"]}


@app.get("/api/spec")
def spec():
    # Do not expose verifier token or privileged state to a GUI agent.
    return {key: val for key, val in SPEC.items() if key not in ("initial_tasks", "reference")}


@app.get("/api/tasks")
def list_tasks(include_closed: bool = Query(default=False)):
    with connection() as db:
        rows = db.execute("SELECT * FROM tasks " + ("" if include_closed else "WHERE is_active=1 ") + "ORDER BY id").fetchall()
        return [serialize(r) for r in rows]


@app.get("/api/events")
def list_events():
    with connection() as db:
        return [dict(id=r["id"], task_id=r["task_id"], action=r["action"],
                     details=json.loads(r["details_json"]), timestamp=r["timestamp"])
                for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]


@app.get("/api/tasks/{task_id}")
def read_task(task_id: int):
    with connection() as db:
        return serialize(get_task(db, task_id))


@app.post("/api/tasks", status_code=201)
def create_task(input: TaskCreate):
    data = input.model_dump(exclude_none=True)
    data.setdefault("priority", SPEC["default_priority"])
    data.setdefault("column", SPEC["default_column"])
    data = check_fields(data)
    stamp = utcnow()
    with connection() as db:
        cur = db.execute(
            "INSERT INTO tasks(title,description,priority,column_name,tags_json,is_active,created_at,updated_at) "
            "VALUES(?,?,?,?,?,1,?,?)",
            (data["title"], data["description"], data["priority"], data["column"], json.dumps(data["tags"]), stamp, stamp),
        )
        log_event(db, cur.lastrowid, "create_task", {"title": data["title"], "column": data["column"]})
        return serialize(get_task(db, cur.lastrowid))


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, input: TaskPatch):
    data = check_fields(input.model_dump(exclude_unset=True, exclude_none=True))
    with connection() as db:
        row = get_task(db, task_id)
        if not data:
            return serialize(row)
        mapping = {"title": "title", "description": "description", "priority": "priority", "column": "column_name", "tags": "tags_json"}
        updates = {mapping[k]: json.dumps(v) if k == "tags" else v for k, v in data.items()}
        updates["updated_at"] = utcnow()
        sql = "UPDATE tasks SET " + ", ".join(f"{k}=?" for k in updates) + " WHERE id=?"
        db.execute(sql, (*updates.values(), task_id))
        log_event(db, task_id, "update_task", data)
        return serialize(get_task(db, task_id))


def set_active(task_id: int, active: bool):
    with connection() as db:
        get_task(db, task_id)
        db.execute("UPDATE tasks SET is_active=?,updated_at=? WHERE id=?", (int(active), utcnow(), task_id))
        log_event(db, task_id, "reopen_task" if active else "close_task", {})
        return serialize(get_task(db, task_id))


@app.post("/api/tasks/{task_id}/close")
def close_task(task_id: int):
    return set_active(task_id, False)


@app.post("/api/tasks/{task_id}/reopen")
def reopen_task(task_id: int):
    return set_active(task_id, True)


@app.get("/internal/state")
def internal_state(x_verifier_key: Optional[str] = Header(default=None)):
    require_verifier(x_verifier_key)
    with connection() as db:
        return {
            "tasks": [serialize(r) for r in db.execute("SELECT * FROM tasks ORDER BY id").fetchall()],
            "events": [dict(id=r["id"], task_id=r["task_id"], action=r["action"],
                            details=json.loads(r["details_json"]), timestamp=r["timestamp"])
                       for r in db.execute("SELECT * FROM events ORDER BY id").fetchall()],
        }


@app.post("/internal/reset")
def internal_reset(x_verifier_key: Optional[str] = Header(default=None)):
    require_verifier(x_verifier_key)
    with connection() as db:
        reset_db(db)
    return {"ok": True, "reset_to_seed": True}


@app.post("/internal/verify")
def internal_verify(goal: Goal, x_verifier_key: Optional[str] = Header(default=None)):
    require_verifier(x_verifier_key)
    allowed = {"id", "title", "description", "priority", "column", "tags", "is_active"}
    if not goal.task and goal.count is None:
        raise HTTPException(422, "Specify a task predicate or count")
    if set(goal.task) - allowed:
        raise HTTPException(422, "Unsupported goal predicate field")
    with connection() as db:
        tasks = [serialize(r) for r in db.execute("SELECT * FROM tasks ORDER BY id")]
    matches = [x for x in tasks if all((set(v).issubset(x[k]) if k == "tags" and isinstance(v, list)
                                      else x[k] == v) for k, v in goal.task.items())]
    success = (len(matches) >= 1) if goal.count is None else (len(matches) == goal.count)
    return {"success": success, "matches": [t["id"] for t in matches], "match_count": len(matches)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
