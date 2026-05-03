"""Telegram Bot — Apple ID Manager (aiogram 3.x)"""
import asyncio, logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, BufferedInputFile,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import db
from config import BOT_TOKEN, ADMIN_ID
from playwright_automation import (
    do_login, get_devices_info, do_change_password,
    do_erase_device, open_find_my, open_mail, get_security_info
)

logger = logging.getLogger("apple_bot")

async def _make_step_sender(message: Message):
    """Создаёт коллбэк, который шлёт скриншот прямо в чат Telegram."""
    async def sender(step_name: str, screenshot: bytes):
        try:
            if screenshot:
                await message.answer_photo(
                    BufferedInputFile(screenshot, filename=f"{step_name}.png"),
                    caption=f"🖼 Шаг: <code>{step_name}</code>"
                )
            else:
                await message.answer(f"🖼 Шаг: <code>{step_name}</code> — скриншот не удался")
        except Exception as e:
            logger.warning(f"step sender failed: {e}")
    return sender

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

_tfa_queue: asyncio.Queue = asyncio.Queue()
_monitor_task = None
_autoprotect = False

class Setup(StatesGroup):
    email = State()
    password = State()
    q1_text = State()
    q1_answer = State()
    q2_text = State()
    q2_answer = State()
    q3_prompt = State()
    q3_text = State()
    q3_answer = State()

class ChangePass(StatesGroup):
    current = State()
    new1 = State()
    new2 = State()

class EraseConfirm(StatesGroup):
    waiting = State()

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ═══════════════════════════════════════════════════════════
# START
# ═══════════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Доступ запрещён.")
    cfg = db.get_config()
    email = cfg.get("email", "не задан")
    setup_ok = bool(email and cfg.get("q1_text"))
    status = "✅ Настроено" if setup_ok else "❌ Не настроено"
    text = (
        f"🍎 <b>Apple ID Manager</b>\n\n"
        f"👤 Аккаунт: <code>{email}</code>\n"
        f"⚙️ Статус: {status}\n\n"
        f"<b>Команды:</b>\n"
        f"/setup — настройка аккаунта\n"
        f"/login — проверить вход\n"
        f"/devices — список устройств\n"
        f"/findmy — Find My\n"
        f"/erase [имя] — стереть устройство\n"
        f"/changepass — сменить пароль\n"
        f"/mail — почта iCloud\n"
        f"/security — настройки безопасности\n"
        f"/autoprotect on|off\n"
        f"/monitor start|stop\n"
        f"/tfa [код] — ввести код 2FA"
    )
    await message.answer(text)


# ═══════════════════════════════════════════════════════════
# SETUP FSM
# ═══════════════════════════════════════════════════════════

@router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Доступ запрещён.")
    await message.answer("📧 Шаг 1/7 — Введи email Apple ID:")
    await state.set_state(Setup.email)

@router.message(Setup.email)
async def s_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text.strip())
    await message.answer("🔑 Шаг 2/7 — Введи пароль Apple ID:")
    await state.set_state(Setup.password)

@router.message(Setup.password)
async def s_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text.strip())
    await message.answer("❓ Шаг 3/7 — Введи ТЕКСТ первого контрольного вопроса (как в Apple):")
    await state.set_state(Setup.q1_text)

@router.message(Setup.q1_text)
async def s_q1t(message: Message, state: FSMContext):
    await state.update_data(q1_text=message.text.strip())
    await message.answer("❗️ Шаг 4/7 — Введи ОТВЕТ на первый вопрос:")
    await state.set_state(Setup.q1_answer)

@router.message(Setup.q1_answer)
async def s_q1a(message: Message, state: FSMContext):
    await state.update_data(q1_answer=message.text.strip())
    await message.answer("❓ Шаг 5/7 — Введи ТЕКСТ второго контрольного вопроса:")
    await state.set_state(Setup.q2_text)

@router.message(Setup.q2_text)
async def s_q2t(message: Message, state: FSMContext):
    await state.update_data(q2_text=message.text.strip())
    await message.answer("❗️ Шаг 6/7 — Введи ОТВЕТ на второй вопрос:")
    await state.set_state(Setup.q2_answer)

@router.message(Setup.q2_answer)
async def s_q2a(message: Message, state: FSMContext):
    await state.update_data(q2_answer=message.text.strip())
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("❓ Есть третий контрольный вопрос?", reply_markup=kb)
    await state.set_state(Setup.q3_prompt)

