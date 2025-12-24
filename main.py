import asyncio
import json
import os
import math
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from openpyxl import Workbook
import calendar

# ============== CONFIG ==============
BOT_TOKEN = "8579881937:AAGX0oiDtE-uTx2zRdkWjsrD4N46oexG80E"  # замените на ваш токен
ADMIN_IDS = [880339036]  # только ты как админ

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

HISTORY_FILE = "history.json"
EMPLOYEES_FILE = "employees.json"
ALLOWED_USERS_FILE = "allowed_users.json"
CONTACTS_FILE = "contacts.json"

# in-memory state
USER_STATE: Dict[int, Optional[str]] = {}
USER_DATA: Dict[int, Dict[str, Any]] = {}
user_lang: Dict[int, str] = {}

# ============== Localization ==========
LANG = {
    "ru": {
        "hello": "Ассалому алайкум! 👋 Выберите действие:",
        "new_calc": "🔥 Новый расчёт",
        "history": "📚 История",
        "language": "🌐 Язык",
        "admin": "🛠 Админ",
        "close": "❌ Закрыть",

        "enter_d1": "Введите дату приёма (ДД.MM.YYYY)",
        "enter_d2": "Введите дату увольнения (ДД.MM.YYYY)",
        "enter_used_work": "Сколько использовано рабочих дней? (число)",
        "enter_used_cal": "Сколько использовано календарных дней? (число)",
        "enter_prog": "Введите прогул (в днях):",

        "calc_done": "📊 Расчёт готов!",
        "no_history": "История пуста.",
        "history_title": "📚 Последние записи:",

        "confirm_clear": "Вы уверены, что хотите удалить историю?",
        "yes": "Да",
        "no": "Нет",

        "lang_ru": "🇷🇺 Русский",
        "lang_uz": "🇺🇿 O‘zbekcha",
        "choose_lang": "Выберите язык:",

        "emp_list": "Список сотрудников:",
        "emp_added": "Сотрудник добавлен.",
        "emp_deleted": "Сотрудник удалён.",
        "emp_choose": "Сотрудников нет. Админ может добавить через админ-панель.",
        "order_created": "✅ Приказ (PDF) создан и отправлен.",
        "not_admin": "У вас нет доступа к админ-панели."
    },
    "uz": {
        "hello": "Assalomu alaykum! 👋 Amalni tanlang:",
        "new_calc": "🔥 Yangi hisoblash",
        "history": "📚 Tarix",
        "language": "🌐 Til",
        "admin": "🛠 Admin",
        "close": "❌ Yopish",

        "enter_d1": "Ishga kirgan sana (DD.MM.YYYY)",
        "enter_d2": "Ishdan bo'shagan sanasi",
        "enter_used_work": "Foydalanilgan mehnat tatili (Eski):",
        "enter_used_cal": "Foydalanilgan mehnat tatili (Yangi):",
        "enter_prog": "Progul (kun):",

        "calc_done": "📊 Hisob tayyor!",
        "no_history": "Tarix bo'sh.",
        "history_title": "📚 So'nggi yozuvlar:",

        "confirm_clear": "Tarixni o'chirmoqchimisiz?",
        "yes": "Ha",
        "no": "Yo'q",

        "lang_ru": "🇷🇺 Ruscha",
        "lang_uz": "🇺🇿 O'zbekcha",
        "choose_lang": "Tilni tanlang:",

        "emp_list": "Xodimlar ro'yxati:",
        "emp_added": "Xodim qo‘shildi.",
        "emp_deleted": "Xodim o‘chirildi.",
        "emp_choose": "Xodimlar mavjud emas. Admin qo'shishi mumkin.",
        "order_created": "✅ Buyruq (PDF) yaratildi va yuborildi.",
        "not_admin": "Siz admin emassiz."
    }
}

def L(uid: int, key: str) -> str:
    lang = user_lang.get(uid, "ru")
    return LANG.get(lang, LANG["ru"]).get(key, key)

