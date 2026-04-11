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
                engine.setProperty("rate", 180)
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
    conversation_mode = False
    last_interaction_time = None


    global MIC_INDEX
    try:
        resource_log_interval = 30  # seconds
        last_resource_log = time.time()
        mic_fail_count = 0
        MAX_MIC_FAILS = 3
        # Calibrate for background noise ONCE at startup
        try:
            mics = sr.Microphone.list_microphone_names()
            if MIC_INDEX >= len(mics):
                logging.error(f"Selected microphone index {MIC_INDEX} not available. Available devices:")
                for idx, name in enumerate(mics):
                    logging.error(f"  Index {idx}: {name}")
                print("[JARVIS] Microphone device not found. Please select a new device.")
                speak_text("Microphone device not found. Please select a new device.")
                safe_tts_join()
                MIC_INDEX = select_macbook_microphone()
            # Always use context manager for microphone
            with sr.Microphone(device_index=MIC_INDEX) as source:
                logging.info("[STATE] Microphone opened for initial calibration.")
                speak_text("Calibrating for background noise, please wait.")
                safe_tts_join()
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                except AssertionError as e:
                    logging.critical(f"[MIC ERROR] Could not calibrate microphone: {e}")
                    print("[JARVIS] Microphone calibration failed. Please check your device and try again.")
                    speak_text("Microphone calibration failed. Please check your device and try again.")
                    safe_tts_join()
                    sys.exit(1)
        except Exception as e:
            logging.critical(f"[MIC ERROR] Exception during microphone calibration: {e}")
            print("[JARVIS] Microphone calibration failed due to an unexpected error.")
            speak_text("Microphone calibration failed due to an unexpected error.")
            safe_tts_join()
            sys.exit(1)
        logging.info("[STATE] Calibration complete.")
        calibrated = True
        MAX_UNRECOGNIZED_ATTEMPTS = 3
        unrecognized_attempts = 0
        EXIT_COMMANDS = ["exit", "quit", "stop listening", "goodbye"]
        SELF_TEST_COMMANDS = ["run a self-test", "self test", "diagnose", "check system"]

        # --- Refactored: Keep microphone open for each mode ---
        try:
            while True:
                mics = sr.Microphone.list_microphone_names()
                if MIC_INDEX >= len(mics):
                    logging.error(f"Selected microphone index {MIC_INDEX} not available. Available devices:")
                    for idx, name in enumerate(mics):
                        logging.error(f"  Index {idx}: {name}")
                    print("[JARVIS] Microphone device not found. Please select a new device.")
                    speak_text("Microphone device not found. Please select a new device.")
                    safe_tts_join()
                    if not conversation_mode:
                        post("status", "idle")
                        logging.info("🎤 Listening for wake word...")
                        speak_text("Listening for wake word.")
                        safe_tts_join()
                        try:
                            # Always use 'with' for microphone context
                            with sr.Microphone(device_index=MIC_INDEX) as source:
                                logging.info("[STATE] Microphone opened.")
                                try:
                                    audio = recognizer.listen(source, timeout=30, phrase_time_limit=8)
                                except Exception as e:
                                    audio = None
                                    logging.error(f"Microphone listen error: {e}")
                                    speak_text("Microphone error during listening. Please check your device.")
                                    safe_tts_join()
                                    mic_fail_count += 1
                                    time.sleep(1)
                                    continue
                                if audio is not None:
                                    try:
                                        transcript = recognizer.recognize_google(audio) # type: ignore
                                        logging.info(f"🗣 Heard: {transcript}")
                                        # Fuzzy wake word match
                                        if any(w in transcript.lower() for w in [TRIGGER_WORD.lower(), "jarv", "jervis"]):
                                            logging.info(f"🗣 Triggered by: {transcript}")
                                            post("log", ("user", transcript))
                                            logging.info("[STATE] Entering conversation mode.")
                                            speak_text("Yes sir?")
                                            safe_tts_join()
                                            time.sleep(0.5)
                                            conversation_mode = True
                                            last_interaction_time = time.time()
                                        else:
                                            logging.debug("Wake word not detected, continuing...")
                                            speak_text("Wake word not detected. Listening again.")
                                            safe_tts_join()
                                        mic_fail_count = 0
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
                                        safe_tts_join()
                                    except Exception as e:
                                        logging.exception("❌ Error during wake word recognition (inner):")
                                        speak_text("Error during wake word recognition. Please try again.")
                                        safe_tts_join()
                                        mic_fail_count += 1
                                else:
                                    logging.error("No audio captured from microphone.")
                                    speak_text("No audio captured. Please try again.")
                                    safe_tts_join()
                                    mic_fail_count += 1
                                    time.sleep(1)
                                    continue
                                # Error handling for microphone failures
                                if mic_fail_count >= MAX_MIC_FAILS:
                                    print("[JARVIS] Too many microphone errors. Please select a new device or check your hardware.")
                                    speak_text("Too many microphone errors. Please select a new device or check your hardware.")
                                    safe_tts_join()
                                    MIC_INDEX = select_macbook_microphone()
                                    mic_fail_count = 0
                                    continue
                        except (AssertionError, AttributeError) as e:
                            logging.error(f"Microphone error (outer): {e}")
                            speak_text("Critical microphone error. Please check your device and restart Jarvis.")
                            safe_tts_join()
                            break
                        except Exception as e:
                            logging.exception("❌ Error during wake word recognition (outer):")
                            speak_text("Error during wake word recognition. Please try again.")
                            safe_tts_join()
                            mic_fail_count += 1
                            time.sleep(1)
                            if mic_fail_count >= MAX_MIC_FAILS:
                                print("[JARVIS] Too many microphone errors. Please select a new device or check your hardware.")
                                speak_text("Too many microphone errors. Please select a new device or check your hardware.")
                                safe_tts_join()
                                MIC_INDEX = select_macbook_microphone()
                                mic_fail_count = 0
                            continue
                        safe_tts_join()
                        mic_fail_count += 1
                        time.sleep(1)
                        if mic_fail_count >= MAX_MIC_FAILS:
                            print("[JARVIS] Too many microphone errors. Please select a new device or check your hardware.")
                            speak_text("Too many microphone errors. Please select a new device or check your hardware.")
                            safe_tts_join()
                            MIC_INDEX = select_microphone()
                            mic_fail_count = 0
                        continue
                else:
                    post("status", "listening")
                    logging.info("🎤 Listening for user command in conversation mode...")
                    speak_text("Listening for your command.")
                    safe_tts_join()
                    try:
                        # Always use 'with' for microphone context
                        with sr.Microphone(device_index=MIC_INDEX) as source:
                            logging.info("[STATE] Microphone opened.")
                            try:
                                audio = recognizer.listen(source, timeout=30, phrase_time_limit=10)
                            except Exception as e:
                                audio = None
                                logging.error(f"Microphone listen error: {e}")
                                speak_text("Microphone error during listening. Returning to wake word mode.")
                                safe_tts_join()
                                conversation_mode = False
                                unrecognized_attempts = 0
                                time.sleep(1)
                                break
                            if audio is not None:
                                try:
                                    user_command = recognizer.recognize_google(audio)
                                    logging.info(f"🗣 User command: {user_command}")
                                    post("log", ("user", user_command))
                                    # Check for exit command
                                    if any(cmd in user_command.lower() for cmd in EXIT_COMMANDS):
                                        speak_text("Exiting conversation mode. Say 'Jarvis' to wake me up again.")
                                        safe_tts_join()
                                        conversation_mode = False
                                        unrecognized_attempts = 0
                                        continue
                                    # Self-test command
                                    if any(cmd in user_command.lower() for cmd in SELF_TEST_COMMANDS):
                                        speak_text("Running self-test. Checking TTS and microphone...")
                                        safe_tts_join()
                                        # TTS test
                                        try:
                                            set_tts_voice(tts_engine)
                                            tts_engine.say("This is a test of the Jarvis voice system. If you hear this, TTS is working.")
                                            tts_engine.runAndWait()
                                            tts_ok = True
                                        except Exception as e:
                                            tts_ok = False
                                        # Microphone test
                                        try:
                                            with sr.Microphone(device_index=MIC_INDEX) as test_source:
                                                speak_text("Testing microphone. Please say something after the beep.")
                                                safe_tts_join()
                                                import sys
                                                sys.stdout.write('\a')
                                                sys.stdout.flush()
                                                test_audio = recognizer.listen(test_source, timeout=5, phrase_time_limit=3)
                                                speak_text("Recording complete. Attempting recognition.")
                                                safe_tts_join()
                                                try:
                                                    result = recognizer.recognize_google(test_audio)
                                                    mic_ok = True
                                                except Exception:
                                                    mic_ok = False
                                        except Exception:
                                            mic_ok = False
                                        # Report
                                        if tts_ok and mic_ok:
                                            speak_text("Self-test complete. Both TTS and microphone are working correctly.")
                                        elif not tts_ok and mic_ok:
                                            speak_text("Microphone is working, but TTS failed. Please check your sound settings.")
                                        elif tts_ok and not mic_ok:
                                            speak_text("TTS is working, but the microphone did not capture your voice. Please check your input device.")
                                        else:
                                            speak_text("Both TTS and microphone tests failed. Please check your hardware and restart Jarvis.")
                                        safe_tts_join()
                                        last_interaction_time = time.time()
                                        unrecognized_attempts = 0
                                        continue
                                    # --- Response time measurement ---
                                    import time as _time
                                    response_start = _time.time()
                                    response = executor.invoke({"input": user_command})
                                    speak_text(str(response["output"]))
                                    safe_tts_join()
                                    response_end = _time.time()
                                    print(f"Response time: {response_end - response_start:.2f} seconds")
                                    last_interaction_time = _time.time()
                                    unrecognized_attempts = 0
                                except sr.WaitTimeoutError:
                                    logging.info("⌛ No input in conversation mode. Returning to wake word mode.")
                                    speak_text("No input detected. Returning to wake word mode.")
                                    safe_tts_join()
                                    conversation_mode = False
                                    unrecognized_attempts = 0
                                except sr.UnknownValueError:
                                    logging.warning("⚠️ Could not understand audio in conversation mode.")
                                    # Save failed audio for debugging
                                    import wave, datetime
                                    nowstr = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    with wave.open(f"conversation_fail_{nowstr}.wav", "wb") as wf:
                                        wf.setnchannels(1)
                                        wf.setsampwidth(2)
                                        wf.setframerate(16000)
                                        wf.writeframes(audio.get_raw_data())
                                    unrecognized_attempts += 1
                                    if unrecognized_attempts >= MAX_UNRECOGNIZED_ATTEMPTS:
                                        speak_text("Too many failed attempts. Returning to wake word mode.")
                                        safe_tts_join()
                                        conversation_mode = False
                                        unrecognized_attempts = 0
                                    else:
                                        speak_text("Sorry, I didn't catch that. Please repeat.")
                                        safe_tts_join()
                                        last_interaction_time = time.time()
                                except (AssertionError, AttributeError) as e:
                                    logging.error(f"Microphone error: {e}")
                                    speak_text("Microphone error. Returning to wake word mode.")
                                    safe_tts_join()
                                    conversation_mode = False
                                    unrecognized_attempts = 0
                                    time.sleep(1)
                                    break
                                except Exception as e:
                                    logging.exception("❌ Error during user command recognition or processing:")
                                    speak_text("Sorry, something went wrong.")
                                    safe_tts_join()
                                    conversation_mode = False
                                    unrecognized_attempts = 0
                            else:
                                logging.error("No audio captured from microphone in conversation mode.")
                                speak_text("No audio captured. Returning to wake word mode.")
                                safe_tts_join()
                                conversation_mode = False
                                unrecognized_attempts = 0
                                time.sleep(1)
                                break
                    except (AssertionError, AttributeError) as e:
                        logging.error(f"Microphone error (outer): {e}")
                        speak_text("Critical microphone error. Please check your device and restart Jarvis.")
                        safe_tts_join()
                        break
                    except Exception as e:
                        logging.exception("❌ Error during user command recognition or processing (outer):")
                        speak_text("Sorry, something went wrong.")
                        safe_tts_join()
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

                now = time.time()
                if now - last_resource_log > resource_log_interval:
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory()
                    logging.info(f"[RESOURCE] CPU: {cpu}%, Memory: {mem.percent}% used ({mem.used // (1024*1024)}MB/{mem.total // (1024*1024)}MB)")
                    last_resource_log = now
        finally:
            # No mic cleanup needed; always use context manager
            # Ensure TTS worker is stopped on exit
            if tts_worker.is_alive():
                tts_worker.stop()
                try:
                    tts_worker.join(timeout=2)
                except Exception as e:
                    logging.warning(f"[TTS] Exception during TTS worker join: {e}")

    except Exception as e:
        logging.exception("❌ Critical error in main loop:")


if __name__ == "__main__":
    write()
