# --- Imports ---
import os
import sys
import psutil
import logging
import time
import threading
import queue
import subprocess
from dotenv import load_dotenv
import speech_recognition as sr
from langchain_ollama import ChatOllama, OllamaLLM
from langchain_core.messages import HumanMessage
from langchain.agents import AgentExecutor, create_tool_calling_agent
# memory context
from memory import build_memory_context
from langchain_core.prompts import ChatPromptTemplate
# importing tools
from tools.time import get_time
from tools.OCR import read_text_from_latest_image
from tools.arp_scan import arp_scan_terminal
from tools.duckduckgo import duckduckgo_search_tool
from tools.matrix import matrix_mode
from tools.screenshot import take_screenshot
from tools.todo import add_todo, remove_todo, complete_todo, list_todos
load_dotenv()
try:
    from jarvis_gui import post
except ImportError:
    def post(event, data=None): pass

# --- Flask Web Server ---
from flask import Flask, request, jsonify, send_from_directory

# --- Config ---
PORT = int(os.getenv("JARVIS_PORT", 8340))

# --- LangChain Agent Setup ---

def select_macbook_microphone():
    mics = sr.Microphone.list_microphone_names()
    for idx, name in enumerate(mics):
        if "macbook air microphone" in name.lower():
            print(f"Auto-selected MacBook Air Microphone at index {idx}")
            return idx
    print("MacBook Air Microphone not found. Defaulting to index 0.")
    return 0

# --- Voice CLI Config ---
MIC_INDEX = select_macbook_microphone()
TRIGGER_WORD = "jarvis"
CONVERSATION_TIMEOUT = 120  # seconds of inactivity before exiting conversation mode
logging.basicConfig(level=os.environ.get("JARVIS_LOGLEVEL", "WARNING"))
recognizer = sr.Recognizer()

# --- LLM Agent ---
llm = ChatOllama(model="qwen3:1.7b", reasoning=False)  # Reverted to available model

tools = [get_time, arp_scan_terminal, read_text_from_latest_image, duckduckgo_search_tool, matrix_mode, take_screenshot, add_todo, remove_todo, complete_todo, list_todos]
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are Jarvis, an intelligent, conversational AI assistant. Your goal is to be helpful, friendly, and informative. You can respond in natural, human-like language and use tools when needed to answer questions more accurately. Always explain your reasoning simply when appropriate, and keep your responses conversational and concise."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])
agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


# --- Flask App ---
from flask import abort
import pathlib
BASE_DIR = "/Users/ahmedmansi/Jarvis_ollama"
app = Flask(__name__, static_folder="frontend/public", static_url_path="")
def safe_path(rel_path):
    # Prevent directory traversal
    full = os.path.abspath(os.path.join(BASE_DIR, rel_path))
    if not full.startswith(os.path.abspath(BASE_DIR)):
        abort(403)
    return full

# List files in BASE_DIR
@app.route("/api/files", methods=["GET"])
def list_files():
    files = []
    for p in pathlib.Path(BASE_DIR).glob("**/*"):
        if p.is_file():
            files.append(str(p.relative_to(BASE_DIR)))
    return {"files": files}

# Read a file
@app.route("/api/files/<path:relpath>", methods=["GET"])
def read_file(relpath):
    path = safe_path(relpath)
    if not os.path.isfile(path):
        abort(404)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"content": content}

