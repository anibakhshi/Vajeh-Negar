import base64
import csv
import io
import re
import secrets
from statistics import mean
from quality import differences
from html import escape
from pathlib import Path

import httpx
import streamlit as st
from ollama import ResponseError
import documents
from player import player
from speech import audio_control, suggest
from translator import MODEL, VERSIONS, translate

ROOT = Path(__file__).parent
st.set_page_config(page_title="واژه‌نگار · VajehNegar", page_icon="📖", layout="wide")
state = st.session_state
language = st.sidebar.selectbox("زبان رابط · Interface language", ["فارسی", "English"], key="language")
fa = language == "فارسی"


def t(persian, english):
    return persian if fa else english


@st.cache_data
def styles():
    fonts = ""
    for family, filename in [("NotoFA", "NotoSansArabic-Regular"), ("NotoEN", "NotoSans-Regular")]:
        data = base64.b64encode((ROOT / "assets" / (filename+".ttf")).read_bytes()).decode()
        fonts += f"@font-face{{font-family:{family};src:url(data:font/ttf;base64,{data}) format('truetype')}}"
    return fonts


@st.cache_data
def palette():
    return (ROOT/"assets"/"studio.css").read_text(encoding="utf-8")


st.html("<style>"+styles()+palette()+".stMainBlockContainer{direction:"+("rtl" if fa else "ltr")+"}</style>")
credit_rows = [
    ("نام دانشجو · آنیتا بخشی", "Student · Anita Bakhshi"),
    ("نام استاد · استاد داریوش تصدیقی", "Instructor · Dariush Tasdighi"),
    ("نام دوره · LLMOPS", "Course · LLMOPS")]
st.html('<header class="hero"><div><h1>'+t("واژه‌نگار","VajehNegar")+'</h1><p>'+
        t("مترجم و واژه‌نامهٔ فارسی، انگلیسی و آلمانی","Persian, English and German translation studio")+
        '</p></div><div class="art" aria-hidden="true"><i>A</i><i>آ</i></div></header>')
with st.sidebar.expander(t("مشخصات پروژه","Project credits")):
    st.html('<div class="credits">'+ "".join(
        f'<div><strong dir="rtl">{p}</strong><small dir="ltr">{e}</small></div>' for p,e in credit_rows)+'</div>')


def panel(label, value, lang, target=False):
    direction = "rtl" if lang == "fa" else "ltr"
    st.html(f'<section class="sheet {"output" if target else ""}"><header><b>{escape(label)}</b>'
            f'<small>{escape(lang.upper())}</small></header><div class="copy" lang="{lang}" dir="{direction}">'
            f'{escape(value)}</div></section>')


def error(exc):
    if isinstance(exc, ValueError):
        st.error(t("ترجمه ناقص است یا یک رشتهٔ بدون فاصله خیلی طولانی است.",
                   "Incomplete translation or an unbroken token is too long."))
    else:
        st.error(t("اتصال به مدل محلی ناموفق بود. سرویس Ollama و نصب مدل را بررسی کنید.",
                   "Local model unavailable. Check Ollama and the installed model.") + f" ({MODEL})")


