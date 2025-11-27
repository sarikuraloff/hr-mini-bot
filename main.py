import asyncio
import json
import os
import math
from datetime import datetime, date

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

# Если хочешь экспорт в excel:
from openpyxl import Workbook

# ========== CONFIG ==========
BOT_TOKEN = "8579881937:AAGX0oiDtE-uTx2zRdkWjsrD4N46oexG80E"
ADMIN_ID = 880339036           # <-- твой id, админ
HISTORY_FILE = "history.json"
USERS_FILE = "allowed_users.json"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ========== HELPERS: load/save json ==========
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========== STORAGE ==========
allowed_users = load_json(USERS_FILE, [])
history = load_json(HISTORY_FILE, [])

# Если админ не в allowed_users — добавим автоматически (чтоб он не блокировался)
if ADMIN_ID not in allowed_users:
    allowed_users.append(ADMIN_ID)
    save_json(USERS_FILE, allowed_users)

# ========== CALC FUNCTIONS ==========
def months_between_precise(start_date: date, end_date: date) -> int:
    """Примерная оценка количества месяцев между датами (целые месяцы)."""
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    # корректировка по дням
    if end_date.day >= start_date.day:
        pass
    else:
        months -= 1
    return max(0, months)

def progul_deduction_days(prog):
    """Сколько месяцев вычесть за прогул (в днях). 30 дней = 1 месяц"""
    try:
        p = int(prog)
    except:
        p = 0
    return p // 30

def calculate(d1_str, d2_str, used_work, used_cal, prog):
    """
    Возвращает dict с расчетами.
    d1_str, d2_str в формате 'DD.MM.YYYY'
    used_work, used_cal — числа
    prog — целое
    """
    d1 = datetime.strptime(d1_str, "%d.%m.%Y").date()
    d2 = datetime.strptime(d2_str, "%d.%m.%Y").date()

    # Разделитель старые/новые месяцы — пример (в коде раньше был pivot 2023-04-30)
    pivot = date(2023, 4, 30)

    if d2 < pivot:
        months_old = months_between_precise(d1, d2)
        months_new = 0
    elif d1 > pivot:
        months_old = 0
        months_new = months_between_precise(d1, d2)
    else:
        months_old = months_between_precise(d1, pivot)
        months_new = months_between_precise(pivot, d2)

    prog_m = progul_deduction_days(prog)
    months_new_net = max(0, months_new - prog_m)

    base_old = months_old * 1.25
    base_new = months_new_net * 1.75

    netto_old = max(0, base_old - float(used_work))
    netto_new = max(0, base_new - float(used_cal))

    total = netto_old + netto_new
    final = math.ceil(total)

    return {
        "months_old": months_old,
        "months_new": months_new,
        "prog_m": prog_m,
        "months_new_net": months_new_net,
        "base_old": base_old,
        "base_new": base_new,
        "netto_old": netto_old,
        "netto_new": netto_new,
        "total": total,
        "final": final
    }

# ========== KEYBOARDS ==========
def main_menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔥 Новый расчёт"))
    kb.add(KeyboardButton("📚 История"))
    kb.row(KeyboardButton("🌍 Язык"), KeyboardButton("🛠 Админ"))
    kb.add(KeyboardButton("❌ Закрыть"))
    return kb

def admin_menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("➕ Добавить пользователя"))
    kb.add(KeyboardButton("📤 Export Excel"))
    kb.add(KeyboardButton("🧹 Очистить историю"))
    kb.add(KeyboardButton("⬅ Назад"))
    return kb

# ========== STATE ==========
user_state = {}   # uid -> "wait_d1" / "wait_d2" / ...
user_data = {}    # uid -> temp data dict

# ========== HANDLERS ==========

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    # Если пользователь не в allowed_users — предложим запросить доступ
    if uid not in allowed_users:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔓 Запросить доступ", callback_data="req_access")]
        ])
        await msg.answer("У вас пока нет доступа к боту. Отправить запрос админу?", reply_markup=kb)
        return

    await msg.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu_kb())