# ============== Utilities ==============
def safe_float(v):
    try:
        return float(v)
    except:
        return 0.0

def safe_int(v):
    try:
        return int(v)
    except:
        return 0

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_history():
    return load_json(HISTORY_FILE, [])

def save_history_item(item: dict):
    h = load_history()
    h.insert(0, item)
    save_json(HISTORY_FILE, h[:200])

def load_employees():
    return load_json(EMPLOYEES_FILE, [])

def save_employees(elist):
    save_json(EMPLOYEES_FILE, elist)
    
def load_contacts():
    return load_json(CONTACTS_FILE, {})

def save_contacts(data):
    save_json(CONTACTS_FILE, data)

# ============== Allowed users helpers ==============
def load_allowed_users():
    return load_json(ALLOWED_USERS_FILE, [])

def save_allowed_users(lst):
    save_json(ALLOWED_USERS_FILE, lst)

def is_allowed(uid: int) -> bool:
    allowed = load_allowed_users()
    return uid in allowed or uid in ADMIN_IDS

# ============== Date parsing & suggestions ==============
def parse_date_try(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    formats = ["%d.%m.%Y","%d-%m-%Y","%d/%m/%Y","%Y-%m-%d","%d.%m.%y"]
    for f in formats:
        try:
            dt = datetime.strptime(s, f).date()
            return dt.strftime("%d.%m.%Y")
        except:
            continue
    digits = ''.join(ch for ch in s if ch.isdigit())
    if len(digits) == 8:
        try:
            dt = datetime.strptime(digits, "%d%m%Y").date()
            return dt.strftime("%d.%m.%Y")
        except:
            pass
    return None

# ============== Calculation logic ==============
def months_between_precise(start_date: date, end_date: date) -> int:
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    day_diff = end_date.day - start_date.day
    if day_diff >= 15:
        months += 1
    elif day_diff < 0:
        months -= 1
        if (end_date.day + (30 + day_diff)) >= 15:
            months += 1
    return max(months, 0)

def progul_deduction_days(progul: int) -> int:
    try:
        p = int(progul)
    except:
        return 0
    if p < 15:
        return 0
    return ((p - 15) // 30) + 1

def round_half_up(value: float) -> int:
    frac = value - math.floor(value)
    return math.ceil(value) if frac >= 0.5 else math.floor(value)

def calculate_compensation(
    d1s, d2s,
    used_old=0, used_new=0,
    prog_old=0, prog_new=0,
    bs_old=0, bs_new=0
):
    pivot = date(2023, 4, 29)

    d1 = datetime.strptime(d1s, "%d.%m.%Y").date()
    d2 = datetime.strptime(d2s, "%d.%m.%Y").date()

    def calc_period(start, end, used, prog, bs, coef):
        if start > end:
            return {
                "days": 0,
                "deductions": 0,
                "eff_days": 0,
                "months": 0,
                "rest": 0,
                "rounded": 0,
                "result": 0.0
            }

        total_days = (end - start).days + 1
        deductions = int(prog) + int(bs)
        effective_days = total_days - deductions


        months = effective_days // 30
        rest = effective_days % 30
        rounded_months = months + (1 if rest >= 15 else 0)

        return {
            "days": total_days,
            "deductions": deductions,
            "eff_days": effective_days,
            "months": months,
            "rest": rest,
            "rounded": rounded_months,
            "result": rounded_months * coef
        }
    # 🟤 старый период
    old = calc_period(
        d1,
        min(d2, pivot),
        used_old, prog_old, bs_old,
        coef=1.25
    )

    # 🟢 новый период
    new = calc_period(
        max(d1, pivot + timedelta(days=1)),
        d2,
        used_new, prog_new, bs_new,
        coef=1.75
    )

    total = old["result"] + new["result"]
    total_after_used = max(0, total - used_old - used_new)

    return {
        "old": old,
        "new": new,
        "total": total,
        "final": round_half_up(total_after_used),
        "used_total": used_old + used_new
    }
# ============== PDF & Excel helpers ==============
def create_pdf_result(table_data: dict, filename="komp_result.pdf"):
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    y = 800
    c.drawString(50, y, "HRminiBot — Расчёт компенсации")
    c.setFont("Helvetica", 11)
    y -= 28
    for k, v in table_data.items():
        if k == "":
            y -= 8
            continue
        c.drawString(50, y, f"{k}: {v}")
        y -= 18
        if y < 80:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = 800
    c.save()
    return filename

def create_order_pdf(employee: dict, calc_info: dict, filename="order.pdf"):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, height-80, "ПРИКАЗ")
    c.setFont("Helvetica", 12)
    y = height - 130
    c.drawString(60, y, f"Работник: {employee.get('name','-')}")
    y -= 18
    c.drawString(60, y, f"Должность: {employee.get('position','-')}")
    y -= 18
    c.drawString(60, y, f"Период: {calc_info.get('d1','-')} — {calc_info.get('d2','-')}")
    y -= 28
    for k, v in calc_info.get("summary", {}).items():
        c.drawString(60, y, f"{k}: {v}")
        y -= 18
    y -= 20
    c.drawString(60, y, "Компенсация к выплате: " + str(calc_info.get("summary", {}).get("Компенсация", "-")))
    y -= 40
    c.drawString(60, y, "Дата: " + datetime.utcnow().strftime("%d.%m.%Y"))
    y -= 50
    c.drawString(60, y, "Подпись: ____________________")
    c.save()
    return filename

def export_history_excel(filename="history.xlsx"):
    h = load_history()
    
    # FIX старых записей
    for r in h:
        r.setdefault("prog_old", 0)
        r.setdefault("prog_new", 0)
        r.setdefault("bs_old", 0)
        r.setdefault("bs_new", 0)
        
    wb = Workbook()
    ws = wb.active
    ws.title = "History"
    
    ws.append(["Дата приёма", "Дата увольнения", "Исп. рабочих", "Исп. календ.", "Прогул старый", "Прогул новый", "БС старый", "БС новый", "Итого", "Компенсация", "ts"])
    for r in h:
        ws.append([
            r.get("d1",""),
            r.get("d2",""),
            r.get("used_work",0),
            r.get("used_cal",0),
            r.get("prog_old",0),
            r.get("prog_new",0),
            r.get("bs_old",0),
            r.get("bs_new",0),
            r.get("total",""),
            r.get("final",""),
            r.get("ts","")
        ])
    wb.save(filename)
    return filename
# ============== pretty table ==============
def make_table(data: dict) -> str:
    col1 = max(len(str(k)) for k in data.keys())
    col2 = max(len(str(v)) for v in data.values())
    top = "┌" + "─"*(col1+2) + "┬" + "─"*(col2+2) + "┐"
    mid = "├" + "─"*(col1+2) + "┼" + "─"*(col2+2) + "┤"
    bot = "└" + "─"*(col1+2) + "┴" + "─"*(col2+2) + "┘"
    rows = [top]
    for k, v in data.items():
        if k == "":
            rows.append(mid)
            continue
        rows.append(f"│ {str(k).ljust(col1)} │ {str(v).ljust(col2)} │")
    rows.append(bot)
    return "\n".join(rows)

# ============== Keyboards ==============
def main_menu(uid: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=L(uid, "new_calc"))],
            [KeyboardButton(text=L(uid, "history"))],
            [KeyboardButton(text=L(uid, "language")), KeyboardButton(text=L(uid, "admin"))],
            [KeyboardButton(text=L(uid, "close"))]
        ],
        resize_keyboard=True
    )
    return kb

