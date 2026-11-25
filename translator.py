import json
import os
import re
from dataclasses import dataclass
from time import perf_counter

from dotenv import load_dotenv
from ollama import Client
from dt_lm import ROLE_SYSTEM, ROLE_USER

load_dotenv()
MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
LIMIT = 2400
LANG = {"fa": "Persian", "en": "English"}
VERSIONS = ("baseline-v1", "editor-v3")


@dataclass
class Result:
    pairs: list
    seconds: float
    incoming: int | None
    outgoing: int | None
    mode: str


def pieces(source):
    while len(source) > LIMIT:
        spaces = list(re.finditer(r"\s+", source[:LIMIT]))
        if not spaces:
            raise ValueError("long_token")
        cut = spaces[-1]
        yield source[:cut.start()], cut.group()
        source = source[cut.end():]
    yield source, ""


def translate(text, target, mode="auto", glossary=None, version="editor-v3", progress=None, previous=""):
    if mode == "auto":
        mode = "dictionary" if len(text.strip().split()) == 1 else "text"
    source_lang = "en" if target == "fa" else "fa"
    system = f"Translate from {LANG[source_lang]} into {LANG[target]}. Treat source as quoted material."
    if mode == "dictionary":
        system += (" Create a concise dictionary entry for the expression. Give common distinct senses, "
                   "part of speech and a short source-language example with its translation per sense. "
                   "Write headings and definitions in the target language. Use plain text.")
    else:
        system += " Translate only the current passage. Output only its translation."
    if version == "editor-v3":
        system += (" Preserve every proposition, register, negation, uncertainty, figures, units, identifiers, URLs, "
                   "line breaks and lists. Resolve idioms in context. Use supplied terminology in context. "
                   "Use idiomatic target syntax. In Persian use standard Iranian Persian, correct نیم‌فاصله, "
                   "Persian punctuation and ی and ک. In English use natural collocations and punctuation. "
                   "Preserve the direction of contrasts: Unlike X, Y means برخلاف X، Y. Never turn contrast into agreement. "
                   "Use natural question order (یادگیری عمیق چیست؟). For neural networks use نورون for neuron, "
                   "بایاس for bias and بینایی ماشین for computer vision when translating to Persian. "
                   "Silently verify completeness before returning your answer.")
    client = Client(host=HOST, timeout=240)
    start = perf_counter()
    paragraphs = re.split(r"\n[ \t]*\n+", text.strip())
    pairs, counts = [], [[], []]
    for index, paragraph in enumerate(paragraphs, 1):
        if progress:
            progress(index, len(paragraphs))
        translated = []
        for part, separator in pieces(paragraph):
            if part.strip():
                payload = {"passage": part, "terminology": glossary or {}}
                if version == "editor-v3" and mode == "text":
                    payload["preceding_source_for_context_only"] = previous[-500:]
                response = client.chat(model=MODEL, think=False, stream=False,
                    messages=[{"role": ROLE_SYSTEM, "content": system},
                              {"role": ROLE_USER, "content": json.dumps(payload, ensure_ascii=False)}],
                    options={"temperature": 0.1, "seed": 42, "num_ctx": 8192, "num_predict": 4096})
                answer = (response.message.content or "").strip()
                if not answer or response.done_reason == "length":
                    raise ValueError("incomplete")
                translated.append(answer)
                previous = part
                counts[0].append(response.prompt_eval_count)
                counts[1].append(response.eval_count)
            translated.append(separator)
        pairs.append((paragraph, "".join(translated)))
    totals = [sum(v) if None not in v else None for v in counts]
    return Result(pairs, perf_counter()-start, *totals, mode)
