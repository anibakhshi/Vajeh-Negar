import asyncio
from hashlib import sha256
from time import perf_counter

import edge_tts
from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0
VOICES = {"en": "en-US-JennyNeural", "fa": "fa-IR-DilaraNeural", "de": "de-DE-KatjaNeural"}


def suggest(text):
    try:
        lang = detect(text)
    except LangDetectException:
        return None
    return lang if lang in VOICES else None


async def synthesize(text, lang):
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, VOICES[lang]).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("Empty audio")
    return bytes(audio)


def audio_control(st, t, text, lang, key, label):
    if not text.strip():
        return
    cache = st.session_state.setdefault("audio_cache", {})
    digest = sha256((VOICES[lang]+"\0"+text).encode()).hexdigest()
    if digest not in cache and st.button(label, key="listen_"+key, icon=":material/volume_up:"):
        try:
            with st.spinner(t("در حال ساخت صدا…", "Generating audio…")):
                start = perf_counter()
                data = asyncio.run(synthesize(text, lang))
                cache[digest] = (data, perf_counter()-start)
                while len(cache)>1 and sum(len(v[0]) for v in cache.values())>32*1024*1024:
                    del cache[next(iter(cache))]
        except Exception:
            st.warning(t("صدا دریافت نشد. اتصال اینترنت را بررسی و دوباره تلاش کنید.",
                         "Audio unavailable. Check your connection and try again."))
    if digest in cache:
        data, seconds = cache[digest]
        st.caption(f"{label} · {VOICES[lang]} · {seconds:.2f} s")
        st.audio(data, format="audio/mpeg")
        st.download_button(t("دریافت MP3","Download MP3"), data, f"{key}-{lang}.mp3",
                           "audio/mpeg", key="download_"+key,on_click="ignore")
