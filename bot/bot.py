"""Telegram-бот @sorockina_ai_bot: воронка после игры «Контент-шар».

Цепочка: гайд по форматам -> канал -> кейс Bravos -> консультация по контенту -> обучение ИИ.
Запускается в GitHub Actions (long polling). Ключ бота берётся из секрета BOT_TOKEN.
Состояние (кому и когда отправить следующее сообщение) хранится в bot_state.json,
который workflow переносит между запусками через закрытый кэш Actions.
Персональные данные в лог не пишутся: репозиторий публичный.
"""
import html
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.parse

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Elen_Sorockina").lower()
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "20700"))
HERE = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(HERE, "Форматы_Reels_по_нишам.pdf")
STATE_PATH = os.environ.get("STATE_PATH", os.path.join(HERE, "..", "bot_state.json"))

CHANNEL_URL = "https://t.me/ne_ruchkami"
LENA_URL = "https://t.me/Elen_Sorockina"

MIN = 60
HOUR = 60 * MIN

# ---------- Тексты ----------

TEXT_GIFT = (
    "Шар передал, что ты за форматами 🔮\n\n"
    "Держи гайд <b>«25 форматов Reels, которые приносят заявки»</b>. "
    "Здоровье, красота, эксперты, производство: у каждого формата реальный ролик и цифры.\n\n"
    "Найди свой и сними его уже на этой неделе."
)

TEXT_CHANNEL = (
    "А теперь честно: шар пошутил, а система работает 😉\n\n"
    "В канале <b>«Не ручками»</b> разбираю контент, который продаёт: "
    "живые кейсы, форматы и воронки. Без охватов ради охватов."
)

TEXT_CASE = (
    "Помнишь кейс с копи лювак на выступлении? Расскажу, как он устроен.\n\n"
    "<b>Задача:</b> протестировать спецпродукт, самый элитный кофе в мире.\n"
    "<b>Контент:</b> серия роликов. «Правда или миф» прогревает, дальше предзаказ, "
    "дальше ролик «За этот кофе мы заплатили 90 000 ₽» с призывом написать «ЛЮВАК».\n"
    "<b>Путь:</b> человек пишет слово, бот отвечает в директ, присылает набор и ссылку. "
    "Сайт был просто кассой.\n"
    "<b>Результат:</b> партия ушла за 2 дня. Ни одного ролика ради охвата, юмора или хайпа.\n\n"
    "Контент не должен быть красивым. Он должен работать."
)

TEXT_CONSULT = (
    "Хочешь, чтобы контент так же закрывал задачу твоего бизнеса?\n\n"
    "На консультации разберём твой контент и решим, какие форматы приведут "
    "<b>заявки, а не только лайки</b>: что снимать, о чём и куда вести человека дальше."
)

TEXT_CONSULT_OK = (
    "Отлично! Напиши мне в личку слово <b>КОНСУЛЬТАЦИЯ</b>, "
    "и договоримся о времени 🙌"
)

TEXT_AI = (
    "Что снимать, теперь понятно. Остаётся вопрос: когда на это всё найти время?\n\n"
    "Сценарии, тексты, монтаж и идеи под форматы можно отдать ИИ. "
    "Я учу этому лично: под твой бизнес и твои задачи, без сложных терминов. "
    "Сразу собираем рабочие связки, которыми ты пользуешься на следующий день."
)

TEXT_AI_OK = (
    "Супер! Напиши мне в личку слово <b>ОБУЧЕНИЕ</b>, "
    "расскажу формат и подберём время 🙌"
)

TEXT_MENU = "Выбирай, что нужно 👇"