# ============== Handlers ==============
@dp.message(F.contact)
async def handle_contact(msg: Message):
    uid = msg.from_user.id
    contact = msg.contact
    phone = contact.phone_number
    full_name = msg.from_user.full_name

    # сохраняем телефон в отдельный файл
    contacts = load_contacts()
    contacts[str(uid)] = {
        "phone": phone,
        "name": full_name
    }
    save_contacts(contacts)

    # если уже есть доступ — просто спасибо сказать
    if is_allowed(uid):
        await msg.answer("✅ Контакт сохранён. У вас уже есть доступ.", reply_markup=main_menu(uid))
        return

    # отправляем запрос всем админам с теми же кнопками grant/deny
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"grant:{uid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny:{uid}")]
    ])
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(
                admin,
                f"📨 Запрос доступа (по контакту)\n\n"
                f"Имя: {full_name}\n"
                f"Телефон: {phone}\n"
                f"ID: {uid}\n\nРазрешить доступ?",
                reply_markup=kb
            )
        except Exception as e:
            print("Notify admin(contact) error:", e)

    await msg.answer(
        "📲 Спасибо! Ваш номер отправлен администратору.\n"
        "Ожидайте, когда он разрешит доступ.",
        reply_markup=ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[[KeyboardButton(text="🔄 Проверить доступ (/start)")]]
        )
    )

