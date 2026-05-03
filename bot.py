"""
Telegram-бот полной автоматизации Apple ID.
Команды: /setup /login /devices /findmy /erase /changepass /mail /security /monitor /autoprotect
"""
import asyncio
import os
import sys
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    BufferedInputFile,
)

import db
from config import OWNER_TELEGRAM_ID, TELEGRAM_TOKEN
from logger import get_logger
from utils import mask_email, validate_apple_password

logger = get_logger()
router = Router()

_bot_instance: Bot | None = None
_monitor_task: asyncio.Task | None = None
_tfa_queue: asyncio.Queue = asyncio.Queue()
_tfa_queues: dict = {}

# FSM состояния
class Setup(StatesGroup):
    email = State()
    password = State()
    q1_text = State()
    q1_answer = State()
    q2_text = State()
    q2_answer = State()
    q3_text = State()
    q3_answer = State()
    confirm = State()

class ChangePass(StatesGroup):
    current = State()
    new1 = State()
    new2 = State()

class EraseConfirm(StatesGroup):
    waiting = State()

class NewDeviceAction(StatesGroup):
    change_pass_current = State()
    change_pass_new1 = State()
    change_pass_new2 = State()
    erase_confirm = State()

class TwoFA(StatesGroup):
    code = State()
    waiting_code = State()

def is_owner(uid: int) -> bool:
    return uid == OWNER_TELEGRAM_ID

async def guard(obj) -> bool:
    if isinstance(obj, Message):
        if not is_owner(obj.from_user.id):
            await obj.answer("⛔ Доступ запрещён.")
            return False
    elif isinstance(obj, CallbackQuery):
        if not is_owner(obj.from_user.id):
            await obj.answer("⛔ Доступ запрещён.", show_alert=True)
            return False
    return True

async def notify(text: str, photo: bytes | None = None) -> None:
    if not _bot_instance:
        return
    try:
        if photo:
            await _bot_instance.send_photo(
                OWNER_TELEGRAM_ID,
                BufferedInputFile(photo, "screen.png"),
                caption=text[:1024], parse_mode="HTML"
            )
        else:
            await _bot_instance.send_message(
                OWNER_TELEGRAM_ID, text, parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"[notify] {e}")

async def notify_owner(text: str, photo: bytes | None = None) -> None:
    """Alias for notify function."""
    await notify(text, photo)

def _get_cfg() -> dict:
    return db.get_setup()

def _acc_id() -> int:
    """Возвращает account_id из БД (создаёт если нет)."""
    cfg = _get_cfg()
    if not cfg["email"]:
        return 0
    accs = db.get_all_accounts()
    for a in accs:
        if a["email"] == cfg["email"].lower():
            return a["id"]
    return 0

def _ensure_account() -> int:
    """Создаёт аккаунт в БД если не существует."""
    cfg = _get_cfg()
    if not cfg["email"] or not cfg["password"]:
        return 0
    accs = db.get_all_accounts()
    for a in accs:
        if a["email"] == cfg["email"].lower():
            db.update_account_password(a["id"], cfg["password"])
            return a["id"]
    return db.add_account(cfg["email"], cfg["password"])

# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------

def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Устройства"), KeyboardButton(text="📍 Локатор")],
        [KeyboardButton(text="🔑 Сменить пароль"), KeyboardButton(text="📬 Почта")],
        [KeyboardButton(text="🔒 Безопасность"), KeyboardButton(text="⚙️ Настройки")],
    ], resize_keyboard=True)

def yn_kb(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=yes_data),
        InlineKeyboardButton(text="❌ Нет", callback_data=no_data),
    ]])

# ---------------------------------------------------------------------------
# /start /help
# ---------------------------------------------------------------------------