errors = (ConnectionError, httpx.RequestError, ResponseError, ValueError)
work, lab = st.tabs([t("میز ترجمه","Translator"),t("آزمایشگاه پرامپت","Prompt lab")])
with work:
    names={"en":t("انگلیسی","English"),"fa":t("فارسی","Persian"),"de":t("آلمانی","German")}
    def reset_job():
        state.pop("job",None)
    def swap():
        old=state.get("job")
        state.src,state.dst=state.dst,state.src
        if old and len(old["items"])==len(old["parts"]):
            state.input_text="\n\n".join(r.pairs[0][1] for r in old["items"])
        reset_job()
    with st.sidebar.expander(t("اسناد محلی", "Local documents")):
        saved=documents.choices()
        def reopen():
            job=documents.load(state.doc_choice)
            state.src=job.pop("src")
            state.dst=job.pop("dst")
            state.input_text="\n\n".join(job["parts"])
            state.mode=job["mode"]
            state["terms_"+state.src+state.dst]="\n".join(f"{k} = {v}" for k,v in job["glossary"].items())
            state.job=job
            for key in list(state):
                if key.startswith(("edit_","draft_")):
                    del state[key]
            if "last_edit" in job:
                state[f"edit_{job['id']}_{job['last_edit']}"]=True
        if saved:
            st.selectbox(t("سند ذخیره‌شده","Saved document"),list(saved),format_func=saved.get,key="doc_choice")
            st.button(t("باز کردن سند","Open document"),on_click=reopen)
    left,middle,right=st.columns([3,1,3])
    direction=left.selectbox(t("زبان مبدأ","Source language"),list(names),format_func=names.get,key="src",on_change=reset_job)
    target=right.selectbox(t("زبان مقصد","Target language"),list(names),index=1,format_func=names.get,key="dst",on_change=reset_job)
    middle.button("⇄",key="swap_lang",help=t("جابه‌جایی زبان‌ها","Swap languages"),on_click=swap)
    modes={"auto":t("خودکار","Automatic"),"dictionary":t("واژه‌نامه","Dictionary"),"text":t("متن","Text")}
    mode=st.sidebar.selectbox(t("حالت","Mode"),list(modes),format_func=modes.get,key="mode")
    entry="input_text"
    def change_source(value):
        state[entry] = value
        state.pop("job",None)
    example = ("The meeting was called off.\nPlease keep report_v2.csv.\n\nRevenue may fall by 12%."
               if direction=="en" else "جلسه لغو شد.\nفایل report_v2.csv را نگه دارید.\n\nممکن است درآمد ۱۲ درصد کاهش یابد.")
    if direction=="de":
        example="Die Besprechung wurde abgesagt.\nBitte behalten Sie report_v2.csv.\n\nDer Umsatz könnte um 12 Prozent sinken."
    st.html("<style>.st-key-"+entry+" textarea{direction:"+("rtl;text-align:right" if direction=="fa" else "ltr;text-align:left")+"}</style>")
    source = st.text_area(t("متن مبدأ","Source text"),key=entry,height=200,placeholder=t("متن را اینجا وارد کنید…","Type or paste your text here…"))
    a,b=st.columns(2)
    a.button(t("درج نمونه","Load sample"),on_click=change_source,args=(example,))
    b.button(t("پاک کردن","Clear"),on_click=change_source,args=("",))
    def detect_input():
        guess=suggest(state.input_text)
        if guess:
            state.src=guess
            reset_job()
        state.detected=guess or "?"
    st.button(t("تشخیص زبان متن","Detect source language"),on_click=detect_input,disabled=not source.strip())
    if state.get("detected")=="?":
        st.caption(t("زبان را دستی انتخاب کنید.","Select the source language manually."))
    speech_on=st.sidebar.checkbox(t("فعال‌سازی صوت آنلاین","Enable online audio"),key="speech_on")
    if speech_on:
        st.caption(t("با زدن دکمهٔ شنیدن، متن انتخاب‌شده برای تولید صدا به Microsoft Edge TTS فرستاده می‌شود.",
                     "Pressing Listen sends the selected text to Microsoft Edge TTS."))
        audio_control(st,t,source,direction,"source-full",t("شنیدن کل متن مبدأ","Listen to full source"))
    if direction==target:
        st.info(t("دو زبان متفاوت انتخاب کنید.","Choose two different languages."))
    with st.sidebar.expander(t("واژه‌نامهٔ اختصاصی","Custom terminology")):
        terms = st.text_area(t("هر خط یک معادل، به شکل مبدأ = مقصد","One mapping per line, source = target"),
                             key="terms_"+direction+target,height=90,max_chars=1200)
    if st.button(t("ترجمه کن","Translate"),type="primary",key="translate",disabled=direction==target):
        state.pop("job",None)
        glossary = {}
        for line in terms.splitlines():
            if not line.strip():
                continue
            key, sep, value = line.partition("=")
            if not sep or not key.strip() or not value.strip():
                st.error(t("هر سطر واژه‌نامه به یک مبدأ و مقصد نیاز دارد.","Each glossary row needs a source and target."))
                break
            glossary[key.strip()] = value.strip()
        else:
            if not source.strip():
                st.warning(t("یک واژه یا متن وارد کنید.","Enter a word or passage."))
            else:
                resolved = ("dictionary" if len(source.split())==1 else "text") if mode=="auto" else mode
                state.job = dict(id=secrets.token_hex(6), parts=re.split(r"\n[ \t]*\n+", source.strip()),
                                 items=[], mode=resolved, glossary=glossary, running=True)
    job = state.get("job")
    if job:
        items = job["items"]
        parts = job["parts"]
        def generate(i):
            return translate(parts[i],target,job["mode"],job["glossary"],previous=parts[i-1] if i else "",source_lang=direction)

        split = st.toggle(t("نمای تطبیقی","Side by side"),value=True,key="compare")
        if len(items)<len(parts) and not job["running"]:
            if st.button(t("ادامه از بند بعدی","Resume from next passage"),key="resume"):
                job["running"]=True
        for i,original in enumerate(parts):
            if i==len(items):
                if not job["running"]:
                    break
                try:
                    with st.spinner(t("ترجمهٔ بند","Translating passage")+f" {i+1}/{len(parts)}"):
                        result=generate(i)
                    job.setdefault("initial",[]).append(result.pairs[0][1])
                    items.append(result)
                except errors as exc:
                    job["running"]=False
                    state["failed"]=str(type(exc).__name__)
                    st.rerun()
            result=items[i]
            uid=f'{job["id"]}_{i}'
            with st.container(border=True):
                st.caption(t(f"بند {i+1} از {len(parts)}", f"Passage {i+1} of {len(parts)}"))
                if job.get("last_edit")==i:
                    st.caption(t("آخرین بند ویرایش‌شده","Last edited passage"))
                edit="edit_"+uid
                if st.button(t("ترجمهٔ مجدد","Retranslate"),key="retry_"+uid):
                    try:
                        result=generate(i)
                        items[i]=result
                        state.pop("draft_"+uid,None)
                        state[edit]=False
                    except errors as exc:
                        error(exc)
                cols=st.columns(2) if split else [st.container(),st.container()]
                answer=result.pairs[0][1]
                with cols[0]:
                    panel(t("مبدأ","Original"),original,direction)
                    if speech_on:
                        audio_control(st,t,original,direction,"source-"+uid,t("شنیدن مبدأ","Listen to source"))
                with cols[1]:
                    panel(t("ترجمه","Translation"),answer,target,True)
                    if speech_on:
                        audio_control(st,t,answer,target,"translation-"+uid,t("شنیدن ترجمه","Listen to translation"))
                    if st.toggle(t("ویرایش ترجمه","Edit translation"),key=edit):
                        draft=st.text_area(t("متن ویرایش‌شده","Revised text"),answer,key="draft_"+uid)
                        if st.button(t("ذخیرهٔ ویرایش","Save edit"),key="save_"+uid,disabled=not draft.strip()):
                            job["last_edit"]=i
                            result.pairs[0]=(original,draft.strip())
                            st.rerun()
                if job.get("initial") and answer!=job["initial"][i]:
                    with st.expander(t("اولین ترجمهٔ مدل","Original model translation")):
                        panel(t("نسخهٔ اولیه","Initial version"),job["initial"][i],target)
                missing,added=differences(original,answer)
                if missing or added:
                    if missing:
                        st.warning(t("در ترجمه پیدا نشد","Missing in translation")+" · "+", ".join(missing))
                    if added:
                        st.warning(t("در ترجمه اضافه شد","Added in translation")+" · "+", ".join(added))
        if len(items)<len(parts) and not job["running"]:
            st.error(t("تولید بند کامل نشد. سرویس مدل و طول ورودی را بررسی کنید و ادامه را بزنید.",
                       "Passage generation stopped. Check the model service and input length, then resume."))
        if items:
            if st.button(t("ذخیرهٔ سند روی این دستگاه","Save document on this device")):
                documents.save(job,direction,target)
                st.success(t("سند ذخیره شد.","Document saved."))
            if speech_on:
                with st.expander(t("تمرین شنیداری پیوسته","Continuous listening practice")):
                    player(st,t,items,direction,target)
            if speech_on and len(items)==len(parts):
                audio_control(st,t,"\n\n".join(r.pairs[0][1] for r in items),target,"translation-full",t("شنیدن کل ترجمه","Listen to full translation"))
            st.download_button(t("دریافت متن فعلی","Download current translation"),
                "\n\n".join(r.pairs[0][1] for r in items),"translation.txt","text/plain;charset=utf-8",on_click="ignore")
            with st.expander(t("جزئیات اجرای بندهای فعلی","Current passage metrics")):
                st.write(f"{MODEL} · editor-v3 · {modes[job['mode']]}")
                for col,label,key in zip(st.columns(3),[t("ثانیه","Seconds"),t("توکن ورودی","Input tokens"),
                    t("توکن خروجی","Output tokens")],["seconds","incoming","outgoing"]):
                    values=[getattr(r,key) for r in items]
                    col.metric(label,"—" if None in values else round(sum(values),2))
