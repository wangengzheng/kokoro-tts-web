from kokoro import KPipeline
import soundfile as sf
import numpy as np

pipeline = KPipeline(lang_code="a")

text = '''
Our planet is facing serious environmental challenges. The good news is that we are making progress to solve many of these.

Deforestation is increasing. We are losing around 10 million hectares of forest every year.

Global temperatures are rising. 2024 was the warmest year since records began.

Plastic pollution is spreading across oceans, harming sea life. Around 10 million tons of plastic end up in the ocean each year.

Air quality is getting worse in many cities. The World Health Organization (WHO) estimates that air pollution causes around four million deaths each year.

Many countries are working to replant forests. More than 100 have agreed to reverse deforestation by 2030.

Governments are agreeing to reduce carbon emissions. More than 140 countries are hoping to reach net-zero emissions by 2050.

Companies are creating sustainable materials to replace plastic. Global trade in plastic alternatives was worth around $388 billion in 2020.

More people around the world are using electric cars. According to the International Energy Agency (IEA), nearly one in five cars sold in 2023 was electric.
'''

generator = pipeline(
    text,
    voice="af_heart"
)

audio_chunks = []

for _, _, audio in generator:
    audio_chunks.append(audio)

# 拼接所有音频
audio = np.concatenate(audio_chunks)

sf.write(
    "entrepreneur.wav",
    audio,
    24000
)

print("✅ 已生成 entrepreneur.wav")