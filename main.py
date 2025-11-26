import asyncio
import json
import math
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    CallbackQuery,
)

from openpyxl import Workbook

# ----------------- CONFIG -----------------
BOT_TOKEN = "8579881937:AAGX0oiDtE-uTx2zRdkWjsrD4N46oexG80E"   # <-- вставь сюда токен
ADMIN_ID = 880339036                  # <-- твой id (как ты прислал)

HISTORY_FILE = "history.json"
ALLOWED_FILE = "allowed_users.json"
PENDING_FILE = "pending_requests.json"

# calculation params (подогнать при желании)
OLD_MONTHS_LIMIT = 35   # "старые месяцы" ограничение (см. пример)
DEDUCTION_MONTHS = 2    # вычет месяцев из новых
COEF_OLD = 1.25
COEF_NEW = 1.75

# ------------------------------------------

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ---------- Helpers: storage ----------
def ensure_file(path: str, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)


def load_json(path: str):
    ensure_file(path, [])
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# init files
ensure_file(HISTORY_FILE, [])
ensure_file(ALLOWED_FILE, [ADMIN_ID])  # admin allowed by default
ensure_file(PENDING_FILE, [])


# ---------- State stores (simple) ----------
USER_STATE: Dict[int, str] = {}       # uid -> state
USER_DATA: Dict[int, Dict[str, Any]] = {}  # uid -> data

# states: "idle", "wait_d1", "wait_d2", "wait_used_work", "wait_used_cal", "wait_prog"


# ---------- Utilities ----------
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def is_allowed(uid: int) -> bool:
    allowed = load_json(ALLOWED_FILE)
    return uid in allowed


def add_allowed(uid: int):
    allowed = load_json(ALLOWED_FILE)
    if uid not in allowed:
        allowed.append(uid)
        save_json(ALLOWED_FILE, allowed)


def remove_allowed(uid: int):
    allowed = load_json(ALLOWED_FILE)
    if uid in allowed:
        allowed.remove(uid)
        save_json(ALLOWED_FILE, allowed)


def add_pending(uid: int):
    pending = load_json(PENDING_FILE)
    if uid not in pending:
        pending.append(uid)
        save_json(PENDING_FILE, pending)


def pop_pending(uid: int):
    pending = load_json(PENDING_FILE)
    if uid in pending:
        pending.remove(uid)
        save_json(PENDING_FILE, pending)


def save_history(record: Dict[str, Any]):
    history = load_json(HISTORY_FILE)
    history.insert(0, record)  # newest first
    save_json(HISTORY_FILE, history)


def generate_table_text(res: Dict[str, Any]) -> str:
    # builds ASCII table similar to user's sample
    # res should contain: d1_text, d2_text, used_work, used_cal, prog, old_months, new_months, deduction_months,
    # old_days, new_days, old_value, new_value, old_after, new_after, total, compensation
    lines = []
    lines.append("┌" + "─" * 18 + "┬" + "─" * 12 + "┐")
    def row(k, v):
        return f"│ {k:<16}│ {str(v):>10} │"
    lines.append(row("Дата приёма", res["d1_text"]))
    lines.append(row("Дата увольнения", res["d2_text"]))
    lines.append(row("Исп. рабочих", f"{res['used_work']}"))
    lines.append(row("Исп. календарных", f"{res['used_cal']}"))
    lines.append(row("Прогул", f"{res['prog']}"))
    lines.append("├" + "─" * 18 + "┼" + "─" * 12 + "┤")
    lines.append(row("Старые месяцы", res["old_months"]))
    lines.append(row("Новые месяцы", res["new_months"]))
    lines.append(row("Вычет месяцев", res["deduction_months"]))
    lines.append(row("После вычета", res["after_deduction"]))
    lines.append(row("Старые дни ×1.25", f"{res['old_value']:.2f} - {res['used_work']} = {res['old_after']:.2f}"))
    lines.append(row("Новые дни ×1.75", f"{res['new_value']:.2f} - {res['used_cal']} = {res['new_after']:.2f}"))
    lines.append(row("Итого", f"{res['total']:.2f}"))
    lines.append(row("Компенсация", f"{res['compensation']}"))
    lines.append("└" + "─" * 18 + "┴" + "─" * 12 + "┘")
    return "\n".join(lines)


