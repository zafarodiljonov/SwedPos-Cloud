"""Help center content for the website.

The texts are written once, as plain files in the desktop repo's `help/` folder; `python tools/build_help.py`
(desktop repo) copies them here as `help.json`. Topics marked audience "app" (cash desk, printers...) are not shown here.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from django.utils.html import escape
from django.utils.safestring import mark_safe

DATA = Path(__file__).with_name("help.json")
SURFACE = "web"


@lru_cache(maxsize=1)
def _raw():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _pick(obj, lang):
    return obj.get(lang) or obj.get("uz") or ""


def _web_topics():
    return [t for t in _raw()["topics"] if t["audience"] in ("both", SURFACE)]


def categories(lang):
    """Categories that have at least one topic for the website, each with its topics."""
    topics = _web_topics()
    result = []
    for c in _raw()["categories"]:
        items = [{"id": t["id"], "title": _pick(t["title"], lang)} for t in topics if t["category"] == c["id"]]
        if items:
            result.append({"id": c["id"], "title": _pick(c["title"], lang), "topics": items})
    return result


def topic(topic_id, lang):
    for t in _web_topics():
        if t["id"] == topic_id:
            return {"id": t["id"], "title": _pick(t["title"], lang), "html": render(_pick(t["body"], lang))}
    return None


def terms(lang):
    return [{"id": t["id"], "title": _pick(t["title"], lang), "short": _pick(t["short"], lang)} for t in _raw()["terms"]]


def contacts(lang):
    return [{"label": _pick(c["label"], lang), "value": c["value"]} for c in _raw()["contacts"] if c["value"]]


def search(query, lang):
    """Every word must appear in the title or the text; title matches first."""
    words = [w.lower() for w in re.split(r"[ ,.?!]+", query) if w]
    if not words:
        return []
    found = []
    for t in _web_topics():
        title = _pick(t["title"], lang).lower()
        text = title + " " + _pick(t["body"], lang).lower()
        if all(w in text for w in words):
            found.append((-sum(w in title for w in words), {"id": t["id"], "title": _pick(t["title"], lang)}))
    return [item for _, item in sorted(found, key=lambda x: x[0])]


# ---- the mini markup (same rules as HelpCenter.ParseBody in the desktop app) ----

def _inline(text):
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def render(body):
    html, para = [], []
    state = {"list": None}

    def close_list():
        if state["list"]:
            html.append("</%s>" % state["list"])
            state["list"] = None

    def flush():
        if para:
            html.append("<p>%s</p>" % _inline(" ".join(para)))
            para.clear()

    def item(kind, text):
        flush()
        if state["list"] != kind:
            close_list()
            html.append("<%s>" % kind)
            state["list"] = kind
        html.append("<li>%s</li>" % _inline(text))

    for raw in body.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line:
            flush()
            close_list()
        elif line.startswith("## "):
            flush()
            close_list()
            html.append("<h2>%s</h2>" % _inline(line[3:].strip()))
        elif line.startswith("- "):
            item("ul", line[2:].strip())
        elif line.startswith("> "):
            flush()
            close_list()
            html.append('<div class="note">%s</div>' % _inline(line[2:].strip()))
        elif re.match(r"^\d{1,2}\. ", line):
            item("ol", line.split(". ", 1)[1].strip())
        else:
            close_list()
            para.append(line.strip())
    flush()
    close_list()
    return mark_safe("\n".join(html))
