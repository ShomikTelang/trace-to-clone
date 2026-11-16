"""Generate a bounded Kanban clone from a checked application spec.

This first generator supports the Kanban/task schema only. Extending to arbitrary
applications requires additional runtime templates or generated implementations.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "kanban_runtime"


def validate_spec(spec):
    mandatory = ["app_id", "title", "columns", "priorities", "default_column", "default_priority"]
    for key in mandatory:
        if key not in spec:
            raise ValueError(f"missing spec field: {key}")
    ids = [c["id"] for c in spec["columns"]]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("columns must have unique non-empty IDs")
    if spec["default_column"] not in ids:
        raise ValueError("default_column is not in columns")
    if spec["default_priority"] not in spec["priorities"]:
        raise ValueError("default_priority is not in priorities")
    for task in spec.get("initial_tasks", []):
        if task.get("column", spec["default_column"]) not in ids:
            raise ValueError("seed task has an unknown column")
        if task.get("priority", spec["default_priority"]) not in spec["priorities"]:
            raise ValueError("seed task has an unknown priority")
    return spec


def generate(spec_path: str, output: str, force: bool = False) -> Path:
    spec = validate_spec(json.loads(Path(spec_path).read_text()))
    destination = Path(output).resolve()
    if destination.exists():
        if not force:
            raise FileExistsError(f"{destination} already exists; pass --force to replace")
        shutil.rmtree(destination)
    shutil.copytree(TEMPLATE, destination)
    (destination / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    return destination