# ---- callback запрос доступа ----
@dp.callback_query(lambda c: c.data == "req_access")
async def cb_req_access(cb: CallbackQuery):
    requester = cb.from_user
    await bot.send_message(ADMIN_ID,
                           f"📩 Запрос доступа: {requester.full_name} (ID {requester.id}).\nРазрешить?",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                               [InlineKeyboardButton("✔ Разрешить", callback_data=f"allow_{requester.id}")],
                               [InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_{requester.id}")]
                           ]))
    await cb.message.answer("Запрос отправлен админу.")
    await cb.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("allow_"))
async def cb_allow(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Только админ может подтверждать.", show_alert=True)
        return
    uid = int(cb.data.split("_", 1)[1])
    if uid not in allowed_users:
        allowed_users.append(uid)
        save_json(USERS_FILE, allowed_users)
    await cb.message.answer(f"Пользователь {uid} разрешён.")
    await bot.send_message(uid, "🎉 Вам выдан доступ к боту (по решению админа).")
    await cb.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("deny_"))
async def cb_deny(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Только админ может отклонять.", show_alert=True)
        return
    uid = int(cb.data.split("_", 1)[1])
    await cb.message.answer(f"Пользователь {uid} — отклонён.")
    await bot.send_message(uid, "⛔ Админ отклонил ваш запрос доступа.")
    await cb.answer()

# ========== TEXT MESSAGE ROUTING ==========
@dp.message()
async def on_message(msg: Message):
    uid = msg.from_user.id
    text = (msg.text or "").strip()

    # Если нет доступа — только запрос доступа разрешаем
    if uid not in allowed_users:
        if text.lower() == "/start":
            await msg.answer("У вас нет доступа. Нажмите кнопку запроса доступа в /start.")
        else:
            await msg.answer("⛔ У вас нет доступа. Отправьте /start и запросите доступ.")
        return

    # Админ меню
    if text == "🛠 Админ":
        if uid != ADMIN_ID:
            await msg.answer("⛔ Только админ может открыть админ-панель.")
            return
        await msg.answer("Админ панель:", reply_markup=admin_menu_kb())
        return

    # Добавление пользователя вручную (админ)
    if text == "➕ Добавить пользователя" and uid == ADMIN_ID:
        user_state[uid] = "add_user"
        await msg.answer("Введи Telegram ID пользователя для добавления:")
        return

    if user_state.get(uid) == "add_user" and uid == ADMIN_ID:
        try:
            target = int(text)
            if target not in allowed_users:
                allowed_users.append(target)
                save_json(USERS_FILE, allowed_users)
                await msg.answer(f"Пользователь {target} добавлен в allowed_users.")
                await bot.send_message(target, "Админ выдал вам доступ к HRminiBot.")
            else:
                await msg.answer("Этот пользователь уже в списке.")
        except:
            await msg.answer("Ошибка: введите корректный числовой ID.")
        user_state.pop(uid, None)
        return

    # Export excel (админ)
    if text == "📤 Export Excel" and uid == ADMIN_ID:
        if not history:
            await msg.answer("Нет данных для экспорта.")
            return
        wb = Workbook()
        ws = wb.active
        ws.append(["Дата приёма", "Дата увольнения", "Исп. рабочих", "Исп. календарных", "Прогул", "Компенсация"])
        for item in history:
            ws.append([item.get("d1"), item.get("d2"), item.get("used_work"), item.get("used_cal"), item.get("prog"), item.get("result_final")])
        fname = "export.xlsx"
        wb.save(fname)
        await msg.answer_document(open(fname, "rb"))
        return

    # Очистить историю (админ)
    if text == "🧹 Очистить историю" and uid == ADMIN_ID:
        history.clear()
        save_json(HISTORY_FILE, history)
        await msg.answer("История очищена.")
        return

    # Назад
    if text == "⬅ Назад":
        await msg.answer("Вернулся в главное меню.", reply_markup=main_menu_kb())
        return

    # Новый расчёт (запуск ввода)
    if text == "🔥 Новый расчёт":
        user_state[uid] = "wait_d1"
        user_data[uid] = {}
        await msg.answer("Введите дату приёма (ДД.MM.ГГГГ):")
        return

    # Переключаем состояние по ожиданиям (пошаговый ввод)
    state = user_state.get(uid)
    if state == "wait_d1":
        # проверка формата
        try:
            datetime.strptime(text, "%d.%m.%Y")
            user_data[uid]["d1"] = text
            user_state[uid] = "wait_d2"
            await msg.answer("Введите дату увольнения (ДД.MM.ГГГГ):")
        except:
            await msg.answer("Неверный формат. Введите в виде ДД.MM.ГГГГ (например 01.06.2020).")
        return

    if state == "wait_d2":
        try:
            datetime.strptime(text, "%d.%m.%Y")
            user_data[uid]["d2"] = text
            user_state[uid] = "wait_used_work"
            await msg.answer("Использовано рабочих дней (число):")
        except:
            await msg.answer("Неверный формат даты. Введите в виде ДД.MM.ГГГГ.")
        return

    if state == "wait_used_work":
        try:
            user_data[uid]["used_work"] = float(text)
            user_state[uid] = "wait_used_cal"
            await msg.answer("Использовано календарных дней (число):")
        except:
            await msg.answer("Введите число (например 15 или 0).")
        return

    if state == "wait_used_cal":
        try:
            user_data[uid]["used_cal"] = float(text)
            user_state[uid] = "wait_prog"
            await msg.answer("Прогул (в днях):")
        except:
            await msg.answer("Введите число (например 0).")
        return

    if state == "wait_prog":
        try:
            user_data[uid]["prog"] = int(text)
        except:
            user_data[uid]["prog"] = 0

        # Выполним расчёт
        d = user_data[uid]
        try:
            res = calculate(d["d1"], d["d2"], d["used_work"], d["used_cal"], d["prog"])
        except Exception as e:
            await msg.answer("Ошибка при вычислении. Проверьте даты и значения.")
            user_state.pop(uid, None)
            user_data.pop(uid, None)
            return

        # Соберём ASCII-таблицу в нужном виде
        table = (
            "┌──────────────────┬────────────┐\n"
            f"│ Дата приёма      │ {d['d1']:<10} │\n"
            f"│ Дата увольнения  │ {d['d2']:<10} │\n"
            f"│ Исп. рабочих     │ {d['used_work']:<10} │\n"
            f"│ Исп. календарных │ {d['used_cal']:<10} │\n"
            f"│ Прогул           │ {d['prog']:<10} │\n"
            "├──────────────────┼────────────┤\n"
            f"│ Старые месяцы    │ {res['months_old']:<10} │\n"
            f"│ Новые месяцы     │ {res['months_new']:<10} │\n"
            f"│ Вычет месяцев    │ {res['prog_m']:<10} │\n"
            f"│ После вычета     │ {res['months_new_net']:<10} │\n"
            f"│ Старые дни ×1.25 │ {res['base_old']:.2f} - {d['used_work']} = {res['netto_old']:.2f} │\n"
            f"│ Новые дни ×1.75  │ {res['base_new']:.2f} - {d['used_cal']} = {res['netto_new']:.2f} │\n"
            "├──────────────────┼────────────┤\n"
            f"│ Итого            │ {res['total']:.2f}     │\n"
            f"│ Компенсация      │ {res['final']:<10} │\n"
            "└──────────────────┴────────────┘"
        )

        await msg.answer("📊 Расчёт готов:\n" + "```\n" + table + "\n```", parse_mode="Markdown")

        # Сохраняем в историю
        history.append({
            "d1": d["d1"],
            "d2": d["d2"],
            "used_work": d["used_work"],
            "used_cal": d["used_cal"],
            "prog": d["prog"],
            "result_final": res["final"]
        })
        save_json(HISTORY_FILE, history)

        # Очистка состояния
        user_state.pop(uid, None)
        user_data.pop(uid, None)
        return

    # История
    if text == "📚 История":
        if not history:
            await msg.answer("История пуста.")
            return
        lines = ["📘 Последние записи:"]
        for rec in history[-10:]:
            lines.append(f"{rec['d1']} → {rec['d2']} | {rec['result_final']}")
        await msg.answer("\n".join(lines))
        return

    if text == "❌ Закрыть":
        await msg.answer("Меню закрыто.")
        return

    # Язык (пусто — можно расширить)
    if text == "🌍 Язык":
        await msg.answer("Язык: Русский (по умолчанию).")
        return

    # Если ничего подходящего:
    await msg.answer("Не понял команду. Выберите из меню:", reply_markup=main_menu_kb())

# ========== RUN BOT ==========
async def main():
    print("HRminiBot STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
