import subprocess

def test_tts():
    subprocess.run(["say", "-v", "Samantha", "This is a test of the TTS system."])
    engine.setProperty('rate', 140)
    engine.say('This is Samantha at slow speed, rate one forty.')
    engine.runAndWait()
    print('Speaking at rate 180 (normal)')
    engine.setProperty('rate', 180)
    engine.say('This is Samantha at normal speed, rate one eighty.')
    engine.runAndWait()
    print('Speaking at rate 220 (fast)')
    engine.setProperty('rate', 220)
    engine.say('This is Samantha at fast speed, rate two twenty.')
    engine.runAndWait()

if __name__ == '__main__':
    test_tts_variants()
