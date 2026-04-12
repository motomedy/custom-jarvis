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
CONVERSATION_TIMEOUT = 120  # seconds of inactivity before exiting conversation mode

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
def write():
    """Testable main loop: processes up to 5 commands or failed attempts, logs resources, and exits cleanly."""
    resource_log_interval = 30  # seconds
    last_resource_log = time.time()
    failed_attempts = 0
    MAX_FAILED_ATTEMPTS = 5
    commands_processed = 0
    MAX_COMMANDS = 5
    # After test commands, enter interactive mode
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
            # Ensure mic is fully released before TTS
            del mic
            time.sleep(0.2)  # Let CoreAudio settle
            speak_text(output)
            safe_tts_join()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting Jarvis.")
                break
            except Exception as e:
                print(f"Error processing command: {e}")
        # Wait to ensure all TTS output is played before exiting
        safe_tts_join()

# Ensure the test runs when script is executed
if __name__ == "__main__":
    write()
