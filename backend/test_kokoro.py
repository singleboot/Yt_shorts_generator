import soundfile as sf
from kokoro_onnx import Kokoro
import sys
import os

print("Testing Kokoro-onnx initialization...")
try:
    kokoro = Kokoro("backend/kokoro-v1.0.onnx", "backend/voices-v1.0.bin")
    print("Kokoro loaded successfully.")
    
    voices = list(kokoro.voices)
    print("Available voices count:", len(voices))
    print("Voice list (first 10):", voices[:10])
    
    text = "Hello! This is Kokoro, the high-quality local text to speech system."
    print(f"Generating test audio for: '{text}' using af_heart voice...")
    samples, sample_rate = kokoro.create(text, voice="af_heart", speed=1.0, lang="en-us")
    
    output_wav = "backend/test_kokoro.wav"
    sf.write(output_wav, samples, sample_rate)
    print(f"Test audio saved successfully at {output_wav} with size {os.path.getsize(output_wav)} bytes.")
except Exception as e:
    print("Error during Kokoro TTS test:", e)
    sys.exit(1)
