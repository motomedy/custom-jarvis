import os
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

MIC_INDEX = 2
TRIGGER_WORD = "jarvis"
CONVERSATION_TIMEOUT = 30  # seconds of inactivity before exiting conversation mode

logging.basicConfig(level=logging.DEBUG)  # logging

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



# TTS engine setup (initialize once)
tts_engine = pyttsx3.init()
logging.debug("[TTS] pyttsx3 engine initialized.")
# Set a specific English female voice for reliability
voices = tts_engine.getProperty("voices")
logging.debug(f"[TTS] Available voices:")
for v in voices:
    logging.debug(f"- {v.name} ({v.id}) [{v.languages}]")
selected = False
# Try to select 'laura' voice first
for voice in voices:
    if "laura" in voice.name.lower() and ("en" in str(voice.languages).lower() or "english" in voice.name.lower()):
        tts_engine.setProperty("voice", voice.id)
        logging.debug(f"[TTS] Using LAura voice: {voice.name}")
        selected = True
        break
# If not found, try other preferred English female voices
if not selected:
    preferred_names = ["samantha", "karen", "victoria", "fiona", "serena", "martha", "tessa", "moira", "joana", "luciana", "allison", "ava", "susan"]
    for name in preferred_names:
        for voice in voices:
            if name in voice.name.lower() and ("en" in str(voice.languages).lower() or "english" in voice.name.lower()):
                tts_engine.setProperty("voice", voice.id)
                logging.debug(f"[TTS] Using English female voice: {voice.name}")
                selected = True
                break
        if selected:
            break
# Fallback: pick any English female voice
if not selected:
    for voice in voices:
        if ("female" in voice.name.lower() or "woman" in voice.name.lower()) and ("en" in str(voice.languages).lower() or "english" in voice.name.lower()):
            tts_engine.setProperty("voice", voice.id)
            logging.debug(f"[TTS] Using fallback English female voice: {voice.name}")
            selected = True
            break
# If still not found, use the default voice
if not selected:
    logging.debug("[TTS] No English female voice found, using default.")
tts_engine.setProperty("rate", 180)
tts_engine.setProperty("volume", 1.0)


# TTS background thread setup
tts_queue = queue.Queue()

def tts_worker():
    while True:
        text = tts_queue.get()
        try:
            if text is None:
                break
            post("status", "speaking")
            post("log", ("jarvis", text))
            logging.info("[STATE] TTS starting.")
            try:
                logging.debug(f"[TTS] Speaking: {text}")
                tts_engine.say(text)
                logging.debug("[TTS] Called engine.say()")
                tts_engine.runAndWait()
                logging.debug("[TTS] Called engine.runAndWait()")
                time.sleep(0.3)
            except Exception as e:
                logging.exception("❌ TTS failed:")
                # Attempt to re-initialize the TTS engine if it fails
                try:
                    global tts_engine
                    tts_engine = pyttsx3.init()
                    logging.info("[TTS] pyttsx3 engine re-initialized after failure.")
                except Exception as reinit_e:
                    logging.exception("[TTS] Failed to re-initialize pyttsx3 engine:")
            finally:
                logging.info("[STATE] TTS finished.")
                post("status", "idle")
        except Exception as fatal_e:
            logging.exception("[TTS] Fatal error in TTS worker loop:")
        finally:
            tts_queue.task_done()

tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def speak_text(text: str):
    tts_queue.put(text)


# Main interaction loop
def write():
    conversation_mode = False
    last_interaction_time = None


    try:
        resource_log_interval = 30  # seconds
        last_resource_log = time.time()
        while True:
            try:
                with sr.Microphone(device_index=MIC_INDEX) as source:
                    logging.info("[STATE] Microphone opened.")
                    recognizer.adjust_for_ambient_noise(source)
                    if not conversation_mode:
                        post("status", "idle")
                        logging.info("🎤 Listening for wake word...")
                        audio = recognizer.listen(source, timeout=10)
                        transcript = recognizer.recognize_google(audio) # type: ignore
                        logging.info(f"🗣 Heard: {transcript}")

                        if TRIGGER_WORD.lower() in transcript.lower():
                            logging.info(f"🗣 Triggered by: {transcript}")
                            # Wake word detected, entering convo mode
                            post("log", ("user", transcript))
                            logging.info("[STATE] Entering conversation mode.")
                            speak_text("Yes sir?")
                            conversation_mode = True
                            last_interaction_time = time.time()
                        else:
                            logging.debug("Wake word not detected, continuing...")
                    else:
                        post("status", "listening")
                        logging.info("🎤 Listening for next command...")
                        audio = recognizer.listen(source, timeout=10)
                        command = recognizer.recognize_google(audio) # type: ignore
                        logging.info(f"📥 Command: {command}")
                        post("log", ("user", command))
                        post("status", "thinking")

                        logging.info("🤖 Sending command to agent...")
                        response = executor.invoke({"input": command})
                        content = response["output"]
                        logging.info(f"✅ Agent responded: {content}")

                        print("Jarvis:", content)
                        speak_text(content)
                        last_interaction_time = time.time()

                        if last_interaction_time is not None and time.time() - last_interaction_time > CONVERSATION_TIMEOUT:
                            logging.info("[STATE] Exiting conversation mode due to timeout.")
                            conversation_mode = False
                    logging.info("[STATE] Microphone closed.")

            except sr.WaitTimeoutError:
                logging.warning("⚠️ Timeout waiting for audio.")
                if (
                    conversation_mode
                    and last_interaction_time is not None
                    and time.time() - last_interaction_time > CONVERSATION_TIMEOUT
                ):
                    logging.info(
                        "⌛ No input in conversation mode. Returning to wake word mode."
                    )
                    conversation_mode = False
                # Add a short delay after timeout in conversation mode
                if conversation_mode:
                    time.sleep(1)
            except sr.UnknownValueError:
                logging.warning("⚠️ Could not understand audio.")
                # Add a short delay after failed recognition in conversation mode
                if conversation_mode:
                    time.sleep(1)
            except Exception as e:
                logging.exception("❌ Error during recognition or tool call:")
                time.sleep(1)
            # Step 1: Add a small sleep to prevent high CPU usage
            time.sleep(0.1)

            # Step 5: Periodically log CPU and memory usage
            now = time.time()
            if now - last_resource_log > resource_log_interval:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                logging.info(f"[RESOURCE] CPU: {cpu}%, Memory: {mem.percent}% used ({mem.used // (1024*1024)}MB/{mem.total // (1024*1024)}MB)")
                last_resource_log = now

    except Exception as e:
        logging.exception("❌ Critical error in main loop:")


if __name__ == "__main__":
    write()
