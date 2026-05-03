"""
Клавиатуры и меню для Telegram-бота.
"""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📬 Почта iCloud"), KeyboardButton(text="📱 Мои устройства")],
            [KeyboardButton(text="📍 Find My"), KeyboardButton(text="👤 Аккаунт")],
            [KeyboardButton(text="📊 Аналитика"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="🗄️ Резервные копии"), KeyboardButton(text="🚨 Экстренные действия")],
        ],
        resize_keyboard=True,
    )

def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="main")]]
    )

def mail_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Последние письма", callback_data="mail_last")],
            [InlineKeyboardButton(text="🍎 Apple-события", callback_data="mail_apple")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def devices_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все устройства", callback_data="devices_all")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def findmy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все устройства", callback_data="devices_all")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def account_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="acc_list")],
            [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def account_item_menu(acc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Устройства", callback_data=f"acc_devices_{acc_id}")],
            [InlineKeyboardButton(text="💾 Сохранить IMEI/модели", callback_data=f"acc_savedevices_{acc_id}")],
            [InlineKeyboardButton(text="🔄 Обновить данные", callback_data=f"acc_refresh_{acc_id}")],
            [InlineKeyboardButton(text="📬 Письма аккаунта", callback_data=f"acc_mail_{acc_id}")],
            [InlineKeyboardButton(text="🔑 Сменить пароль", callback_data=f"acc_chpwd_{acc_id}")],
            [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"acc_delete_{acc_id}")],
            [InlineKeyboardButton(text="◀️ К списку", callback_data="acc_list")],
        ]
    )

def device_actions_menu(dev_db_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔊 Звуковой сигнал", callback_data=f"dev_sound_{dev_db_id}")],
            [InlineKeyboardButton(text="🔒 Режим пропажи", callback_data=f"dev_lost_{dev_db_id}")],
            [InlineKeyboardButton(text="💥 Стереть", callback_data=f"dev_wipe_{dev_db_id}")],
            [InlineKeyboardButton(text="🗑 Удалить из iCloud", callback_data=f"dev_remove_{dev_db_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="devices_all")],
        ]
    )

def analytics_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="an_stats")],
            [InlineKeyboardButton(text="🥧 График устройств", callback_data="an_pie")],
            [InlineKeyboardButton(text="📄 Экспорт устройств", callback_data="an_csv")],
            [InlineKeyboardButton(text="📧 Экспорт писем", callback_data="an_mails_csv")],
            [InlineKeyboardButton(text="📋 Журнал действий", callback_data="an_actions")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Включить мониторинг", callback_data="mon_start")],
            [InlineKeyboardButton(text="⏸ Выключить мониторинг", callback_data="mon_stop")],
            [InlineKeyboardButton(text="📋 Логи", callback_data="set_logs")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def backup_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Локальный бэкап", callback_data="bk_now")],
            [InlineKeyboardButton(text="📦 Dropbox", callback_data="bk_dropbox")],
            [InlineKeyboardButton(text="☁️ Google Drive", callback_data="bk_gdrive")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def emergency_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Lost Mode всем", callback_data="em_lost_all")],
            [InlineKeyboardButton(text="💥 Стереть всё", callback_data="em_wipe_all")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def monitoring_control() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Запустить мониторинг", callback_data="mon_start")],
            [InlineKeyboardButton(text="⏹ Остановить", callback_data="mon_stop")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main")],
        ]
    )

def confirm_menu(confirm_data: str, cancel_data: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=confirm_data),
                InlineKeyboardButton(text="❌ Нет", callback_data=cancel_data),
            ]
        ]
    )