def months_between(d1: datetime, d2: datetime) -> int:
    # inclusive-ish - approximate to match examples: add 1 if day2 >= day1
    months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    if d2.day >= d1.day:
        months += 1
    return max(0, months)


def make_excel(history: List[Dict[str, Any]], out_path="history.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "History"
    headers = [
        "timestamp", "user_id", "d1", "d2", "used_work", "used_cal", "prog",
        "old_months", "new_months", "deduction_months", "total", "compensation"
    ]
    ws.append(headers)
    for rec in reversed(history):  # older first
        ws.append([
            rec.get("ts"),
            rec.get("user_id"),
            rec.get("d1_text"),
            rec.get("d2_text"),
            rec.get("used_work"),
            rec.get("used_cal"),
            rec.get("prog"),
            rec.get("old_months"),
            rec.get("new_months"),
            rec.get("deduction_months"),
            rec.get("total"),
            rec.get("compensation"),
        ])
    wb.save(out_path)
    return out_path


# ---------- Keyboards ----------
def main_menu_keyboard(admin: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Новый расчёт", callback_data="new_calc")],
        [InlineKeyboardButton(text="📚 История", callback_data="history")],
        [InlineKeyboardButton(text="🧾 Язык (RU/UZ)", callback_data="lang")],
    ])
    if admin:
        kb.inline_keyboard.append([InlineKeyboardButton(text="🛠 Админ", callback_data="admin_panel")])
    return kb


def admin_panel_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Export Excel", callback_data="admin_export")],
        [InlineKeyboardButton(text="📋 Show history", callback_data="admin_show")],
        [InlineKeyboardButton(text="🧹 Clear history", callback_data="admin_clear")],
        [InlineKeyboardButton(text="✅ Approve pending", callback_data="admin_pending")],
    ])
    return kb


# ---------- Handlers ----------
@dp.message(Command(commands=["start"]))
async def cmd_start(message: Message):
    uid = message.from_user.id
    if not is_allowed(uid):
        # not allowed -> prompt to request access
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Запросить доступ", callback_data="request_access")],
        ])
        await message.answer("Доступ закрыт. Нажмите кнопку, чтобы отправить запрос админу.", reply_markup=kb)
        return

    # allowed - show menu
    kb = main_menu_keyboard(admin=is_admin(uid))
    await message.answer("Выберите действие:", reply_markup=kb)


@dp.callback_query(lambda c: c.data == "request_access")
async def cb_request_access(cq: CallbackQuery):
    uid = cq.from_user.id
    add_pending(uid)
    # notify admin
    await cq.answer("Запрос отправлен админу.")
    text = f"Новый запрос доступа от {cq.from_user.full_name} (id={uid}).\n" \
           f"Команды админа: /approve {uid}  или нажать Админ -> Approve pending"
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        pass