@dp.message(Command(commands=["start"]))
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    user_lang.setdefault(uid, "ru")
    USER_STATE[uid] = None
    USER_DATA[uid] = {}

    # Если не разрешён — показываем подсказку, /access и кнопку отправки контакта
    if not is_allowed(uid):
        kb = ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="📱 Отправить контакт", request_contact=True)]
            ]
        )
        await msg.answer(
            "❌ У вас нет доступа к этому боту.\n\n"
            "1) Нажмите кнопку «📱 Отправить контакт» ниже,\n"
            "   чтобы админ увидел ваш номер и ID.\n"
            "ИЛИ\n"
            "2) Отправьте команду /access чтобы запросить доступ.",
            reply_markup=kb
        )
        return

    await msg.answer(L(uid, "hello"), reply_markup=main_menu(uid))

@dp.message(Command(commands=["access"]))
async def cmd_access(msg: Message):
    uid = msg.from_user.id
    username = msg.from_user.username or msg.from_user.full_name or str(uid)

    if is_allowed(uid):
        await msg.answer("✔ У вас уже есть доступ.")
        return

    # Отправляем уведомление всем администраторам
    for admin in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Разрешить доступ", callback_data=f"grant:{uid}")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny:{uid}")]
            ])
            await bot.send_message(
                admin,
                f"📨 Запрос доступа\n\nПользователь: @{username}\nID: {uid}\n\nРазрешить доступ?",
                reply_markup=kb
            )
        except Exception as e:
            # если не получилось отправить админу, продолжаем
            print("Notify admin error:", e)
    await msg.answer("Ваш запрос отправлен администратору. Ждите ответа.")

