import pyttsx3

def test_tts_variants():
    engine = pyttsx3.init()
    engine.setProperty('volume', 1.0)
    for v in engine.getProperty('voices'):
        if 'Samantha' in v.name:
            engine.setProperty('voice', v.id)
            break
    print('Speaking at rate 140 (slow)')
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