@router.message(Command("start", "help"))
async def cmd_start(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.clear()
    try:
        db.init_db()
        cfg = _get_cfg()
        setup_ok = db.is_setup_complete()
    except Exception:
        cfg = {"email": "", "monitor": "off", "autoprotect": "off"}
        setup_ok = False
    mon = cfg.get("monitor", "off")
    ap = cfg.get("autoprotect", "off")
    status = (
        f"📧 Email: {mask_email(cfg['email']) if cfg['email'] else '—'}\n"
        f"🔍 Мониторинг: {'✅ вкл' if mon=='on' else '⏸ выкл'}\n"
        f"🛡 Автозащита: {'✅ вкл' if ap=='on' else '⏸ выкл'}\n"
    )
    text = (
        "🍎 <b>iCloud Monitor Bot</b>\n\n"
        f"{status}\n"
        "<b>Команды:</b>\n"
        "/setup — настройка email + вопросы\n"
        "/login — войти в аккаунт\n"
        "/devices — список устройств + IMEI\n"
        "/findmy — локатор устройств\n"
        "/erase [имя] — стереть устройство\n"
        "/changepass — сменить пароль\n"
        "/mail — проверить почту\n"
        "/security — настройки безопасности\n"
        "/monitor start|stop — мониторинг\n"
        "/autoprotect on|off — автозащита\n"
        "/tfa [код] — ввести 2FA код\n"
        "/cancel — отменить действие\n"
    )
    if not setup_ok:
        text += "\n⚠️ <b>Сначала выполните /setup</b>"
    await m.answer(text, parse_mode="HTML", reply_markup=main_kb())

@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.clear()
    await m.answer("❌ Отменено.", reply_markup=main_kb())

# ---------------------------------------------------------------------------
# /tfa — ввод 2FA кода
# ---------------------------------------------------------------------------

@router.message(Command("tfa"))
async def cmd_tfa(m: Message, state: FSMContext = None):
    if not await guard(m): return
    # If there are per-account queues, ask which account
    if _tfa_queues:
        if len(_tfa_queues) == 1:
            acc_id = next(iter(_tfa_queues))
            if state:
                await state.update_data(tfa_account_id=acc_id)
                await state.set_state(TwoFA.waiting_code)
            await m.answer(f"Введите 6-значный код 2FA для аккаунта #{acc_id}:")
        else:
            await m.answer("Несколько активных сессий 2FA. Используйте /tfa <код>")
        return
    parts = m.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Нет активных сессий 2FA.")
        return
    code = parts[1].strip()
    if not code.isdigit() or len(code) != 6:
        await m.answer("❌ Код должен быть 6 цифр.")
        return
    await _tfa_queue.put(code)
    await m.answer("✅ Код 2FA передан боту.")

# ---------------------------------------------------------------------------
# /setup — пошаговая настройка
# ---------------------------------------------------------------------------

@router.message(Command("setup"))
async def cmd_setup(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.clear()
    await state.set_state(Setup.email)
    await m.answer(
        "⚙️ <b>Настройка Apple ID бота</b>\n\n"
        "Шаг 1/8: Введите ваш Apple ID (email):",
        parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
    )

@router.message(StateFilter(Setup.email))
async def setup_email(m: Message, state: FSMContext):
    if not await guard(m): return
    from utils import is_valid_email
    email = m.text.strip()
    if not is_valid_email(email):
        await m.answer("❌ Некорректный email. Попробуйте ещё раз:"); return
    await state.update_data(email=email)
    await state.set_state(Setup.password)
    await m.answer(
        "Шаг 2/8: Введите пароль Apple ID:\n<i>(сообщение будет удалено)</i>",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.password))
async def setup_password(m: Message, state: FSMContext):
    if not await guard(m): return
    pwd = m.text.strip()
    try: await m.delete()
    except Exception: pass
    err = validate_apple_password(pwd)
    if err:
        await m.answer(f"❌ {err}\nПопробуйте ещё раз:"); return
    await state.update_data(password=pwd)
    await state.set_state(Setup.q1_text)
    await m.answer(
        "Шаг 3/8: Введите текст первого контрольного вопроса\n"
        "<i>Пример: 你的理想工作是什么？</i>",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q1_text))
async def setup_q1_text(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q1_text=m.text.strip())
    await state.set_state(Setup.q1_answer)
    await m.answer(
        f"Шаг 4/8: Введите ответ на первый вопрос:\n"
        f"«{m.text.strip()}»\n\n<i>Вводите ТОЧНО как в Apple ID</i>",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q1_answer))
async def setup_q1_answer(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q1_answer=m.text.strip())
    await state.set_state(Setup.q2_text)
    await m.answer(
        "Шаг 5/8: Введите текст второго контрольного вопроса\n"
        "<i>Пример: 你少年时代最好的朋友叫什么名字？</i>",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q2_text))
async def setup_q2_text(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q2_text=m.text.strip())
    await state.set_state(Setup.q2_answer)
    await m.answer(
        f"Шаг 6/8: Введите ответ на второй вопрос:\n"
        f"«{m.text.strip()}»",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q2_answer))
async def setup_q2_answer(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q2_answer=m.text.strip())
    await state.set_state(Setup.q3_text)
    await m.answer(
        "Шаг 7/8: Введите текст третьего контрольного вопроса\n"
        "<i>Пример: 你父母是在哪里相识的？</i>",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q3_text))
