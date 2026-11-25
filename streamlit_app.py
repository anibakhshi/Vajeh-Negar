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
from translator import MODEL, VERSIONS, translate

ROOT = Path(__file__).parent
st.set_page_config(page_title="واژه‌نگار · VajehNegar", page_icon="📖", layout="wide")
state = st.session_state
language = st.selectbox("زبان رابط · Interface language", ["فارسی", "English"], key="language")
fa = language == "فارسی"


def t(persian, english):
    return persian if fa else english


@st.cache_data
def styles():
    fonts = ""
    for family, filename in [("NotoFA", "NotoSansArabic-Regular"), ("NotoEN", "NotoSans-Regular")]:
        data = base64.b64encode((ROOT / "assets" / (filename+".ttf")).read_bytes()).decode()
        fonts += f"@font-face{{font-family:{family};src:url(data:font/ttf;base64,{data}) format('truetype')}}"
    return fonts + """
.stApp{background:radial-gradient(ellipse at top right,#dde9e3,transparent 48%),#faf7ef}
.stMainBlockContainer{max-width:75rem;padding-top:2rem}
.stApp :is(p,textarea,input,label,h1,h2,h3,small,button,.copy,.credits){font-family:NotoEN,NotoFA,sans-serif}
.hero{border-radius:24px;color:#fff8e9;padding:2rem 2.5rem;position:relative;overflow:hidden;
background:radial-gradient(circle at 85% 10%,#384d65,transparent 52%),linear-gradient(115deg,#123b3e,#282443);
border-bottom:4px solid #dcb575;margin:.6rem 0 1rem}
.hero:before{content:"";position:absolute;width:26rem;height:26rem;right:-14rem;top:-12rem;border-radius:50%;
box-shadow:0 0 0 1px #ffffff22,0 0 0 22px #ffffff0a,0 0 0 44px #ffffff0a,0 0 0 66px #ffffff09}
.hero h1{color:#fff8e9;font-size:clamp(2rem,5vw,3.6rem);padding:0}
.credits{display:grid;gap:.25rem;margin-top:.7rem;position:relative}
.credits div{display:flex;flex-wrap:wrap;gap:.35rem 1.5rem;justify-content:space-between}
.copy{white-space:pre-wrap;overflow-wrap:anywhere;line-height:2.1;padding:.85rem 1rem;border-radius:12px;
background:#f3f0e8;border-inline-start:3px solid #b58f60;color:#203b3a}
.copy.target{background:#e4f0eb;border-color:#27786b}
textarea{line-height:1.9!important}
"""


@st.cache_data
def palette():
    return (ROOT/"assets"/"studio.css").read_text(encoding="utf-8")


st.html("<style>"+styles()+palette()+".stMainBlockContainer{direction:"+("rtl" if fa else "ltr")+"}</style>")
credit_rows = [
    ("نام دانشجو · آنیتا بخشی", "Student · Anita Bakhshi"),
    ("نام استاد · استاد داریوش تصدیقی", "Instructor · Dariush Tasdighi"),
    ("نام دوره · LLMOPS", "Course · LLMOPS")]
st.html('<header class="hero"><h1>'+t("واژه‌نگار","VajehNegar")+'</h1><div class="credits">'+
        "".join(f'<div><span dir="rtl">{p}</span><span dir="ltr">{e}</span></div>' for p,e in credit_rows)
        +'</div></header>')


