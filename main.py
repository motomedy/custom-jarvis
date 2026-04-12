import os
import sys
import psutil
import logging
import time
import threading
import queue
import pyttsx3
from dotenv import load_dotenv
import speech_recognition as sr
from langchain_ollama import ChatOllama, OllamaLLM

# from langchain_openai import ChatOpenAI # if you want to use openai
from langchain_core.messages import HumanMessage
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

# importing tools
from tools.time import get_time
from tools.OCR import read_text_from_latest_image
from tools.arp_scan import arp_scan_terminal
from tools.duckduckgo import duckduckgo_search_tool
from tools.matrix import matrix_mode
from tools.screenshot import take_screenshot

# Imports for the todos
from tools.todo import add_todo, remove_todo, complete_todo, list_todos

load_dotenv()

try:
    from jarvis_gui import post
except ImportError:
    def post(event, data=None): pass

def select_macbook_microphone():
    mics = sr.Microphone.list_microphone_names()
    for idx, name in enumerate(mics):
        if "macbook air microphone" in name.lower():
            print(f"Auto-selected MacBook Air Microphone at index {idx}")
            return idx
    print("MacBook Air Microphone not found. Defaulting to index 0.")
    return 0

MIC_INDEX = select_macbook_microphone()
TRIGGER_WORD = "jarvis"
CONVERSATION_TIMEOUT = 30  # seconds of inactivity before exiting conversation mode

logging.basicConfig(level=os.environ.get("JARVIS_LOGLEVEL", "WARNING"))  # Default to WARNING, override with env var

# api_key = os.getenv("OPENAI_API_KEY") removed because it's not needed for ollama
# org_id = os.getenv("OPENAI_ORG_ID") removed because it's not needed for ollama

recognizer = sr.Recognizer()

# Initialize LLM
llm = ChatOllama(model="qwen3:1.7b", reasoning=False)

# llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, organization=org_id) for openai

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
TTS_VOICE_NAME = "Samantha"  # macOS voice

class TTSWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                text = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                engine = pyttsx3.init()
                # Select Samantha voice
                selected = False
                for v in engine.getProperty('voices'):
                    if TTS_VOICE_NAME.lower() in v.name.lower():
                        engine.setProperty('voice', v.id)
                        selected = True
                        logging.info(f"[TTS] Using Samantha voice: {v.name}")
                        break
                if not selected:
                    for v in engine.getProperty('voices'):
                        if ("female" in v.name.lower() or "woman" in v.name.lower()) and ("en" in str(v.languages).lower() or "english" in v.name.lower()):
                            engine.setProperty('voice', v.id)
                            logging.info(f"[TTS] Using fallback English female voice: {v.name}")
                            selected = True
                            break
                if not selected:
                    logging.warning("[TTS] No English female voice found, using default.")
                engine.setProperty("rate", 140)
                engine.setProperty("volume", 1.0)
                logging.debug(f"[TTS] Speaking: {text}")
                post("status", "speaking")
                post("log", ("jarvis", text))
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                time.sleep(0.1)
            except Exception as e:
                logging.exception("❌ TTS failed:")
            finally:
                logging.info("[STATE] TTS finished.")
                post("status", "idle")
                self.queue.task_done()

    def speak(self, text):
        self.queue.put(text)

    def stop(self):
        self._stop_event.set()

# Instantiate and start the TTS worker
tts_worker = TTSWorker()
tts_worker.start()

def speak_text(text: str):
    tts_worker.speak(text)

def safe_tts_join():
    # Only join if the thread is alive and not stopping
    if tts_worker.is_alive() and not tts_worker._stop_event.is_set():
        try:
            tts_worker.queue.join()
        except Exception as e:
            logging.warning(f"[TTS] Exception during queue join: {e}")


# Main interaction loop
def write():
    """Testable main loop: processes up to 5 commands or failed attempts, logs resources, and exits cleanly."""
    resource_log_interval = 30  # seconds
    last_resource_log = time.time()
    failed_attempts = 0
    MAX_FAILED_ATTEMPTS = 5
    commands_processed = 0
    MAX_COMMANDS = 5
    test_commands = [
        "Jarvis",
        "Phased AI Assistant Build: 1. Learn Python, APIs, data structures, LLM basics. 2. Build simple chat loop, API calls, command routing. 3. Make a single-purpose assistant (e.g., search or scheduling). 4. Add session and long-term memory; define assistant identity (role, tone, permissions). 5. Implement tool orchestration (planning, delegation, reversible actions). 6. Add security: least-privilege, human approval, encryption, prompt-injection defense, audit logging. 7. Add observability: tracing, metrics, structured logs, failure/adversarial testing. 8. Scale to new workflows, reuse memory/policy/orchestration, add voice/multi-agent if stable. Recommended learning order: Python → APIs → prompt design → memory → tool use → security → orchestration/observability."
    ]
    try:
        for user_command in test_commands:
            print(f"Processing: {user_command}")
            try:
                response = executor.invoke({"input": user_command})
                output = response.get('output', '')
                print(f"DEBUG: Raw response: {response}")
                if not output or not isinstance(output, str):
                    output = "Sorry, I did not understand that command."
                print(f"Jarvis: {output}")
                speak_text(output)
                safe_tts_join()
                commands_processed += 1
            except Exception as e:
                print(f"Error processing command: {e}")
                failed_attempts += 1
            now = time.time()
            if now - last_resource_log > resource_log_interval:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                logging.info(f"[RESOURCE] CPU: {cpu}%, Memory: {mem.percent}% used ({mem.used // (1024*1024)}MB/{mem.total // (1024*1024)}MB)")
                last_resource_log = now
            if failed_attempts >= MAX_FAILED_ATTEMPTS:
                print("Too many failed attempts. Exiting test.")
                break
    finally:
        # Wait to ensure all TTS output is played before exiting
        time.sleep(2)
        if tts_worker.is_alive():
            tts_worker.stop()

# Ensure the test runs when script is executed
if __name__ == "__main__":
    write()
