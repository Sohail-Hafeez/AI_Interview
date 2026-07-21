import os
import sys
import queue

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
import requests
import pyttsx3
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")

if not GROQ_API_KEY or not NGROK_URL:
    sys.exit("GROQ_API_KEY or NGROK_URL missing from .env")

groq_client = Groq(api_key=GROQ_API_KEY)

SAMPLERATE = 16000
SYSTEM_PROMPT = (
    "You are a friendly voice assistant confirming a speech pipeline works. "
    "Keep replies short, 1-2 sentences, natural to speak aloud."
)

conversation = [{"role": "system", "content": SYSTEM_PROMPT}]


def record_until_enter():
    q = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    input("\nPress Enter to start speaking...")
    stream = sd.InputStream(samplerate=SAMPLERATE, channels=1, dtype="int16", callback=callback)
    stream.start()
    print("Recording... press Enter to stop.")
    input()
    stream.stop()
    stream.close()

    chunks = []
    while not q.empty():
        chunks.append(q.get())

    if not chunks:
        return None

    audio = np.concatenate(chunks, axis=0)
    filename = "mic_input.wav"
    write(filename, SAMPLERATE, audio)
    return filename


def transcribe(audio_path, retries=3):
    url = NGROK_URL.rstrip("/") + "/transcribe"
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with open(audio_path, "rb") as f:
                response = requests.post(url, files={"audio": f}, timeout=60)
            response.raise_for_status()
            return response.json().get("text", "").strip()
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"Transcription attempt {attempt} failed ({e.__class__.__name__}), retrying...")
    raise last_error


def get_reply(user_text):
    conversation.append({"role": "user", "content": user_text})
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=conversation,
    )
    reply = response.choices[0].message.content.strip()
    conversation.append({"role": "assistant", "content": reply})
    return reply


def speak(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    engine.stop()


if __name__ == "__main__":
    print("Voice chatbot ready. Say 'quit' or 'exit' to stop.")
    while True:
        audio_file = record_until_enter()
        if not audio_file:
            print("No audio captured, try again.")
            continue

        try:
            user_text = transcribe(audio_file)
        except requests.exceptions.RequestException as e:
            print(f"Transcription failed after retries: {e}")
            continue
        print(f"You said: {user_text}")

        if not user_text:
            print("Couldn't understand, try again.")
            continue

        if user_text.strip().lower().strip(".") in ("quit", "exit"):
            print("Goodbye!")
            break

        reply = get_reply(user_text)
        print(f"Bot: {reply}")
        speak(reply)