with lab:
    st.subheader(t("مقایسهٔ دو نسخهٔ پرامپت","Compare two prompt versions"))
    st.caption(t("۴۶ آزمون در شش جهت. امتیاز معنایی و روانی را پس از خواندن پاسخ وارد کنید.",
                 "46 cases across six directions. Review each answer to score meaning and fluency."))
    cases=list(csv.reader((ROOT/"cases.tsv").read_text(encoding="utf-8").splitlines(),delimiter="\t"))
    chosen=st.selectbox(t("نمونهٔ آزمون","Test case"),range(len(cases)),format_func=lambda i: f"{cases[i][0]} → {cases[i][1]} · {cases[i][2]}", key="case")
    scope=st.checkbox(t("اجرای هر ۴۶ آزمون (۹۲ فراخوانی مدل)","Run all 46 cases (92 model calls)"))
    rows=state.setdefault("runs",{})
    if st.button(t("اجرای مقایسه","Run comparison")):
        try:
            with st.status(t("در حال ارزیابی","Evaluating")) as status:
                for i in (range(len(cases)) if scope else [chosen]):
                    lang,dest,src,ref,required=cases[i]
                    order=list(VERSIONS)
                    secrets.SystemRandom().shuffle(order)
                    pending={}
                    for alias,v in zip("AB",order):
                        status.update(label=f"{i+1}/{len(cases)}")
                        res=translate(src,dest,"text",version=v,source_lang=lang)
                        out=res.pairs[0][1]
                        pending[i,alias]=dict(model=MODEL,version=v,alias=alias,direction=f"{lang} → {dest}",locked=False,source=src,reference=ref,output=out,
                            seconds=round(res.seconds,2),input_tokens=res.incoming,output_tokens=res.outgoing,
                            token_check=(any(x in out for x in required.split("|")) if required else None),
                            meaning=None,fluency=None)
                    rows.update(pending)
                    for v in "AB":
                        for field in ("meaning","fluency"):
                            state.pop(f"{i}_{v}_{field}",None)
                status.update(label=t("پایان مقایسه","Comparison complete"),state="complete")
        except errors as exc:
            error(exc)
    lang,dest,src,ref,required=cases[chosen]
    panel(t("ترجمهٔ مرجع","Reference translation"),ref,dest)
    if state.get("speech_on"):
        audio_control(st,t,src,lang,"lab-source",t("شنیدن نمونه","Listen to sample"))
        audio_control(st,t,ref,dest,"lab-reference",t("شنیدن مرجع","Listen to reference"))
        st.caption(t("تلفظ عدد، درصد و نام فایل را در نمونه‌های report_v2.csv بررسی کنید.",
                     "Check the number, percentage and filename in the report_v2.csv samples."))
    for col,v in zip(st.columns(2),"AB"):
        with col:
            row=rows.get((chosen,v))
            if row:
                panel(v,row["output"],dest,True)
                if state.get("speech_on"):
                    audio_control(st,t,row["output"],dest,"lab-"+v,t("شنیدن پاسخ","Listen to answer"))
                st.caption(f'{row["seconds"]} s')
                if required:
                    st.write(t("حفظ عدد یا شناسه","Number or identifier preserved"),"✓" if row["token_check"] else "✗")
                for field,label in [("meaning",t("وفاداری معنایی","Meaning")),("fluency",t("روانی","Fluency"))]:
                    row[field]=st.selectbox(label+" (1–5)",[None,1,2,3,4,5],
                        index=[None,1,2,3,4,5].index(row[field]),format_func=lambda x:"—" if x is None else str(x),
                        key=f"{chosen}_{v}_{field}",disabled=row["locked"])
    pair=[rows.get((chosen,v)) for v in "AB"]
    if all(pair) and all(r["meaning"] and r["fluency"] for r in pair):
        if not pair[0]["locked"] and st.button(t("ثبت نهایی و نمایش نسخه‌ها","Lock ratings and reveal versions")):
            for r in pair:
                r["locked"]=True
            st.rerun()
        if pair[0]["locked"]:
            st.caption(" · ".join(f'{r["alias"]} = {r["version"]}' for r in pair))
    locked=[r for r in rows.values() if r["locked"]]
    if locked:
        summary=[]
        for lang in sorted({r["direction"] for r in locked}):
            for version in VERSIONS:
                group=[r for r in locked if r["direction"]==lang and r["version"]==version]
                if group:
                    summary.append({t("جهت","Direction"): lang.upper(),
                        t("نسخه","Version"):version,t("تعداد","Cases"):len(group),
                        **{label:round(mean(r[k] for r in group),2) for k,label in
                           [("meaning",t("دقت معنایی","Meaning")),("fluency",t("روانی","Fluency")),("seconds",t("ثانیه","Seconds"))]}})
        st.dataframe(summary,hide_index=True)
    if rows:
        stream=io.StringIO()
        writer=csv.DictWriter(stream,fieldnames=next(iter(rows.values())).keys())
        writer.writeheader()
        writer.writerows({**r,"version":r["version"] if r["locked"] else ""} for r in rows.values())
        st.download_button(t("دریافت نتایج CSV","Download results CSV"),stream.getvalue().encode("utf-8-sig"),
                           "prompt-comparison.csv","text/csv")