KB_CHANNEL = {"inline_keyboard": [[{"text": "Подписаться на канал «Не ручками»", "url": CHANNEL_URL}]]}
KB_CASE = {"inline_keyboard": [[{"text": "Хочу так же в своём бизнесе", "callback_data": "consult"}]]}
KB_CONSULT = {"inline_keyboard": [[{"text": "Хочу консультацию", "callback_data": "consult"}]]}
KB_AI = {"inline_keyboard": [[{"text": "Хочу обучение ИИ", "callback_data": "ai"}]]}
KB_LENA = {"inline_keyboard": [[{"text": "Написать Лене", "url": LENA_URL}]]}
KB_MENU = {"inline_keyboard": [
    [{"text": "📄 Гайд по форматам", "callback_data": "gift"}],
    [{"text": "Канал «Не ручками»", "url": CHANNEL_URL}],
    [{"text": "Консультация по контенту", "callback_data": "consult"}],
    [{"text": "Обучение ИИ", "callback_data": "ai"}],
]}

# Цепочка после старта: (через сколько секунд, ключ сообщения)
CHAIN = [
    (30 * MIN, "case"),
    (2 * HOUR, "consult"),
    (24 * HOUR, "ai"),
]
MESSAGES = {
    "case": (TEXT_CASE, KB_CASE),
    "consult": (TEXT_CONSULT, KB_CONSULT),
    "ai": (TEXT_AI, KB_AI),
}

# ---------- Состояние ----------

API = f"https://api.telegram.org/bot{TOKEN}/"
state = {"pdf_file_id": None, "admin_chat": ADMIN_CHAT_ID or None,
         "scheduled": [], "started": [], "stats": {"start": 0, "consult": 0, "ai": 0}}


def load_state():
    global state
    try:
        with open(STATE_PATH, encoding="utf8") as f:
            saved = json.load(f)
        state.update({k: v for k, v in saved.items() if k in state})
        if ADMIN_CHAT_ID:
            state["admin_chat"] = ADMIN_CHAT_ID
        print(f"state loaded: {len(state['scheduled'])} scheduled", flush=True)
    except FileNotFoundError:
        print("no state yet", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"state load error: {type(e).__name__}", flush=True)


def save_state():
    try:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception as e:  # noqa: BLE001
        print(f"state save error: {type(e).__name__}", flush=True)


# ---------- Telegram ----------

def call(method, params=None, timeout=70):
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in (params or {}).items()}
    ).encode()
    req = urllib.request.Request(API + method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        print(f"{method} error: {type(e).__name__}", flush=True)
        return {"ok": False}


def send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if kb:
        p["reply_markup"] = kb
    return call("sendMessage", p)


def send_pdf(chat_id):
    if state["pdf_file_id"]:
        res = call("sendDocument", {"chat_id": chat_id, "document": state["pdf_file_id"]})
        if res.get("ok"):
            return res
    boundary = uuid.uuid4().hex
    with open(PDF_PATH, "rb") as f:
        blob = f.read()
    name = "Форматы_Reels_по_нишам.pdf"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{name}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API + "sendDocument", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode())
        if res.get("ok"):
            state["pdf_file_id"] = res["result"]["document"]["file_id"]
        return res
    except Exception as e:  # noqa: BLE001
        print(f"sendDocument error: {type(e).__name__}", flush=True)
        return {"ok": False}


def who(u):
    name = html.escape(" ".join(x for x in [u.get("first_name"), u.get("last_name")] if x))
    return f"{name} (@{u['username']})" if u.get("username") else name


def notify(text):
    if state["admin_chat"]:
        send(state["admin_chat"], text)


# ---------- Логика ----------

def on_start(chat_id, user, payload):
    state["stats"]["start"] += 1
    send(chat_id, TEXT_GIFT)
    send_pdf(chat_id)
    time.sleep(2)
    send(chat_id, TEXT_CHANNEL, KB_CHANNEL)
    if chat_id not in state["started"]:
        state["started"].append(chat_id)
        now = time.time()
        for delay, key in CHAIN:
            state["scheduled"].append([now + delay, chat_id, key])
        src = f", источник: {html.escape(payload)}" if payload else ""
        notify(f"👋 Новый человек в боте: {who(user)}{src}")
    save_state()


