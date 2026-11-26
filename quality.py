"""Literal consistency checks, including equivalent Persian/English number formats."""
from collections import Counter
import re
import unicodedata

TOKEN = re.compile(r"https?://[^\s<>]+|[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.[A-Za-z][A-Za-z0-9]{1,9}\b|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|[-+−]?\d+(?:[,٬]\d{3})*(?:[.٫]\d+)?(?:[ \t]*(?:%|٪|درصد|percent\b|prozent\b))?", re.I)


def literals(text):
    values = []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token.startswith(("http://", "https://")):
            token = token.rstrip(".,;:!?،؛؟)]")
        elif re.match(r"[-+−]?\d", token) and not re.search(r"[A-Za-z]", re.sub(r"percent|prozent", "", token, flags=re.I)):
            token = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in token)
            token = re.sub(r"\s*(?:درصد|percent|prozent|٪|%)$", "%", token, flags=re.I)
            token = token.translate(str.maketrans({"−":"-", "٫":".", "٬":None, ",":None}))
        values.append(token)
    return Counter(values)


NUMBER_WORDS = [
    "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn zwanzig".split(),
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split(),
    "صفر یک دو سه چهار پنج شش هفت هشت نه ده یازده دوازده سیزده چهارده پانزده شانزده هفده هجده نوزده بیست".split(),
]


def written_counts(text):
    # Protect filenames, identifiers and URLs before looking for standalone words.
    plain = TOKEN.sub(" ", text.casefold())
    counts = Counter()
    for words in NUMBER_WORDS:
        for n, word in enumerate(words):
            for match in re.finditer(r"(?<![\w‌-])"+word+r"(?![\w‌-])", plain):
                suffix = plain[match.end():]
                percent = re.match(r"\s*(?:درصد|percent\b|prozent\b|٪|%)", suffix)
                counts[str(n) + ("%" if percent else "")] += 1
    return counts


def differences(source, result):
    before, after = literals(source), literals(result)
    # Cancel equivalent written forms only for unmatched numeric literals.
    source_words, target_words = written_counts(source), written_counts(result)
    missing = (before-after) - (target_words-source_words)
    added = (after-before) - (source_words-target_words)
    return list(missing.elements()), list(added.elements())
