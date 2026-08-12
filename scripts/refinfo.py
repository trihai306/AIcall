import glob, soundfile as sf
for f in sorted(glob.glob(r"C:\duan\chat-ai\models\tts\ref_voices\*.wav")):
    i = sf.info(f)
    print("%-16s %5.2f giay  %d Hz" % (f.rsplit("\\",1)[-1], i.duration, i.samplerate))