@dp.message()
async def main_handler(msg: Message):
    uid = msg.from_user.id
    text = (msg.text or "").strip()
    user_lang.setdefault(uid, "ru")

    # Блокируем всех НЕ разрешённых при любом сообщении (кроме /access handled above)
    if not is_allowed(uid):
        await msg.answer("❌ Вам запрещено пользоваться этим ботом. Отправьте /access чтобы запросить доступ.")
        return

    # MAIN MENU ACTIONS
    if text == L(uid, "new_calc"):
        USER_DATA[uid] = {}
        USER_STATE[uid] = "d1"
        await msg.answer(L(uid, "enter_d1"))
        return

    if text == L(uid, "history"):
        h = load_history()
        if not h:
            await msg.answer(L(uid, "no_history"))
            return
        out = [L(uid, "history_title")]
        for i, x in enumerate(h[:10], start=1):
            out.append(f"{i}) {x['d1']} → {x['d2']} | {x['final']} дней")
        await msg.answer("\n".join(out))
        return

    if text == L(uid, "language"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=L(uid, "lang_ru"), callback_data=f"lang:set:ru:{uid}")],
            [InlineKeyboardButton(text=L(uid, "lang_uz"), callback_data=f"lang:set:uz:{uid}")]
        ])
        await msg.answer(L(uid, "choose_lang"), reply_markup=kb)
        return

    if text == L(uid, "admin"):
        if uid not in ADMIN_IDS:
            await msg.answer(L(uid, "not_admin"))
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Show employees", callback_data=f"admin:emps:{uid}")],
            [InlineKeyboardButton(text="➕ Add employee", callback_data=f"admin:addemp:{uid}")],
            [InlineKeyboardButton(text="🧹 Clear employees", callback_data=f"admin:clearemps:{uid}")],
            [InlineKeyboardButton(text="🗑 Clear history", callback_data=f"admin:clearhist:{uid}")],
            [InlineKeyboardButton(text="📤 Export Excel", callback_data=f"admin:export:{uid}")],
            [InlineKeyboardButton(text="👥 Show allowed users", callback_data=f"admin:showallowed:{uid}")],
            [InlineKeyboardButton(text="❌ Remove user", callback_data=f"admin:removeallowed:{uid}")]
        ])

        await msg.answer("Admin panel:", reply_markup=kb)
        return

    if text == L(uid, "close"):
        USER_STATE[uid] = None
        await msg.answer("Меню закрыто.", reply_markup=main_menu(uid))
        return

    # ADMIN ADD EMPLOYEE FLOW (only admin)
    if USER_STATE.get(uid) == "admin_add_employee":
        # received name
        name = text
        USER_DATA[uid] = {"emp_name": name}
        USER_STATE[uid] = "admin_add_employee_position"
        await msg.answer("Введите должность сотрудника (или отправьте пустое сообщение):")
        return

    if USER_STATE.get(uid) == "admin_add_employee_position":
        pos = text
        emp = {"name": USER_DATA[uid].get("emp_name", ""), "position": pos}
        emps = load_employees()
        emps.append(emp)
        save_employees(emps)
        USER_STATE[uid] = None
        USER_DATA[uid] = {}
        await msg.answer(L(uid, "emp_added"), reply_markup=main_menu(uid))
        return

    # ADMIN add/remove allowed user flows
    if USER_STATE.get(uid) == "admin_add_allowed":
        # admin typed ID to add
        try:
            new_id = int(text.strip())
            users = load_allowed_users()
            if new_id not in users:
                users.append(new_id)
                save_allowed_users(users)
                await msg.answer(f"ID {new_id} добавлен в разрешённые.", reply_markup=main_menu(uid))
            else:
                await msg.answer("Этот ID уже в списке.")
        except:
            await msg.answer("Введите корректный числовой ID.")
        USER_STATE[uid] = None
        return

    if USER_STATE.get(uid) == "admin_del_allowed":
        try:
            del_id = int(text.strip())
            users = load_allowed_users()
            if del_id in users:
                users.remove(del_id)
                save_allowed_users(users)
                await msg.answer(f"ID {del_id} удалён из разрешённых.", reply_markup=main_menu(uid))
            else:
                await msg.answer("ID не найден.")
        except:
            await msg.answer("Введите корректный числовой ID.")
        USER_STATE[uid] = None
        return

    # CALC FLOW
    state = USER_STATE.get(uid)
    if state == "d1":
        parsed = parse_date_try(text)
        if not parsed:
            await msg.answer("Неверный формат даты. Попробуйте ДД.MM.YYYY или используйте календарь.")
            return
        USER_DATA[uid]["d1"] = parsed
        USER_STATE[uid] = "d2"
        y = int(parsed.split(".")[2]); m = int(parsed.split(".")[1])
        await msg.answer(L(uid, "enter_d2"))
        return

    if state == "d2":
        parsed = parse_date_try(text)
        if not parsed:
            await msg.answer("Неверный формат даты. Попробуйте ДД.MM.YYYY или используйте календарь.")
            return
        USER_DATA[uid]["d2"] = parsed
        USER_STATE[uid] = "used_work"
        await msg.answer(L(uid, "enter_used_work"))
        return

    if state == "used_work":
        USER_DATA[uid]["used_work"] = safe_float(text)
        USER_STATE[uid] = "used_cal"
        await msg.answer(L(uid, "enter_used_cal"))
        return

    if state == "used_cal":
        USER_DATA[uid]["used_cal"] = safe_float(text)
        USER_STATE[uid] = "prog_old"
        await msg.answer("Введите прогул старого периода (до 29.04.2023):")
        return

    if state == "prog_old":
        USER_DATA[uid]["prog_old"] = safe_int(text)
        USER_STATE[uid] = "prog_new"
        await msg.answer("Введите прогул нового периода (после 30.04.2023):")
        return

    if state == "prog_new":
        USER_DATA[uid]["prog_new"] = safe_int(text)
        USER_STATE[uid] = "bs_old"
        await msg.answer("Введите БС старого периода (до 29.04.2023):")
        return

    if state == "bs_old":
        USER_DATA[uid]["bs_old"] = safe_int(text)
        USER_STATE[uid] = "bs_new"
        await msg.answer("Введите БС нового периода (после 30.04.2023):")
        return

    if state == "bs_new":
        USER_DATA[uid]["bs_new"] = safe_int(text)
        USER_STATE[uid] = None

        # --- CALCULATION HERE ---
        d = USER_DATA[uid]
        
        res = calculate_compensation( d["d1"], d["d2"], d["used_work"], d["used_cal"], d["prog_old"], d["prog_new"], d["bs_old"], d["bs_new"] )
        entry = {
            "d1": d["d1"], "d2": d["d2"], "used_work": d["used_work"],
            "used_cal": d["used_cal"],
            "prog_old": d["prog_old"], "prog_new": d["prog_new"],
            "bs_old": d["bs_old"], "bs_new": d["bs_new"],
            "total": res["total"], "final": res["final"],
            "ts": datetime.utcnow().isoformat()
        }
        save_history_item(entry)
        
        # Подробные формулы
        old = res["old"]
        new = res["new"]

        total_accrued = old["result"] + new["result"]
        used_total = d["used_work"] + d["used_cal"]
        total_after_used = max(0, total_accrued - used_total)


        lines = []

        lines.append("[ СТАРЫЙ ПЕРИОД ]")
        lines.append(f"Стаж (дни):        {old['days']}")
        lines.append(f"Вычеты (дни):      {old.get('deductions', 0)}")
        lines.append(f"Фактически:        {old['eff_days']}")
        lines.append(f"= {old['months']} мес {old['rest']} дн")
        lines.append(f"Начислено:         {old['rounded']} × 1.25 = {old['result']}")
        lines.append("")

        lines.append("[ НОВЫЙ ПЕРИОД ]")
        lines.append(f"Стаж (дни):        {new['days']}")
        lines.append(f"Вычеты (дни):      {new.get('deductions', 0)}")
        lines.append(f"Фактически:        {new['eff_days']}")
        lines.append(f"= {new['months']} мес {new['rest']} дн")
        lines.append(f"Начислено:         {new['rounded']} × 1.75 = {new['result']}")
        lines.append("")

        lines.append("[ ИТОГ ]")
        lines.append(f"Всего:             {total_accrued:.2f} - {used_total} = {total_after_used:.2f}")
        lines.append(f"Компенсация:       {round_half_up(total_after_used)}")

        await msg.answer("\n".join(lines))

        # if admin previously selected employee in session, create order
        emp = USER_DATA.get(uid, {}).get("employee")
        if emp:
            calc_info = {"d1": d["d1"], "d2": d["d2"], "summary": {"Итого дней": res["total"], "Компенсация": res["final"]}}
            order_file = create_order_pdf(emp, calc_info)
            await msg.answer("Приказ для сотрудника:")
            await msg.answer_document(open(order_file, "rb"))
        return

    # fallback
    await msg.answer(L(uid, "hello"), reply_markup=main_menu(uid))

