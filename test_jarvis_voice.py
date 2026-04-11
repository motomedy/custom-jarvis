import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
import time
import sys

def print_microphones():
    mics = sr.Microphone.list_microphone_names()
    print("\nAvailable microphones:")
    for idx, name in enumerate(mics):
        print(f"  [{idx}] {name}")
    return mics

def select_microphone():
    mics = print_microphones()
    try:
        idx = int(input("Select microphone index (default 0): ") or "0")
        if idx < 0 or idx >= len(mics):
            print("Invalid index, defaulting to 0.")
            idx = 0
    except Exception:
        idx = 0
    print(f"Using microphone: [{idx}] {mics[idx]}")
    return idx

MIC_INDEX = select_microphone()

# Test 1: Record and playback
print('Test 1: Recording 3 seconds of audio...')
fs = 44100
recording = sd.rec(int(3 * fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
print('Playing back...')
sd.play(recording, fs)
sd.wait()
sf.write('test_jarvis_recording.wav', recording, fs)
print('Saved as test_jarvis_recording.wav')

# Test 2: Recognize speech from microphone
print('\nTest 2: Speech recognition (say something after the beep)')
rec = sr.Recognizer()
try:
    with sr.Microphone(device_index=MIC_INDEX) as source:
        print('Calibrating for ambient noise...')
        rec.adjust_for_ambient_noise(source, duration=1)
        print('Beep! Listening...')
        audio = rec.listen(source, timeout=5, phrase_time_limit=5)
    try:
        text = rec.recognize_google(audio)
        print('You said:', text)
    except sr.UnknownValueError:
        print('Could not understand audio')
    except Exception as e:
        print('Recognition error:', e)
except Exception as e:
    print('Microphone initialization/listening error:', e)
    if sys.platform == "darwin":
        print("[macOS] Check System Preferences > Security & Privacy > Microphone permissions for Terminal/Python.")

# Test 3: Simulate edge case (no input)
print('\nTest 3: Simulate no input (wait 5 seconds without speaking)')
try:
    with sr.Microphone(device_index=MIC_INDEX) as source:
        rec.adjust_for_ambient_noise(source, duration=1)
        try:
            audio = rec.listen(source, timeout=5, phrase_time_limit=3)
            text = rec.recognize_google(audio)
            print('You said:', text)
        except sr.WaitTimeoutError:
            print('No speech detected (timeout)')
        except sr.UnknownValueError:
            print('Could not understand audio')
        except Exception as e:
            print('Recognition error:', e)
except Exception as e:
    print('Microphone initialization/listening error:', e)
    if sys.platform == "darwin":
        print("[macOS] Check System Preferences > Security & Privacy > Microphone permissions for Terminal/Python.")

print('\nAll tests complete.')