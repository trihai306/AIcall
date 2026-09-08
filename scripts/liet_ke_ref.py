import soundfile as sf, glob, os, sys
sys.stdout.reconfigure(encoding="utf-8")
for f in sorted(glob.glob("models/tts/ref_voices/*.wav")):
    i = sf.info(f); print(f"{os.path.basename(f):28} {i.duration:5.2f}s {i.samplerate}Hz")