# ============== Callback handler ==============
@dp.callback_query()
async def callback_handler(call: CallbackQuery):
    data = call.data or ""
    uid = call.from_user.id
    
    # === удаление конкретного пользователя ===
    if str(data).startswith("rm:"):
        target_id = int(str(data).split(":")[1])
        users = load_allowed_users()

        if target_id in users:
            users.remove(target_id)
            save_allowed_users(users)
            await call.message.answer(f"Пользователь {target_id} удалён! ✔")
        else:
            await call.message.answer("Этот пользователь уже удалён.")

        await call.answer()
        return


    if data == "noop":
        await call.answer()
        return

    # grant/deny handling (access requests)
    if data.startswith("grant:") or data.startswith("deny:"):
        # only admins can press these
        if uid not in ADMIN_IDS:
            await call.answer("Нет доступа", show_alert=True)
            return
        cmd, s_id = data.split(":")
        try:
            user_id = int(s_id)
        except:
            await call.answer("Неверный ID"); return

        if cmd == "grant":
            users = load_allowed_users()
            if user_id not in users:
                users.append(user_id)
                save_allowed_users(users)
            # notify user and edit admin message
            try:
                await bot.send_message(user_id, "🎉 Вам одобрен доступ к боту!")
            except:
                pass
            try:
                await call.message.edit_text(f"✔ Доступ пользователю {user_id} разрешён.")
            except:
                pass
            await call.answer()
            return
        else:  # deny
            try:
                await bot.send_message(user_id, "❌ Ваш запрос доступа отклонён.")
            except:
                pass
            try:
                await call.message.edit_text(f"❌ Доступ пользователю {user_id} отклонён.")
            except:
                pass
            await call.answer()
            return

    # language set: lang:set:ru:uid
    if data.startswith("lang:set:"):
        parts = data.split(":")
        if len(parts) >= 4:
            lang_code = parts[2]; owner = int(parts[3])
            user_lang[owner] = lang_code
            await call.message.answer("Язык переключён.")
            await call.answer(); return

    # clear from admin panel: clear:yes:uid or clear:no:uid
    if data.startswith("clear:"):
        _, ans, owner_s = data.split(":")
        owner = int(owner_s)
        if owner != uid and uid not in ADMIN_IDS:
            await call.answer("Нет доступа", show_alert=True); return
        if ans == "yes":
            save_json(HISTORY_FILE, [])
            await call.message.answer("История очищена.")
            await call.answer(); return
        else:
            await call.message.answer("Отмена.")
            await call.answer(); return

    # admin actions admin:export:uid, admin:emps:uid, admin:addemp:uid, admin:clearemps:uid
    if data.startswith("admin:"):
        parts = data.split(":")
        if len(parts) >= 3:
            action = parts[1]
            owner = int(parts[2])
            if uid not in ADMIN_IDS:
                await call.answer("Нет доступа", show_alert=True); return

            if action == "export":
                fname = export_history_excel()
                await call.message.answer_document(open(fname, "rb"))
                await call.answer(); return

            if action == "emps":
                emps = load_employees()
                if not emps:
                    await call.message.answer(L(uid, "emp_choose"))
                else:
                    out = [L(uid, "emp_list")]
                    for i,e in enumerate(emps,1):
                        out.append(f"{i}) {e.get('name')} — {e.get('position','')}")
                    await call.message.answer("\n".join(out))
                await call.answer(); return

            if action == "addemp":
                # start admin add flow
                USER_STATE[uid] = "admin_add_employee"
                await call.message.answer("Введите имя сотрудника:")
                await call.answer(); return

            if action == "clearemps":
                save_employees([])
                await call.message.answer("Employees cleared.")
                await call.answer(); return

            if action == "clearhist":
                save_json(HISTORY_FILE, [])
                await call.message.answer("History cleared.")
                await call.answer(); return

            if action == "showallowed":
                users = load_allowed_users()
                contacts = load_contacts()

                if not users:
                    await call.message.answer("Список разрешённых пользователей пуст.")
                else:
                    text = ["👥 Разрешённые пользователи:"]
                    for u in users:
                        info = contacts.get(str(u), {})
                        phone = info.get("phone", "—")
                        name = info.get("name", f"ID {u}")
                        text.append(f"🧑 {name} — 📞 {phone}")
                    await call.message.answer("\n".join(text))

                await call.answer()
                return

                
            if action == "removeallowed":
                users = load_allowed_users()
                contacts = load_contacts()
    
                if not users:
                    await call.message.answer("Список пуст 👀")
                else:
                    kb = InlineKeyboardMarkup(inline_keyboard=[])
                    for u in users:
                        info = contacts.get(str(u), {})
                        phone = info.get("phone", "Неизвестно")
                        name = info.get("name", f"ID {u}")

                        btn_text = f"❌ Удалить {name.replace('None', '')} ({phone})"
                        kb.inline_keyboard.append([
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"rm:{u}"
                            )   
                        ])

                    await call.message.answer("👇 Выберите кого удалить:", reply_markup=kb)
    
                await call.answer()
                return

    # ============== Admin quick commands ==============