@dp.message(Command(commands=["approve"]))
async def cmd_approve(message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("Только админ может выполнять эту команду.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: /approve <user_id>")
        return
    try:
        uid = int(args[1])
    except:
        await message.reply("Неверный id.")
        return
    add_allowed(uid)
    pop_pending(uid)
    await message.reply(f"Пользователь {uid} добавлен в список разрешённых.")
    try:
        await bot.send_message(uid, "Вам предоставлен доступ к HRminiBot. Используйте /start.")
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "new_calc")
async def cb_new_calc(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_allowed(uid):
        await cq.answer("Доступ запрещён.")
        return
    USER_STATE[uid] = "wait_d1"
    USER_DATA[uid] = {}
    await cq.message.answer("Введите дату приёма (ДД.MM.YYYY):")
    await cq.answer()


@dp.message()
async def generic_message(message: Message):
    uid = message.from_user.id
    text = message.text.strip()

    # if not allowed: show short reply w/ request button
    if not is_allowed(uid):
        await message.answer("Доступ закрыт. Чтобы запросить доступ, отправьте /start и нажмите кнопку 'Запросить доступ'.")
        return

    state = USER_STATE.get(uid, "idle")

    # handle sequence
    if state == "wait_d1":
        # validate date
        try:
            d1 = datetime.strptime(text, "%d.%m.%Y")
        except Exception:
            await message.reply("Неверный формат. Введите дату приёма в формате ДД.MM.YYYY (например 01.06.2020).")
            return
        USER_DATA[uid]["d1"] = d1
        USER_DATA[uid]["d1_text"] = text
        USER_STATE[uid] = "wait_d2"
        await message.reply("Введите дату увольнения (ДД.MM.YYYY):")
        return

    if state == "wait_d2":
        try:
            d2 = datetime.strptime(text, "%d.%m.%Y")
        except Exception:
            await message.reply("Неверный формат. Введите дату увольнения в формате ДД.MM.YYYY.")
            return
        if d2 < USER_DATA[uid]["d1"]:
            await message.reply("Дата увольнения раньше даты приёма — исправьте.")
            return
        USER_DATA[uid]["d2"] = d2
        USER_DATA[uid]["d2_text"] = text
        USER_STATE[uid] = "wait_used_work"
        await message.reply("Использовано рабочих дней (число):")
        return

    if state == "wait_used_work":
        try:
            used_work = float(text)
            if used_work < 0:
                raise ValueError
        except:
            await message.reply("Ошибка. Введите число (например 0 или 12):")
            return
        USER_DATA[uid]["used_work"] = used_work
        USER_STATE[uid] = "wait_used_cal"
        await message.reply("Использовано календарных дней (число):")
        return

    if state == "wait_used_cal":
        try:
            used_cal = float(text)
            if used_cal < 0:
                raise ValueError
        except:
            await message.reply("Ошибка. Введите число (например 0 или 14):")
            return
        USER_DATA[uid]["used_cal"] = used_cal
        USER_STATE[uid] = "wait_prog"
        await message.reply("Прогул (в днях, целое число):")
        return

    if state == "wait_prog":
        try:
            prog = int(float(text))
            if prog < 0:
                raise ValueError
        except:
            await message.reply("Ошибка. Введите целое число дней прогула (например 0 или 55):")
            return
        USER_DATA[uid]["prog"] = prog

        # all collected -> compute
        d1: datetime = USER_DATA[uid]["d1"]
        d2: datetime = USER_DATA[uid]["d2"]
        used_work = USER_DATA[uid]["used_work"]
        used_cal = USER_DATA[uid]["used_cal"]

        months = months_between(d1, d2)

        old_months = min(months, OLD_MONTHS_LIMIT)
        new_months = max(0, months - old_months)
        deduction_months = min(DEDUCTION_MONTHS, new_months)
        after_deduction = new_months - deduction_months

        old_days = old_months
        new_days = after_deduction

        old_value = old_days * COEF_OLD
        new_value = new_days * COEF_NEW

        old_after = max(0.0, old_value - used_work)
        new_after = max(0.0, new_value - used_cal)

        total = old_after + new_after
        compensation = math.ceil(total)

        result = {
            "ts": datetime.utcnow().isoformat(),
            "user_id": uid,
            "d1_text": USER_DATA[uid]["d1_text"],
            "d2_text": USER_DATA[uid]["d2_text"],
            "used_work": used_work,
            "used_cal": used_cal,
            "prog": prog,
            "months": months,
            "old_months": old_months,
            "new_months": new_months,
            "deduction_months": deduction_months,
            "after_deduction": after_deduction,
            "old_days": old_days,
            "new_days": new_days,
            "old_value": old_value,
            "new_value": new_value,
            "old_after": old_after,
            "new_after": new_after,
            "total": total,
            "compensation": compensation,
        }

        # save history
        save_history(result)

        # send table
        table_text = generate_table_text({
            "d1_text": result["d1_text"],
            "d2_text": result["d2_text"],
            "used_work": result["used_work"],
            "used_cal": result["used_cal"],
            "prog": result["prog"],
            "old_months": result["old_months"],
            "new_months": result["new_months"],
            "deduction_months": result["deduction_months"],
            "after_deduction": result["after_deduction"],
            "old_value": result["old_value"],
            "new_value": result["new_value"],
            "old_after": result["old_after"],
            "new_after": result["new_after"],
            "total": result["total"],
            "compensation": result["compensation"],
        })
        await message.reply("└─ Расчёт готов! ─\n" + "```\n" + table_text + "\n```", parse_mode="Markdown")

        # reset state
        USER_STATE[uid] = "idle"
        USER_DATA.pop(uid, None)
        return

    # If none of above -> default message with keyboard
    kb = main_menu_keyboard(admin=is_admin(uid))
    await message.reply("Выберите действие:", reply_markup=kb)


# ---------- Callback handlers for other keyboard buttons ----------
@dp.callback_query(lambda c: c.data == "history")
async def cb_history(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_allowed(uid):
        await cq.answer("Доступ запрещён.")
        return
    history = load_json(HISTORY_FILE)
    if not history:
        await cq.message.answer("История пуста.")
        await cq.answer()
        return
    # show last 5 entries
    out = []
    for i, rec in enumerate(history[:10], start=1):
        out.append(f"{i}) {rec['d1_text']} → {rec['d2_text']} | {rec['months']} мес | Компенсация: {rec['compensation']}")
    await cq.message.answer("Последние записи:\n" + "\n".join(out))
    await cq.answer()


@dp.callback_query(lambda c: c.data == "lang")
async def cb_lang(cq: CallbackQuery):
    # placeholder: toggles RU/UZ later
    await cq.answer("Локализация пока не меняется (RU/UZ placeholder).")


@dp.callback_query(lambda c: c.data == "admin_panel")
async def cb_admin_panel(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_admin(uid):
        await cq.answer("Только админ.")
        return
    kb = admin_panel_kb()
    await cq.message.answer("Admin panel:", reply_markup=kb)
    await cq.answer()


@dp.callback_query(lambda c: c.data == "admin_export")
async def cb_admin_export(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_admin(uid):
        await cq.answer("Только админ.")
        return
    history = load_json(HISTORY_FILE)
    if not history:
        await cq.answer("История пуста.")
        return
    path = make_excel(history, out_path="history.xlsx")
    await cq.answer("Формирую Excel...")
    try:
        await bot.send_document(uid, path)
    except Exception as e:
        await cq.message.answer(f"Ошибка отправки файла: {e}")
    await cq.answer()


@dp.callback_query(lambda c: c.data == "admin_show")
async def cb_admin_show(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_admin(uid):
        await cq.answer("Только админ.")
        return
    history = load_json(HISTORY_FILE)
    if not history:
        await cq.message.answer("История пуста.")
        await cq.answer()
        return
    out = []
    for i, rec in enumerate(history[:50], start=1):
        out.append(f"{i}) {rec['d1_text']}→{rec['d2_text']} | comp={rec['compensation']}")
    await cq.message.answer("История:\n" + "\n".join(out))
    await cq.answer()


@dp.callback_query(lambda c: c.data == "admin_clear")
async def cb_admin_clear(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_admin(uid):
        await cq.answer("Только админ.")
        return
    save_json(HISTORY_FILE, [])
    await cq.answer("История очищена.")
    await cq.message.answer("История успешно очищена.")


@dp.callback_query(lambda c: c.data == "admin_pending")
async def cb_admin_pending(cq: CallbackQuery):
    uid = cq.from_user.id
    if not is_admin(uid):
        await cq.answer("Только админ.")
        return
    pending = load_json(PENDING_FILE)
    if not pending:
        await cq.answer("Нет ожидающих запросов.")
        return
    text = "Pending requests:\n" + "\n".join(str(x) for x in pending)
    await cq.answer()
    await cq.message.answer(text + "\nИспользуй /approve <user_id> чтобы подтвердить.")


# ---------- Simple commands ----------
@dp.message(Command(commands=["status"]))
async def cmd_status(message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("Только админ.")
        return
    history = load_json(HISTORY_FILE)
    pending = load_json(PENDING_FILE)
    allowed = load_json(ALLOWED_FILE)
    await message.reply(f"Status:\nHistory entries: {len(history)}\nPending: {len(pending)}\nAllowed: {len(allowed)}")


@dp.message(Command(commands=["request_access"]))
async def cmd_request_access(message: Message):
    add_pending(message.from_user.id)
    await message.reply("Запрос отправлен админу.")
    try:
        await bot.send_message(ADMIN_ID, f"Request access from {message.from_user.full_name} id={message.from_user.id}")
    except:
        pass


# ---------- Run ----------
async def main():
    print("BOT STARTED")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
