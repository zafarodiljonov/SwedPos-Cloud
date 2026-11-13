from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import get_language

from . import content

# Texts of the help page itself (the guides come from help.json).
TEXTS = {
    "uz": {
        "title": "Yordam markazi", "search": "Qidirish...", "guides": "Qo'llanma", "terms": "So'zlar",
        "contact": "Aloqa", "back": "← Hisobotlarga qaytish", "empty": "Hech narsa topilmadi.",
        "welcome": "Chapdagi ro'yxatdan mavzuni tanlang yoki qidiruvga so'z yozing.",
        "contact_text": "Savol yoki muammo bo'lsa, bog'laning.",
    },
    "ru": {
        "title": "Центр помощи", "search": "Поиск...", "guides": "Руководства", "terms": "Слова",
        "contact": "Связь", "back": "← К отчётам", "empty": "Ничего не найдено.",
        "welcome": "Выберите тему слева или введите слово в поиск.",
        "contact_text": "Если есть вопрос или проблема, свяжитесь с нами.",
    },
}


@login_required
def index(request, topic_id=None):
    lang = "ru" if get_language() == "ru" else "uz"
    query = request.GET.get("q", "").strip()
    context = {
        "t": TEXTS[lang], "query": query, "categories": content.categories(lang), "terms": content.terms(lang),
        "contacts": content.contacts(lang), "topic": None, "results": None,
        "show": request.GET.get("tab", "guides"),
    }
    if topic_id:
        context["topic"] = content.topic(topic_id, lang)
        if context["topic"] is None:
            raise Http404
    if query:
        context["results"] = content.search(query, lang)
    return render(request, "help/index.html", context)