@dp.message(Command(commands=["addemp"]))
async def cmd_addemp(msg: Message):
    uid = msg.from_user.id
    if uid not in ADMIN_IDS:
        await msg.answer(L(uid, "not_admin")); return
    text = (msg.text or "").replace("/addemp", "", 1).strip()
    if "|" in text:
        name, pos = [s.strip() for s in text.split("|",1)]
    else:
        name, pos = text, ""
    emps = load_employees()
    emps.append({"name": name, "position": pos})
    save_employees(emps)
    await msg.answer("Employee added.")

@dp.message(Command(commands=["delemp"]))
async def cmd_delemp(msg: Message):
    uid = msg.from_user.id
    if uid not in ADMIN_IDS:
        await msg.answer(L(uid, "not_admin")); return
    args = (msg.text or "").replace("/delemp","",1).strip()
    if not args.isdigit():
        await msg.answer("Usage: /delemp <number>"); return
    idx = int(args)-1
    emps = load_employees()
    if 0 <= idx < len(emps):
        removed = emps.pop(idx)
        save_employees(emps)
        await msg.answer(f"Removed {removed.get('name')}")
    else:
        await msg.answer("Index out of range.")

@dp.message(Command(commands=["adduser"]))
async def cmd_adduser(msg: Message):
    uid = msg.from_user.id
    if uid not in ADMIN_IDS:
        await msg.answer("Нет доступа"); return
    text = (msg.text or "").replace("/adduser","",1).strip()
    try:
        new_id = int(text)
        users = load_allowed_users()
        if new_id not in users:
            users.append(new_id)
            save_allowed_users(users)
            await msg.answer(f"ID {new_id} добавлен.")
        else:
            await msg.answer("Этот ID уже в списке.")
    except:
        await msg.answer("Использование: /adduser <id>")

@dp.message(Command(commands=["deluser"]))
async def cmd_deluser(msg: Message):
    uid = msg.from_user.id
    if uid not in ADMIN_IDS:
        await msg.answer("Нет доступа"); return
    text = (msg.text or "").replace("/deluser","",1).strip()
    try:
        del_id = int(text)
        users = load_allowed_users()
        if del_id in users:
            users.remove(del_id)
            save_allowed_users(users)
            await msg.answer(f"ID {del_id} удалён.")
        else:
            await msg.answer("ID не найден.")
    except:
        await msg.answer("Использование: /deluser <id>")

# ============== Start ==============
async def main():
    print("HRminiBot PRO STARTED")
    # ensure files exist
    if not os.path.exists(HISTORY_FILE):
        save_json(HISTORY_FILE, [])
    if not os.path.exists(EMPLOYEES_FILE):
        save_json(EMPLOYEES_FILE, [])
    if not os.path.exists(ALLOWED_USERS_FILE):
        save_json(ALLOWED_USERS_FILE, [])

    # ➕ Добавляем контактный файл
    if not os.path.exists(CONTACTS_FILE):
        save_json(CONTACTS_FILE, {})

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")
