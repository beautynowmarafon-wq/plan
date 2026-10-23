"""Telegram-бот @sorockina_ai_bot: воронка после игры «Контент-шар».

Запускается в GitHub Actions (long polling). Ключ бота берётся из секрета BOT_TOKEN.
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

CHANNEL_URL = "https://t.me/ne_ruchkami"
YOUTUBE_URL = "https://www.youtube.com/watch?v=t-HqUdZIPl4"
LENA_URL = "https://t.me/Elen_Sorockina"

# Через сколько секунд после старта приходят следующие сообщения
DELAY_YOUTUBE = 20 * 60
DELAY_CONSULT = 60 * 60

TEXT_GIFT = (
    "Шар передал, что ты за форматами 🔮\n\n"
    "Держи гайд <b>«25 форматов Reels, которые приносят заявки»</b>. "
    "Здоровье, красота, эксперты, производство: у каждого формата реальный ролик и цифры.\n\n"
    "Найди свой и сними его уже на этой неделе."
)
TEXT_CHANNEL = (
    "А теперь честно: шар пошутил, а система работает 😉\n\n"
    "В канале <b>«Не ручками»</b> показываю, как собрать контент-систему с ИИ: "
    "без копирайтера, монтажёра и выгорания. Разборы, рабочие связки с Claude и готовые промпты."
)
TEXT_YOUTUBE = (
    "Если хочешь глубже про ИИ в контенте, вот моё видео:\n\n"
    "<b>«Освой 80% возможностей Claude за 15 минут»</b>. "
    "10 приёмов, которые почти никто не использует."
)
TEXT_CONSULT = (
    "Хочешь понять, какой формат сработает именно в твоём бизнесе?\n\n"
    "Я перевожу задачи бизнеса на язык контента. На консультации разберём твой контент "
    "и решим, что снимать, чтобы приходили <b>заявки, а не только лайки</b>."
)
TEXT_CONSULT_OK = (
    "Отлично! Напиши мне в личку слово <b>КОНСУЛЬТАЦИЯ</b>, "
    "и договоримся о времени 🙌"
)
TEXT_MENU = "Выбирай, что нужно 👇"

KB_CHANNEL = {"inline_keyboard": [[{"text": "Подписаться на канал «Не ручками»", "url": CHANNEL_URL}]]}
KB_YOUTUBE = {"inline_keyboard": [[{"text": "▶ Смотреть видео", "url": YOUTUBE_URL}]]}
KB_CONSULT = {"inline_keyboard": [[{"text": "Хочу консультацию", "callback_data": "consult"}]]}
KB_LENA = {"inline_keyboard": [[{"text": "Написать Лене", "url": LENA_URL}]]}
KB_MENU = {"inline_keyboard": [
    [{"text": "📄 Гайд по форматам", "callback_data": "gift"}],
    [{"text": "Канал «Не ручками»", "url": CHANNEL_URL}],
    [{"text": "▶ Видео про Claude", "url": YOUTUBE_URL}],
    [{"text": "Хочу консультацию", "callback_data": "consult"}],
]}

API = f"https://api.telegram.org/bot{TOKEN}/"
pdf_file_id = None
admin_chat = ADMIN_CHAT_ID or None
scheduled = []  # (when, chat_id, kind)
started = set()
stats = {"start": 0, "consult": 0}


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
    global pdf_file_id
    if pdf_file_id:
        return call("sendDocument", {"chat_id": chat_id, "document": pdf_file_id})
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
            pdf_file_id = res["result"]["document"]["file_id"]
        return res
    except Exception as e:  # noqa: BLE001
        print(f"sendDocument error: {type(e).__name__}", flush=True)
        return {"ok": False}


def who(u):
    name = html.escape(" ".join(x for x in [u.get("first_name"), u.get("last_name")] if x))
    return f"{name} (@{u['username']})" if u.get("username") else name


def notify(text):
    if admin_chat:
        send(admin_chat, text)


def on_start(chat_id, user, payload):
    stats["start"] += 1
    send(chat_id, TEXT_GIFT)
    send_pdf(chat_id)
    time.sleep(2)
    send(chat_id, TEXT_CHANNEL, KB_CHANNEL)
    if chat_id not in started:
        started.add(chat_id)
        now = time.time()
        scheduled.append((now + DELAY_YOUTUBE, chat_id, "youtube"))
        scheduled.append((now + DELAY_CONSULT, chat_id, "consult"))
        src = f", источник: {payload}" if payload else ""
        notify(f"👋 Новый человек в боте: {who(user)}{src}")


def on_consult(chat_id, user):
    stats["consult"] += 1
    send(chat_id, TEXT_CONSULT_OK, KB_LENA)
    notify(f"🔥 Заявка на консультацию: {who(user)}\n<a href=\"tg://user?id={user.get('id')}\">Открыть профиль</a>")


def handle(update):
    global admin_chat
    if "callback_query" in update:
        q = update["callback_query"]
        call("answerCallbackQuery", {"callback_query_id": q["id"]})
        chat_id = q["message"]["chat"]["id"]
        if q.get("data") == "consult":
            on_consult(chat_id, q["from"])
        elif q.get("data") == "gift":
            send_pdf(chat_id)
        return
    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    chat_id, user, text = msg["chat"]["id"], msg.get("from", {}), msg["text"].strip()
    if (user.get("username") or "").lower() == ADMIN_USERNAME and not ADMIN_CHAT_ID:
        admin_chat = chat_id
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        on_start(chat_id, user, parts[1] if len(parts) > 1 else "")
    elif text.startswith("/myid"):
        send(chat_id, f"Твой chat id: <code>{chat_id}</code>")
    elif text.startswith("/stats") and str(chat_id) == str(admin_chat):
        send(chat_id, f"С начала этого запуска: стартов {stats['start']}, заявок {stats['consult']}")
    else:
        send(chat_id, TEXT_MENU, KB_MENU)


def run_scheduled():
    now = time.time()
    due = [s for s in scheduled if s[0] <= now]
    for s in due:
        scheduled.remove(s)
        _, chat_id, kind = s
        if kind == "youtube":
            send(chat_id, TEXT_YOUTUBE, KB_YOUTUBE)
        else:
            send(chat_id, TEXT_CONSULT, KB_CONSULT)


def setup():
    call("setMyCommands", {"commands": [{"command": "start", "description": "Забрать гайд по форматам"}]})
    call("setMyShortDescription", {"short_description": "Елена Сорокина · продюсер и ИИ-стратег. Гайд «25 форматов Reels, которые приносят заявки»."})
    call("setMyDescription", {"description": "Привет! Это бот Елены Сорокиной, продюсера и ИИ-стратега.\n\nЖми «Старт» и забирай гайд «25 форматов Reels, которые приносят заявки»: реальные ролики и цифры по нишам."})


def main():
    if not TOKEN:
        print("BOT_TOKEN не задан, выходим", flush=True)
        return
    me = call("getMe")
    if not me.get("ok"):
        print("getMe не прошёл, проверьте ключ", flush=True)
        sys.exit(1)
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
    # перед выходом подтверждаем полученные обновления
    if offset is not None:
        call("getUpdates", {"offset": offset, "timeout": 0})
    print(f"bot stopped: starts={stats['start']} consult={stats['consult']}", flush=True)


if __name__ == "__main__":
    main()
