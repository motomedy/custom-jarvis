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

def select_microphone():
    print("Available microphone devices:")
    mics = sr.Microphone.list_microphone_names()
    for idx, name in enumerate(mics):
        print(f"  Index {idx}: {name}")
    while True:
        try:
            idx = int(input("Select microphone device index: "))
            if 0 <= idx < len(mics):
                print(f"Selected: {mics[idx]}")
                return idx
            else:
                print("Invalid index. Try again.")
        except Exception:
            print("Please enter a valid integer.")

MIC_INDEX = select_microphone()
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
# Always use Samantha as the default TTS voice if available
voices = tts_engine.getProperty("voices")
selected = False
for voice in voices:
    if "samantha" in voice.name.lower():
        tts_engine.setProperty("voice", voice.id)
        logging.info(f"[TTS] Using Samantha voice: {voice.name}")
        selected = True
        break
if not selected:
    for voice in voices:
        if ("female" in voice.name.lower() or "woman" in voice.name.lower()) and ("en" in str(voice.languages).lower() or "english" in voice.name.lower()):
            tts_engine.setProperty("voice", voice.id)
            logging.info(f"[TTS] Using fallback English female voice: {voice.name}")
            selected = True
            break
if not selected:
    logging.warning("[TTS] No English female voice found, using default.")
tts_engine.setProperty("rate", 180)
tts_engine.setProperty("volume", 1.0)


# TTS background thread setup
tts_queue = queue.Queue()