@router.message(Setup.q3_prompt, F.text.lower() == "да")
async def s_q3y(message: Message, state: FSMContext):
    await message.answer("❓ Шаг 7a — Введи ТЕКСТ третьего вопроса:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Setup.q3_text)

@router.message(Setup.q3_prompt, F.text.lower() == "нет")
async def s_q3n(message: Message, state: FSMContext):
    await state.update_data(q3_text="", q3_answer="")
    await _finish_setup(message, state)

@router.message(Setup.q3_text)
async def s_q3t(message: Message, state: FSMContext):
    await state.update_data(q3_text=message.text.strip())
    await message.answer("❗️ Введи ОТВЕТ на третий вопрос:")
    await state.set_state(Setup.q3_answer)

@router.message(Setup.q3_answer)
async def s_q3a(message: Message, state: FSMContext):
    await state.update_data(q3_answer=message.text.strip())
    await _finish_setup(message, state)

async def _finish_setup(message: Message, state: FSMContext):
    data = await state.get_data()
    db.set_config("email", data["email"])
    db.set_config("password", data["password"])
    db.set_config("q1_text", data.get("q1_text", ""))
    db.set_config("q1_answer", data.get("q1_answer", ""))
    db.set_config("q2_text", data.get("q2_text", ""))
    db.set_config("q2_answer", data.get("q2_answer", ""))
    db.set_config("q3_text", data.get("q3_text", ""))
    db.set_config("q3_answer", data.get("q3_answer", ""))
    await state.clear()
    await message.answer(
        f"✅ Настройка сохранена!\n\n"
        f"📧 {data['email']}\n"
        f"Теперь попробуй /login",
        reply_markup=ReplyKeyboardRemove()
    )


# ═══════════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════════

@router.message(Command("login"))
async def cmd_login(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    need = ["email", "password", "q1_text", "q1_answer", "q2_text", "q2_answer"]
    missing = [k for k in need if not cfg.get(k)]
    if missing:
        return await message.answer(f"❌ Не настроены поля: {', '.join(missing)}")
    await message.answer("🔐 Выполняю вход...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if result.get("ok"):
        await message.answer("✅ Вход выполнен. Делаю скриншот...")
        try:
            scr = await result["page"].screenshot()
            if scr:
                await message.answer_photo(BufferedInputFile(scr, "login.png"))
        except Exception as e:
            logger.warning(f"screenshot err {e}")
    else:
        await message.answer(f"❌ Ошибка: {result.get('error', 'unknown')}")
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass


# ═══════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════

@router.message(Command("devices"))
async def cmd_devices(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    if not cfg.get("email"):
        return await message.answer("Сначала /setup")
    await message.answer("⏳ Получаю устройства...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ Вход не удался: {result.get('error')}")
    devs = await get_devices_info(result["page"])
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass

    if not devs.get("devices"):
        return await message.answer("Устройства не найдены или страница изменилась.")
    lines = ["📱 <b>Устройства:</b>\n"]
    for d in devs["devices"]:
        lines.append(f"• {d.get('name', '?')} — {d.get('model', '?')}")
    await message.answer("\n".join(lines))


# ═══════════════════════════════════════════════════════════
# CHANGE PASSWORD
# ═══════════════════════════════════════════════════════════

@router.message(Command("changepass"))
async def cmd_changepass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введи текущий пароль:")
    await state.set_state(ChangePass.current)

@router.message(ChangePass.current)
async def cp_current(message: Message, state: FSMContext):
    await state.update_data(current=message.text.strip())
    await message.answer("Введи новый пароль:")
    await state.set_state(ChangePass.new1)

@router.message(ChangePass.new1)
async def cp_new1(message: Message, state: FSMContext):
    await state.update_data(new1=message.text.strip())
    await message.answer("Повтори новый пароль:")
    await state.set_state(ChangePass.new2)

@router.message(ChangePass.new2)
async def cp_new2(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if data["new1"] != message.text.strip():
        return await message.answer("❌ Пароли не совпадают. Начни заново: /changepass")
    cfg = db.get_config()
    await message.answer("⏳ Меняю пароль...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ Вход не удался: {result.get('error')}")
    r2 = await do_change_password(
        result["page"], data["current"], data["new1"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", "")
    )
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass
    await message.answer("✅ Пароль изменён (если реализация поддерживает)" if r2.get("ok") else "❌ Не удалось")


# ═══════════════════════════════════════════════════════════
# ERASE
# ═══════════════════════════════════════════════════════════

@router.message(Command("erase"))
async def cmd_erase(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Использование: /erase [имя устройства]")
    await state.update_data(device_name=args[1].strip())
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="ДА")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        f"⚠️ Подтверди стирание устройства <code>{args[1]}</code>\n\nВведи ДА:",
        reply_markup=kb
    )
    await state.set_state(EraseConfirm.waiting)

@router.message(EraseConfirm.waiting)
async def erase_confirmed(message: Message, state: FSMContext):
    if message.text.strip().upper() != "ДА":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    data = await state.get_data()
    await state.clear()
    cfg = db.get_config()
    await message.answer("⏳ Выполняю...", reply_markup=ReplyKeyboardRemove())
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ Вход не удался: {result.get('error')}")
    r2 = await do_erase_device(
        result["page"], data["device_name"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", "")
    )
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass
    await message.answer("✅ Команда отправлена" if r2.get("ok") else "❌ Ошибка")


# ═══════════════════════════════════════════════════════════
# FIND MY / MAIL / SECURITY
# ═══════════════════════════════════════════════════════════

@router.message(Command("findmy"))
async def cmd_findmy(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    await message.answer("⏳ Открываю Find My...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ {result.get('error')}")
    r2 = await open_find_my(result["page"])
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass
    if r2.get("screenshot"):
        await message.answer_photo(BufferedInputFile(r2["screenshot"], "findmy.png"))

@router.message(Command("mail"))
async def cmd_mail(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    await message.answer("⏳ Открываю почту...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ {result.get('error')}")
    r2 = await open_mail(result["page"])
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass
    emails = r2.get("emails", [])
    if not emails:
        return await message.answer("📧 Нет новых писем или требуется дополнительная авторизация.")
    # можно дописать разбор писем при необходимости

@router.message(Command("security"))
async def cmd_security(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    await message.answer("⏳ Получаю настройки...")
    result = await do_login(
        cfg["email"], cfg["password"],
        cfg["q1_text"], cfg["q1_answer"],
        cfg["q2_text"], cfg["q2_answer"],
        cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
        tfa_queue=_tfa_queue
    )
    if not result.get("ok"):
        return await message.answer(f"❌ {result.get('error')}")
    r2 = await get_security_info(result["page"])
    try:
        await result["context"].close()
        await result["browser"].close()
        await result["playwright"].stop()
    except:
        pass
    info = r2.get("info", "")
    await message.answer(f"🔐 <b>Настройки безопасности:</b>\n<pre>{info[:3500]}</pre>")


# ═══════════════════════════════════════════════════════════
# AUTO PROTECT / MONITOR / TFA / STATUS
# ═══════════════════════════════════════════════════════════

@router.message(Command("autoprotect"))
async def cmd_autoprotect(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    global _autoprotect
    if len(args) > 1 and args[1].lower() in ("on", "1", "yes", "true", "вкл"):
        _autoprotect = True
        return await message.answer("🛡 AutoProtect ВКЛЮЧЕН")
    elif len(args) > 1 and args[1].lower() in ("off", "0", "no", "false", "выкл"):
        _autoprotect = False
        return await message.answer("🛡 AutoProtect ВЫКЛЮЧЕН")
    else:
        status = "✅ ON" if _autoprotect else "❌ OFF"
        return await message.answer(f"🛡 AutoProtect: <b>{status}</b>\n\nИспользование: /autoprotect on|off")

@router.message(Command("tfa"))
async def cmd_tfa(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Введи код: /tfa 123456")
    code = args[1].strip()
    await _tfa_queue.put(code)
    await message.answer("⏳ Код отправлен в очередь входа...")

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    cfg = db.get_config()
    email = cfg.get("email", "не задан")
    setup_ok = bool(cfg.get("email") and cfg.get("q1_text"))
    monitor = _monitor_task is not None and not _monitor_task.done()
    text = (
        f"📊 <b>Статус</b>\n\n"
        f"👤 Email: <code>{email}</code>\n"
        f"⚙️ Настройки: {'✅' if setup_ok else '❌'}\n"
        f"👁 Мониторинг: {'✅' if monitor else '❌'}\n"
        f"🛡 AutoProtect: {'✅ ON' if _autoprotect else '❌ OFF'}"
    )
    await message.answer(text)


# ═══════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════

def get_dispatcher():
    return dp

def get_bot():
    return bot
