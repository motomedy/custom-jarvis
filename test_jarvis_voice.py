import sounddevice as sd
import soundfile as sf
import speech_recognition as sr
import time

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
with sr.Microphone() as source:
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

# Test 3: Simulate edge case (no input)
print('\nTest 3: Simulate no input (wait 5 seconds without speaking)')
with sr.Microphone() as source:
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

print('\nAll tests complete.')