def tts_worker():
    global tts_engine
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


    global MIC_INDEX
    try:
        resource_log_interval = 30  # seconds
        last_resource_log = time.time()
        fail_count = 0
        MAX_FAILS = 5
        # Calibrate for background noise ONCE at startup
        with sr.Microphone(device_index=MIC_INDEX) as source:
            logging.info("[STATE] Microphone opened for initial calibration.")
            speak_text("Calibrating for background noise, please wait.")
            tts_queue.join()
            recognizer.adjust_for_ambient_noise(source, duration=1)
        logging.info("[STATE] Calibration complete.")
        calibrated = True
        MAX_UNRECOGNIZED_ATTEMPTS = 3
        unrecognized_attempts = 0
        EXIT_COMMANDS = ["exit", "quit", "stop listening", "goodbye"]
        while True:
            try:
                mics = sr.Microphone.list_microphone_names()
                if MIC_INDEX >= len(mics):
                    logging.error(f"Selected microphone index {MIC_INDEX} not available. Available devices:")
                    for idx, name in enumerate(mics):
                        logging.error(f"  Index {idx}: {name}")
                    print("[JARVIS] Microphone device not found. Please select a new device.")
                    speak_text("Microphone device not found. Please select a new device.")
                    tts_queue.join()
                    MIC_INDEX = select_microphone()
                    # Recalibrate after device change
                    with sr.Microphone(device_index=MIC_INDEX) as source:
                        logging.info("[STATE] Microphone opened for re-calibration.")
                        speak_text("Calibrating for background noise, please wait.")
                        tts_queue.join()
                        recognizer.adjust_for_ambient_noise(source, duration=1)
                    logging.info("[STATE] Calibration complete.")
                    continue
                if not conversation_mode:
                    post("status", "idle")
                    logging.info("🎤 Listening for wake word...")
                    speak_text("Listening for wake word.")
                    tts_queue.join()
                    try:
                        with sr.Microphone(device_index=MIC_INDEX) as source:
                            logging.info("[STATE] Microphone opened.")
                            audio = recognizer.listen(source, timeout=30, phrase_time_limit=8)
                        try:
                            transcript = recognizer.recognize_google(audio) # type: ignore
                            logging.info(f"🗣 Heard: {transcript}")
                            # Fuzzy wake word match
                            if any(w in transcript.lower() for w in [TRIGGER_WORD.lower(), "jarv", "jervis"]):
                                logging.info(f"🗣 Triggered by: {transcript}")
                                post("log", ("user", transcript))
                                logging.info("[STATE] Entering conversation mode.")
                                speak_text("Yes sir?")
                                tts_queue.join()
                                time.sleep(0.5)
                                conversation_mode = True
                                last_interaction_time = time.time()
                            else:
                                logging.debug("Wake word not detected, continuing...")
                                speak_text("Wake word not detected. Listening again.")
                                tts_queue.join()
                        except sr.UnknownValueError:
                            logging.warning("Wake word not recognized (UnknownValueError). Prompting user to try again.")
                            # Save failed audio for debugging
                            import wave, datetime
                            nowstr = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            with wave.open(f"wakeword_fail_{nowstr}.wav", "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(16000)
                                wf.writeframes(audio.get_raw_data())
                            speak_text("Didn't catch that. Please say 'Jarvis' again.")
                            tts_queue.join()
                        except Exception as e:
                            logging.exception("❌ Error during wake word recognition (inner):")
                            speak_text("Error during wake word recognition. Please try again.")
                            tts_queue.join()
                    except AssertionError as e:
                        logging.error(f"Microphone assertion error: {e}")
                        speak_text("Microphone error. Please check your device.")
                        tts_queue.join()
                        time.sleep(1)
                        continue
                    except AttributeError as e:
                        logging.error(f"Microphone attribute error: {e}")
                        speak_text("Microphone error. Please check your device.")
                        tts_queue.join()
                        time.sleep(1)
                        continue
                    except Exception as e:
                        logging.exception("❌ Error during wake word recognition (outer):")
                        speak_text("Error during wake word recognition. Please try again.")
                        tts_queue.join()
                        time.sleep(1)
                        continue
                # --- New logic: Listen for user command in conversation mode ---
                elif conversation_mode:
                    post("status", "listening")
                    logging.info("🎤 Listening for user command in conversation mode...")
                    speak_text("Listening for your command.")
                    tts_queue.join()
                    try:
                        with sr.Microphone(device_index=MIC_INDEX) as source:
                            logging.info("[STATE] Microphone opened.")
                            audio = recognizer.listen(source, timeout=30, phrase_time_limit=10)
                        user_command = recognizer.recognize_google(audio)
                        logging.info(f"🗣 User command: {user_command}")
                        post("log", ("user", user_command))
                        # Check for exit command
                        if any(cmd in user_command.lower() for cmd in EXIT_COMMANDS):
                            speak_text("Exiting conversation mode. Say 'Jarvis' to wake me up again.")
                            tts_queue.join()
                            conversation_mode = False
                            unrecognized_attempts = 0
                            continue
                        # Here you can process the user_command with your agent/executor
                        response = executor.invoke({"input": user_command})
                        speak_text(str(response["output"]))
                        tts_queue.join()
                        last_interaction_time = time.time()
                        unrecognized_attempts = 0
                    except sr.WaitTimeoutError:
                        logging.info("⌛ No input in conversation mode. Returning to wake word mode.")
                        speak_text("No input detected. Returning to wake word mode.")
                        tts_queue.join()
                        conversation_mode = False
                        unrecognized_attempts = 0
                    except sr.UnknownValueError:
                        logging.warning("⚠️ Could not understand audio in conversation mode.")
                        unrecognized_attempts += 1
                        if unrecognized_attempts >= MAX_UNRECOGNIZED_ATTEMPTS:
                            speak_text("Too many failed attempts. Returning to wake word mode.")
                            tts_queue.join()
                            conversation_mode = False
                            unrecognized_attempts = 0
                        else:
                            speak_text("Sorry, I didn't catch that. Please repeat.")
                            tts_queue.join()
                            last_interaction_time = time.time()
                    except AssertionError as e:
                        logging.error(f"Microphone assertion error: {e}")
                        speak_text("Microphone error. Returning to wake word mode.")
                        tts_queue.join()
                        conversation_mode = False
                        unrecognized_attempts = 0
                        time.sleep(1)
                        continue
                    except AttributeError as e:
                        logging.error(f"Microphone attribute error: {e}")
                        speak_text("Microphone error. Returning to wake word mode.")
                        tts_queue.join()
                        conversation_mode = False
                        unrecognized_attempts = 0
                        time.sleep(1)
                        continue
                    except Exception as e:
                        logging.exception("❌ Error during user command recognition or processing:")
                        speak_text("Sorry, something went wrong.")
                        tts_queue.join()
                        conversation_mode = False
                        unrecognized_attempts = 0
                if (
                    conversation_mode
                    and last_interaction_time is not None
                    and time.time() - last_interaction_time > CONVERSATION_TIMEOUT
                ):
                    logging.info(
                        "⌛ No input in conversation mode. Returning to wake word mode."
                    )
                    conversation_mode = False
                if conversation_mode:
                    time.sleep(1)
            except sr.UnknownValueError:
                logging.warning("⚠️ Could not understand audio.")
                if conversation_mode:
                    time.sleep(1)
            except Exception as e:
                logging.exception("❌ Error during recognition or tool call:")
                time.sleep(1)
            time.sleep(0.1)

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
