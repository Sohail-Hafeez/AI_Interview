import os
import sys

from dotenv import load_dotenv
import requests

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")


def test_groq():
    print("\n--- Testing Groq API ---")
    if not GROQ_API_KEY:
        print("FAIL: GROQ_API_KEY not set in .env")
        return False

    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        )
        print("OK:", response.choices[0].message.content.strip())
        return True
    except Exception as e:
        print("FAIL:", e)
        return False


def test_ngrok_whisper():
    print("\n--- Testing ngrok Whisper server ---")
    if not NGROK_URL:
        print("FAIL: NGROK_URL not set in .env")
        return False

    health_url = NGROK_URL.rstrip("/") + "/health"
    try:
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
        print("OK:", response.json())
        return True
    except Exception as e:
        print("FAIL:", e)
        return False


def test_transcription(audio_path):
    print(f"\n--- Testing transcription with '{audio_path}' ---")
    if not os.path.exists(audio_path):
        print(f"SKIP: file not found: {audio_path}")
        return

    transcribe_url = NGROK_URL.rstrip("/") + "/transcribe"
    with open(audio_path, "rb") as f:
        try:
            response = requests.post(transcribe_url, files={"audio": f}, timeout=60)
            response.raise_for_status()
            print("OK:", response.json())
        except Exception as e:
            print("FAIL:", e)


def record_audio(filename="test_audio.wav", duration=5, samplerate=16000):
    import sounddevice as sd
    from scipy.io.wavfile import write

    print(f"\nRecording for {duration} seconds... speak now.")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()
    write(filename, samplerate, recording)
    print(f"Saved recording to '{filename}'")
    return filename


if __name__ == "__main__":
    groq_ok = test_groq()
    ngrok_ok = test_ngrok_whisper()

    if ngrok_ok:
        if len(sys.argv) > 1 and sys.argv[1] == "record":
            duration_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            audio_arg = record_audio(duration=duration_arg)
        else:
            audio_arg = sys.argv[1] if len(sys.argv) > 1 else "test_audio.wav"
        test_transcription(audio_arg)

    print("\n--- Summary ---")
    print(f"Groq API:     {'OK' if groq_ok else 'FAILED'}")
    print(f"Ngrok Whisper: {'OK' if ngrok_ok else 'FAILED'}")
