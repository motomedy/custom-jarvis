
import sounddevice as sd
import numpy as np
import soundfile as sf

def list_devices():
	print('Available audio devices:')
	print(sd.query_devices())

def record_and_play(device_index=None, duration=5, amplify=2.0):
	fs = 44100  # Sample rate
	print(f'Recording {duration} seconds of audio...')
	audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device_index, dtype='float32')
	sd.wait()
	print('Recording complete.')
	# Amplify audio
	audio_amplified = np.clip(audio * amplify, -1.0, 1.0)
	print('Playing back amplified audio...')
	sd.play(audio_amplified, fs)
	sd.wait()
	# Optionally save to file
	sf.write('test_recording.wav', audio_amplified, fs)
	print('Saved amplified recording to test_recording.wav')

if __name__ == "__main__":
	list_devices()
	idx = input('Enter device index to test (or press Enter for default): ')
	idx = int(idx) if idx.strip() else None
	record_and_play(device_index=idx)
