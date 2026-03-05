"""
tools/todo.py — Jarvis Todo List Tools

Provides 4 LangChain tools the LLM can call via voice:
  • add_todo      — "Jarvis, add buy milk to my list"
  • remove_todo   — "Jarvis, remove buy milk from my list"
  • complete_todo — "Jarvis, mark buy milk as done"
  • list_todos    — "Jarvis, what's on my list?"

Reads/writes jarvis_todos.json (same file the GUI uses),
and pushes live updates to the GUI via post().
"""

import os
import json
from langchain.tools import tool

# ── JSON store ────────────────────────────────────────────────────────────────
# Stored next to main.py (one level up from tools/)
TODO_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jarvis_todos.json")

def _load() -> list:
    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save(todos: list):
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=2)

# ── GUI bridge (no-op if GUI isn't running) ───────────────────────────────────
try:
    from jarvis_gui import post
except ImportError:
    def post(event, data=None): pass


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def add_todo(task: str) -> str:
    """
    Add a new task to the todo list.
    Use this when the user wants to remember something or add an item to their list.
    Input should be the task description, e.g. 'buy milk' or 'call dentist'.
    """
    task = task.strip()
    if not task:
        return "I didn't catch what you'd like to add. Could you repeat that?"

    todos = _load()

    # Avoid exact duplicates (case-insensitive)
    existing = [t["text"].lower() for t in todos]
    if task.lower() in existing:
        return f"'{task}' is already on your list."

    todos.append({"text": task, "done": False})
    _save(todos)

    post("todo_add", task)   # live GUI update
    return f"Got it! I've added '{task}' to your list."


@tool
def remove_todo(task: str) -> str:
    """
    Remove a task from the todo list by name.
    Use this when the user wants to delete or remove an item.
    Input should be the task name or a close match, e.g. 'buy milk'.
    """
    task = task.strip().lower()
    todos = _load()

    # Find best match (exact first, then partial)
    match_idx = None
    for i, t in enumerate(todos):
        if t["text"].lower() == task:
            match_idx = i
            break
    if match_idx is None:
        for i, t in enumerate(todos):
            if task in t["text"].lower():
                match_idx = i
                break

    if match_idx is None:
        return f"I couldn't find '{task}' on your list. Try listing your tasks to see what's there."

    removed = todos.pop(match_idx)
    _save(todos)

    post("todo_remove", removed["text"])   # live GUI update
    return f"Removed '{removed['text']}' from your list."


@tool
def complete_todo(task: str) -> str:
    """
    Mark a task as completed/done on the todo list.
    Use this when the user says they've finished or completed something.
    Input should be the task name, e.g. 'buy milk'.
    """
    task = task.strip().lower()
    todos = _load()

    match_idx = None
    for i, t in enumerate(todos):
        if t["text"].lower() == task:
            match_idx = i
            break
    if match_idx is None:
        for i, t in enumerate(todos):
            if task in t["text"].lower():
                match_idx = i
                break

    if match_idx is None:
        return f"I couldn't find '{task}' on your list."

    if todos[match_idx]["done"]:
        return f"'{todos[match_idx]['text']}' is already marked as done."

    todos[match_idx]["done"] = True
    _save(todos)

    post("todo_complete", todos[match_idx]["text"])   # live GUI update
    return f"Marked '{todos[match_idx]['text']}' as done. Nice work!"


@tool
def list_todos(filter: str = "all") -> str:
    """
    Read and return the current todo list.
    Use this when the user asks what's on their list, what they need to do,
    or what tasks are pending.
    Input can be 'all', 'pending', or 'done' to filter results.
    """
    todos = _load()

    if not todos:
        return "Your todo list is empty."

    filter = filter.strip().lower()

    pending = [t for t in todos if not t["done"]]
    done    = [t for t in todos if t["done"]]

    if filter == "done":
        if not done:
            return "You haven't completed any tasks yet."
        lines = "\n".join(f"  ✓ {t['text']}" for t in done)
        return f"Completed tasks:\n{lines}"

    if filter == "pending":
        if not pending:
            return "You have no pending tasks — all done!"
        lines = "\n".join(f"  • {t['text']}" for t in pending)
        return f"Pending tasks:\n{lines}"

    # Default: all
    parts = []
    if pending:
        lines = "\n".join(f"  • {t['text']}" for t in pending)
        parts.append(f"Pending ({len(pending)}):\n{lines}")
    if done:
        lines = "\n".join(f"  ✓ {t['text']}" for t in done)
        parts.append(f"Completed ({len(done)}):\n{lines}")

    return "\n\n".join(parts)