def on_request(chat_id, user, kind):
    state["stats"][kind] += 1
    if kind == "consult":
        send(chat_id, TEXT_CONSULT_OK, KB_LENA)
        label = "консультацию по контенту"
    else:
        send(chat_id, TEXT_AI_OK, KB_LENA)
        label = "обучение ИИ"
    # если человек уже оставил заявку, напоминание про консультацию больше не шлём
    if kind == "consult":
        state["scheduled"] = [s for s in state["scheduled"] if not (s[1] == chat_id and s[2] == "consult")]
    notify(f"🔥 Заявка на {label}: {who(user)}\n<a href=\"tg://user?id={user.get('id')}\">Открыть профиль</a>")
    save_state()


def handle(update):
    if "callback_query" in update:
        q = update["callback_query"]
        call("answerCallbackQuery", {"callback_query_id": q["id"]})
        chat_id = q["message"]["chat"]["id"]
        data = q.get("data")
        if data in ("consult", "ai"):
            on_request(chat_id, q["from"], data)
        elif data == "gift":
            send_pdf(chat_id)
        return
    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    chat_id, user, text = msg["chat"]["id"], msg.get("from", {}), msg["text"].strip()
    if (user.get("username") or "").lower() == ADMIN_USERNAME and not ADMIN_CHAT_ID:
        state["admin_chat"] = chat_id
        save_state()
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        on_start(chat_id, user, parts[1] if len(parts) > 1 else "")
    elif text.startswith("/myid"):
        send(chat_id, f"Твой chat id: <code>{chat_id}</code>")
    elif text.startswith("/stats") and str(chat_id) == str(state["admin_chat"]):
        s = state["stats"]
        send(chat_id, f"Всего: стартов {s['start']}, заявок на консультацию {s['consult']}, на обучение ИИ {s['ai']}")
    else:
        send(chat_id, TEXT_MENU, KB_MENU)


def run_scheduled():
    now = time.time()
    due = [s for s in state["scheduled"] if s[0] <= now]
    if not due:
        return
    for s in due:
        state["scheduled"].remove(s)
        _, chat_id, key = s
        text, kb = MESSAGES[key]
        send(chat_id, text, kb)
    save_state()


def setup():
    call("setMyCommands", {"commands": [{"command": "start", "description": "Забрать гайд по форматам"}]})
    call("setMyShortDescription", {"short_description": "Елена Сорокина · продюсер и ИИ-стратег. Гайд «25 форматов Reels, которые приносят заявки»."})
    call("setMyDescription", {"description": "Привет! Это бот Елены Сорокиной, продюсера и ИИ-стратега.\n\nЖми «Старт» и забирай гайд «25 форматов Reels, которые приносят заявки»: реальные ролики и цифры по нишам."})


def main():
    if not TOKEN:
        print("BOT_TOKEN не задан, выходим", flush=True)
        return
    if not call("getMe").get("ok"):
        print("getMe не прошёл, проверьте ключ", flush=True)
        sys.exit(1)
    load_state()
    call("deleteWebhook")
    setup()
    print("bot started", flush=True)
    offset, t_end = None, time.time() + RUN_SECONDS
    while time.time() < t_end:
        params = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        res = call("getUpdates", params, timeout=40)
        for upd in res.get("result", []) if res.get("ok") else []:
            offset = upd["update_id"] + 1
            try:
                handle(upd)
            except Exception as e:  # noqa: BLE001
                print(f"handle error: {type(e).__name__}", flush=True)
        if not res.get("ok"):
            time.sleep(3)
        run_scheduled()
    if offset is not None:
        call("getUpdates", {"offset": offset, "timeout": 0})
    save_state()
    s = state["stats"]
    print(f"bot stopped: starts={s['start']} consult={s['consult']} ai={s['ai']}", flush=True)


if __name__ == "__main__":
    main()