# Write/overwrite a file
@app.route("/api/files/<path:relpath>", methods=["POST"])
def write_file(relpath):
    path = safe_path(relpath)
    data = request.get_json()
    content = data.get("content", "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "ok"}

@app.route("/api/ask", methods=["POST"])
def api_ask():
    try:
        data = request.get_json()
        print(f"[API] Received data: {data}")
        user_input = data.get("input", "") if data else ""
        if not user_input:
            print("[API] Missing input!")
            return jsonify({"error": "Missing input"}), 400
        # Automatic memory: store user's name if stated
        import re
        from memory import remember
        name_match = re.match(r".*my name is ([A-Za-z0-9_\- ]+)[.!]?", user_input, re.IGNORECASE)
        if name_match:
            user_name = name_match.group(1).strip()
            remember(f"User's name is {user_name}", mem_type="person", source="api_ask")
        # Inject memory context
        memory_context = build_memory_context(user_input)
        full_input = f"[CONTEXT]\n{memory_context}\n[USER]\n{user_input}" if memory_context else user_input
        response = executor.invoke({"input": full_input})
        print(f"[API] Agent response: {response}")
        output = response.get('output', '')
        return jsonify({"output": output})
    except Exception as e:
        print(f"[API] Exception: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def serve_index():
    # Serve a minimal HTML if frontend not present
    index_path = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return "<h1>JARVIS Portal</h1><form id='f'><input name='q'><button>Ask</button></form><pre id='r'></pre><script>f.onsubmit=e=>{e.preventDefault();fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:f.q.value})}).then(r=>r.json()).then(j=>r.innerText=j.output)}</script>"

@app.route("/api/health")
def health():
    return {"status": "ok"}

# Tool list
tools = [get_time, arp_scan_terminal, read_text_from_latest_image, duckduckgo_search_tool, matrix_mode, take_screenshot, add_todo, remove_todo, complete_todo, list_todos]

# Tool-calling prompt
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are Jarvis, an intelligent, conversational AI assistant. Your goal is to be helpful, friendly, and informative. You can respond in natural, human-like language and use tools when needed to answer questions more accurately. Always explain your reasoning simply when appropriate, and keep your responses conversational and concise.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

# Agent + executor
agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)





# --- Robust TTS Worker for macOS (thread-safe, new engine per utterance) ---

# --- macOS TTS using 'say' command ---
def speak_text(text: str):
    """Speak text using macOS 'say' command for reliable TTS."""
    try:
        logging.debug(f"[TTS] Speaking: {text}")
        post("status", "speaking")
        post("log", ("jarvis", text))
        # Use 'Samantha' voice if available, fallback to default
        subprocess.run(["say", "-v", "Samantha", text], check=True)
    except Exception as e:
        logging.exception("❌ TTS failed:")
    finally:
        post("status", "idle")

def safe_tts_join():
    # No-op for macOS 'say' command (blocking)
    pass


# Main interaction loop

# --- Voice CLI Main Loop ---
def write():
    """Testable main loop: processes up to 5 commands or failed attempts, logs resources, and exits cleanly."""
    resource_log_interval = 30  # seconds
    last_resource_log = time.time()
    failed_attempts = 0
    MAX_FAILED_ATTEMPTS = 5
    commands_processed = 0
    MAX_COMMANDS = 5
    print("\n--- Jarvis is now running in voice mode. Speak your command after the beep (Ctrl+C to exit) ---")
    recognizer = sr.Recognizer()
    while True:
        try:
            mic = sr.Microphone(device_index=MIC_INDEX)
            with mic as source:
                print("Listening...")
                recognizer.adjust_for_ambient_noise(source)
                print("Beep!")
                audio = recognizer.listen(source)
            try:
                user_command = recognizer.recognize_google(audio)
                print(f"You said: {user_command}")
            except sr.UnknownValueError:
                print("Sorry, I did not catch that. Please try again.")
                continue
            except sr.RequestError as e:
                print(f"Speech recognition error: {e}")
                continue
            if not user_command:
                continue
            response = executor.invoke({"input": user_command})
            output = response.get('output', '')
            print(f"DEBUG: Raw response: {response}")
            if not output or not isinstance(output, str):
                output = "Sorry, I did not understand that command."
            print(f"Jarvis: {output}")
            # --- Save memory: user command and assistant reply ---
            try:
                from memory import remember
                remember(user_command, mem_type="user_command")
                remember(output, mem_type="assistant_reply")
            except Exception as mem_err:
                print(f"[Memory Error] {mem_err}")
            del mic
            time.sleep(1.0)  # Increased delay to reduce CPU load
            speak_text(output)
            safe_tts_join()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Jarvis.")
            break
        except Exception as e:
            print(f"Error processing command: {e}")
    safe_tts_join()

# Ensure the test runs when script is executed
if __name__ == "__main__":
    mode = os.environ.get("JARVIS_MODE", "web")
    if mode == "voice":
        write()
    else:
        print(f"Starting JARVIS web server on http://localhost:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=True)
