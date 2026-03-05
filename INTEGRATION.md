# 🔌 Wiring main.py → jarvis_gui.py

## What you need to change in your existing main.py

The GUI communicates via a single function: `post(event, data)`
You just sprinkle these calls into your existing voice loop.

### 1. At the top of main.py, add:
```python
# Import the GUI event poster (only when running with GUI)
try:
    from jarvis_gui import post
except ImportError:
    def post(event, data=""): pass   # no-op when running headless
```

---

### 2. Wire up your speak() function
```python
def speak(text):
    post("log", ("jarvis", text))    # ← show in convo log
    post("status", "speaking")       # ← pulse ring goes blue
    engine.say(text)
    engine.runAndWait()
    post("status", "idle")           # ← back to idle
```

---

### 3. Wire up your listen loop
```python
# When waiting for wake word:
post("status", "idle")

# When wake word detected, entering convo mode:
post("status", "listening")

# When recording user command:
post("log", ("user", recognized_text))

# When calling the LLM:
post("status", "thinking")
```

---

### 4. Add tasks from voice (optional)
If Jarvis should be able to add todo items by voice:
```python
# e.g. user says "Jarvis, add buy milk to my todo list"
post("todo_add", "Buy milk")
```

---

### 5. In jarvis_gui.py, replace the run_jarvis() stub:
```python
def run_jarvis():
    # Import and run your main loop here
    import main   # or paste the contents directly
```

---

## Installing the one new dependency
```bash
pip install psutil
```
That's it. psutil is tiny (~1MB) and handles RAM/CPU monitoring.

---

## Running
```bash
python jarvis_gui.py
```
The GUI window opens, then spawns your Jarvis voice loop in the background.

---

## Event Reference
| post(event, data)          | Effect                              |
|----------------------------|-------------------------------------|
| post("status", "idle")     | Dim ring, IDLE status bar           |
| post("status", "listening")| Green pulsing ring                  |
| post("status", "thinking") | Yellow pulsing ring                 |
| post("status", "speaking") | Blue pulsing ring                   |
| post("status", "error")    | Red pulsing ring                    |
| post("log", ("user", txt)) | Adds green YOUR message to log      |
| post("log", ("jarvis", txt))| Adds blue JARVIS message to log    |
| post("todo_add", "text")   | Adds item to todo list + saves JSON |
| post("model", "llama3:8b") | Updates model name in status bar    |