def panel(label, value, lang, target=False):
    st.caption(label)
    direction = "rtl" if lang == "fa" else "ltr"
    st.html(f'<div class="copy {"target" if target else ""}" lang="{lang}" dir="{direction}" '
            f'style="text-align:{"right" if lang=="fa" else "left"}">{escape(value)}</div>')


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
    col1,col2 = st.columns(2)
    direction = col1.selectbox(t("جهت ترجمه","Translation direction"), ["en","fa"],
        format_func=lambda x: {"en":t("انگلیسی به فارسی","English to Persian"),"fa":t("فارسی به انگلیسی","Persian to English")}[x],
        key="direction", on_change=lambda: state.pop("job",None))
    target = "fa" if direction=="en" else "en"
    modes = {"auto":t("خودکار","Automatic"),"dictionary":t("واژه‌نامه","Dictionary"),"text":t("متن","Text")}
    mode = col2.selectbox(t("حالت","Mode"),list(modes),format_func=modes.get,key="mode")
    entry = "source_"+direction
    def change_source(value):
        state[entry] = value
        state.pop("job",None)
    example = ("The meeting was called off.\nPlease keep report_v2.csv.\n\nRevenue may fall by 12%."
               if direction=="en" else "جلسه لغو شد.\nفایل report_v2.csv را نگه دارید.\n\nممکن است درآمد ۱۲ درصد کاهش یابد.")
    a,b=st.columns(2)
    a.button(t("درج نمونه","Load sample"),on_click=change_source,args=(example,))
    b.button(t("پاک کردن","Clear"),on_click=change_source,args=("",))
    st.html("<style>.st-key-"+entry+" textarea{direction:"+("rtl;text-align:right" if direction=="fa" else "ltr;text-align:left")+"}</style>")
    source = st.text_area(t("متن مبدأ","Source text"),key=entry,height=180)
    with st.expander(t("واژه‌نامهٔ اختصاصی","Custom terminology")):
        terms = st.text_area(t("هر خط یک معادل، به شکل مبدأ = مقصد","One mapping per line, source = target"),
                             key="terms_"+direction,height=90,max_chars=1200)
    if st.button(t("ترجمه کن","Translate"),type="primary",key="translate"):
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
            return translate(parts[i],target,job["mode"],job["glossary"],previous=parts[i-1] if i else "")

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
                    items.append(result)
                except errors as exc:
                    job["running"]=False
                    state["failed"]=str(type(exc).__name__)
                    st.rerun()
            result=items[i]
            uid=f'{job["id"]}_{i}'
            with st.container(border=True):
                st.caption(t(f"بند {i+1} از {len(parts)}", f"Passage {i+1} of {len(parts)}"))
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
                with cols[1]:
                    panel(t("ترجمه","Translation"),answer,target,True)
                    if st.toggle(t("ویرایش ترجمه","Edit translation"),key=edit):
                        draft=st.text_area(t("متن ویرایش‌شده","Revised text"),answer,key="draft_"+uid)
                        if st.button(t("ذخیرهٔ ویرایش","Save edit"),key="save_"+uid,disabled=not draft.strip()):
                            result.pairs[0]=(original,draft.strip())
                            st.rerun()
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
    st.caption(t("۳۰ آزمون در دو جهت. امتیاز معنایی و روانی را پس از خواندن پاسخ وارد کنید.",
                 "30 bilingual cases. Review each answer to score meaning and fluency."))
    cases=list(csv.reader((ROOT/"cases.tsv").read_text(encoding="utf-8").splitlines(),delimiter="\t"))
    chosen=st.selectbox(t("نمونهٔ آزمون","Test case"),range(len(cases)),format_func=lambda i: cases[i][1], key="case")
    scope=st.checkbox(t("اجرای هر ۳۰ آزمون (۶۰ فراخوانی مدل)","Run all 30 cases (60 model calls)"))
    rows=state.setdefault("runs",{})
    if st.button(t("اجرای مقایسه","Run comparison")):
        try:
            with st.status(t("در حال ارزیابی","Evaluating")) as status:
                for i in (range(len(cases)) if scope else [chosen]):
                    lang,src,ref,required=cases[i]
                    order=list(VERSIONS)
                    secrets.SystemRandom().shuffle(order)
                    pending={}
                    for alias,v in zip("AB",order):
                        status.update(label=f"{i+1}/30 · {v}")
                        res=translate(src,"fa" if lang=="en" else "en","text",version=v)
                        out=res.pairs[0][1]
                        pending[i,alias]=dict(model=MODEL,version=v,alias=alias,direction=lang,locked=False,source=src,reference=ref,output=out,
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
    lang,src,ref,required=cases[chosen]
    dest="fa" if lang=="en" else "en"
    panel(t("ترجمهٔ مرجع","Reference translation"),ref,dest)
    for col,v in zip(st.columns(2),"AB"):
        with col:
            row=rows.get((chosen,v))
            if row:
                panel(v,row["output"],dest,True)
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
        for lang in ("en","fa"):
            for version in VERSIONS:
                group=[r for r in locked if r["direction"]==lang and r["version"]==version]
                if group:
                    summary.append({t("جهت","Direction"): "EN → FA" if lang=="en" else "FA → EN",
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