async def setup_q3_text(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q3_text=m.text.strip())
    await state.set_state(Setup.q3_answer)
    await m.answer(
        f"Шаг 8/8: Введите ответ на третий вопрос:\n"
        f"«{m.text.strip()}»",
        parse_mode="HTML"
    )

@router.message(StateFilter(Setup.q3_answer))
async def setup_q3_answer(m: Message, state: FSMContext):
    if not await guard(m): return
    await state.update_data(q3_answer=m.text.strip())
    data = await state.get_data()
    await state.set_state(Setup.confirm)
    text = (
        "✅ <b>Проверьте данные:</b>\n\n"
        f"📧 Email: <code>{data['email']}</code>\n"
        f"🔑 Пароль: {'*' * len(data['password'])}\n"
        f"❓ Вопрос 1: {data['q1_text']}\n"
        f"   Ответ: <code>{data['q1_answer']}</code>\n"
        f"❓ Вопрос 2: {data['q2_text']}\n"
        f"   Ответ: <code>{data['q2_answer']}</code>\n"
        f"❓ Вопрос 3: {data['q3_text']}\n"
        f"   Ответ: <code>{data['q3_answer']}</code>\n\n"
        "Сохранить?"
    )
    await m.answer(text, parse_mode="HTML",
                   reply_markup=yn_kb("setup_save", "setup_cancel"))

@router.callback_query(F.data == "setup_save")
async def setup_save(cb: CallbackQuery, state: FSMContext):
    if not await guard(cb): return
    data = await state.get_data()
    await state.clear()
    db.set_config("email", data["email"])
    db.set_config("password", data["password"])
    db.set_config("q1_text", data["q1_text"])
    db.set_config("q1_answer", data["q1_answer"])
    db.set_config("q2_text", data["q2_text"])
    db.set_config("q2_answer", data["q2_answer"])
    db.set_config("q3_text", data.get("q3_text", ""))
    db.set_config("q3_answer", data.get("q3_answer", ""))
    _ensure_account()
    await cb.message.answer(
        f"✅ <b>Настройка сохранена!</b>\n"
        f"Email: {data['email']}\n\n"
        "Теперь можно использовать /login /devices /findmy",
        parse_mode="HTML", reply_markup=main_kb()
    )
    await cb.answer()

@router.callback_query(F.data == "setup_cancel")
async def setup_cancel_cb(cb: CallbackQuery, state: FSMContext):
    if not await guard(cb): return
    await state.clear()
    await cb.message.answer("❌ Настройка отменена.", reply_markup=main_kb())
    await cb.answer()

# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------

@router.message(Command("login"))
async def cmd_login(m: Message):
    if not await guard(m): return
    if not db.is_setup_complete():
        await m.answer("⚠️ Сначала выполните /setup"); return
    await m.answer("🔄 Выполняю вход в Apple ID…")
    try:
        from playwright_automation import apple_signin, _get_browser, _new_page
        cfg = _get_cfg()
        acc_id = _ensure_account()
        pw, ctx = await _get_browser(acc_id)
        page = await _new_page(ctx)
        try:
            r = await asyncio.wait_for(
                apple_signin(page, cfg["email"], cfg["password"],
                             cfg["q1_text"], cfg["q1_answer"],
                             cfg["q2_text"], cfg["q2_answer"],
                             cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
                             _tfa_queue, notify),
                timeout=180
            )
            if r["ok"]:
                await m.answer("✅ <b>Вошёл в аккаунт успешно!</b>\n\nДалее: /devices /findmy /mail",
                               parse_mode="HTML", reply_markup=main_kb())
            else:
                await m.answer(f"❌ Ошибка входа: {r['error']}", reply_markup=main_kb())
                if r.get("screenshot"):
                    await m.answer_photo(BufferedInputFile(r["screenshot"], "error.png"), caption="Скриншот ошибки")
        except asyncio.TimeoutError:
            await m.answer("⏱ Таймаут входа. Попробуйте ещё раз.")
        finally:
            await ctx.close()
            await pw.stop()
    except ImportError:
        await m.answer("❌ Playwright не установлен. Установите: pip install playwright && playwright install chromium")
    except Exception as e:
        logger.error(f"[login] {e}")
        await m.answer(f"❌ Ошибка: {e}")

# ---------------------------------------------------------------------------
# /devices
# ---------------------------------------------------------------------------

