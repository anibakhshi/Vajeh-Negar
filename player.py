import asyncio
import base64
from hashlib import sha256
import json
from pathlib import Path

import streamlit.components.v1 as components
from speech import synthesize


def player(st, t, items, src, dst):
    modes = {"both": t("مبدأ سپس ترجمه", "Source then translation"), "source": t("فقط مبدأ", "Source only"),
             "target": t("فقط ترجمه", "Translation only")}
    mode = st.selectbox(t("ترتیب شنیدن", "Listening order"), list(modes),format_func=modes.get)
    tracks = []
    for index, item in enumerate(items):
        original, translation = item.pairs[0]
        if mode != "target":
            tracks.append([index,src,original])
        if mode != "source":
            tracks.append([index,dst,translation])
    fingerprint = sha256(json.dumps(tracks).encode()).hexdigest()
    if st.button(t("آماده‌سازی پخش پیوسته", "Prepare continuous playback")):
        clips = []
        try:
            with st.spinner(t("دریافت صدای بندها…", "Preparing passage audio…")):
                for index,lang,text in tracks:
                    audio = asyncio.run(synthesize(text,lang))
                    clips.append([index,lang,text,base64.b64encode(audio).decode()])
            st.session_state.playlist = fingerprint, clips
        except Exception:
            st.warning(t("دریافت صدا کامل نشد؛ دوباره تلاش کنید.", "Audio generation failed. Please retry."))
    playlist = st.session_state.get("playlist")
    if playlist and playlist[0] == fingerprint:
        template = (Path(__file__).parent/"assets/player.html").read_text(encoding="utf-8")
        payload = json.dumps(playlist[1],ensure_ascii=False).replace("<","\\u003c")
        components.html(template.replace("UI_LANG",t("fa","en")).replace("TRACK_DATA",payload),height=330)