@router.message(Command("devices"))
@router.message(F.text == "📱 Устройства")
async def cmd_devices(m: Message):
    if not await guard(m): return
    if not db.is_setup_complete():
        await m.answer("⚠️ Сначала выполните /setup"); return
    await m.answer("🔄 Загружаю список устройств…\n<i>~2-3 минуты</i>", parse_mode="HTML")
    try:
        from playwright_automation import get_devices, _get_browser, _new_page
        cfg = _get_cfg()
        acc_id = _ensure_account()
        pw, ctx = await _get_browser(acc_id)
        page = await _new_page(ctx)
        try:
            r = await asyncio.wait_for(
                get_devices(page, cfg["email"], cfg["password"],
                            cfg["q1_text"], cfg["q1_answer"],
                            cfg["q2_text"], cfg["q2_answer"],
                            cfg.get("q3_text", ""), cfg.get("q3_answer", ""),
                            _tfa_queue, notify),
                timeout=240
            )
            if not r["ok"]:
                await m.answer(f"❌ Ошибка: {r['error']}", reply_markup=main_kb())
                return
            devices = r.get("devices", [])
            if not devices:
                await m.answer("📱 Устройств не найдено.", reply_markup=main_kb())
                return
            # Сохраняем в БД
            for d in devices:
                name = d.get("name") or d.get("description") or ""
                if name:
                    db.save_known_device(acc_id, name, d.get("model", ""), d.get("imei", ""))
                    db.upsert_device(acc_id, {
                        "device_id": name, "name": name,
                        "model": d.get("model", ""), "version": d.get("version", ""),
                        "imei": d.get("imei", ""),
                    })
            # Форматируем
            lines = []
            for i, d in enumerate(devices, 1):
                name = d.get("name") or "—"
                model = d.get("model") or "—"
                imei = d.get("imei") or "—"
                lines.append(f"<b>{i}. {name}</b>\n   📱 {model}\n   🔑 IMEI: <code>{imei}</code>")
            text = f"📱 <b>Устройства ({len(devices)}):</b>\n\n" + "\n\n".join(lines)
            await m.answer(text, parse_mode="HTML", reply_markup=main_kb())
        except asyncio.TimeoutError:
            await m.answer("⏱ Таймаут. Попробуйте ещё раз.")
        finally:
            await ctx.close()
            await pw.stop()
    except ImportError:
        await m.answer("❌ Playwright не установлен.")
    except Exception as e:
        logger.error(f"[devices] {e}")
        await m.answer(f"❌ Ошибка: {e}")

# ---------------------------------------------------------------------------
# /monitor
# ---------------------------------------------------------------------------

@router.message(Command("monitor"))
async def cmd_monitor(m: Message):
    if not await guard(m): return
    from scheduler import set_monitoring, is_monitoring_active
    parts = m.text.strip().split()
    if len(parts) < 2:
        status = "включён" if is_monitoring_active() else "выключен"
        await m.answer(f"🔍 Мониторинг: {status}\n\nИспользуйте: /monitor start|stop")
        return
    action = parts[1].lower()
    if action in ("start", "on"):
        set_monitoring(True)
        db.set_config("monitor", "on")
        await m.answer("✅ Мониторинг включён")
    elif action in ("stop", "off"):
        set_monitoring(False)
        db.set_config("monitor", "off")
        await m.answer("⏸ Мониторинг выключен")
    else:
        await m.answer("❌ Используйте: /monitor start|stop")

# ---------------------------------------------------------------------------
# /autoprotect
# ---------------------------------------------------------------------------

@router.message(Command("autoprotect"))
async def cmd_autoprotect(m: Message):
    if not await guard(m): return
    parts = m.text.strip().split()
    current = db.get_config("autoprotect", "off")
    if len(parts) < 2:
        status = "включена" if current == "on" else "выключена"
        await m.answer(f"🛡 Автозащита: {status}\n\nИспользуйте: /autoprotect on|off")
        return
    action = parts[1].lower()
    if action in ("on", "1"):
        db.set_config("autoprotect", "on")
        await m.answer("✅ Автозащита включена\nПри обнаружении нового устройства бот автоматически:\n- Сменит пароль\n- Включит режим пропажи")
    elif action in ("off", "0"):
        db.set_config("autoprotect", "off")
        await m.answer("⏸ Автозащита выключена")
    else:
        await m.answer("❌ Используйте: /autoprotect on|off")

# ---------------------------------------------------------------------------
# Создание бота и диспетчера
# ---------------------------------------------------------------------------

def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    global _bot_instance
    bot = Bot(token=TELEGRAM_TOKEN)
    _bot_instance = bot
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return bot, dp
