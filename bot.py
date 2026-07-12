# -*- coding: utf-8 -*-
"""
Telegram Bot - Video Kurslar va Darsliklar Bot (Python versiyasi)
Kutubxona: aiogram v3.x (Asinxron va juda kuchli Telegram Bot kutubxonasi)

Ushbu bot to'liq Python tilida yozilgan va quyidagi imkoniyatlarga ega:
1. Bo'limlar (kategoriyalar) yaratish va o'chirish.
2. Bo'limlarga ketma-ket videolarni, rasmlarni, fayllarni yoki havolalarni yuborib, /tugadi buyrug'i orqali hammasini birdaniga saqlash.
3. Foydalanuvchi bo'limni tanlaganda undagi barcha darsliklarni birdaniga ketma-ket chiqarib berish.
4. Kanalga majburiy a'zolikni tekshirish tizimi.
5. VIP darsliklar va foydalanuvchilarga VIP statusini berish/o'chirish.
6. Jami foydalanuvchilarga, faqat VIP a'zolarga yoki faqat oddiy a'zolarga xabar (reklama) yuborish.
7. Foydalanuvchilar va Adminlar uchun alohida Statistika bo'limi (oddiy foydalanuvchilarga jami a'zolar soni ko'rinmaydi).
8. **Yangi imkoniyat:** Asosiy Owner (Ega) tomonidan yangi adminlar qo'shish va ularni o'chirish tizimi.

O'rnatilishi kerak bo'lgan kutubxonalar (pip orqali):
    pip install aiogram

Ishga tushirish:
    Python fayl ichidagi 'BOT_TOKEN' va 'ADMIN_ID' (Asosiy egasining Telegram ID-si) ni o'zgartiring va quyidagi buyruq orqali ishga tushiring:
    python bot.py
"""

import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- SOZLAMALAR ---
BOT_TOKEN = "8675488106:AAEK9zFIy5bw1zGYuuJ7p4tErcBYzPfZIWA"  # Bu yerga Telegram Bot tokeningizni yozing
MAIN_OWNER_ID = 5775388579  # Bu yerga o'zingizning Telegram ID-ingizni kiriting (Asosiy Owner)

DB_FILE = "db.json"

# --- MA'LUMOTLAR OMBORI (JSON FILE) ---
def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE):
        default_db = {
            "admin_id": MAIN_OWNER_ID,
            "admins": [],  # Yangi adminlar ro'yxati (ID list)
            "categories": [],
            "lessons": [],
            "users": [],
            "channels": []
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(default_db, f, indent=4, ensure_ascii=False)
        return default_db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ma'lumotlar omborini yuklashda xatolik: {e}")
        return {
            "admin_id": MAIN_OWNER_ID,
            "admins": [],
            "categories": [],
            "lessons": [],
            "users": [],
            "channels": []
        }

def save_db(data: Dict[str, Any]):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ma'lumotlar omborini saqlashda xatolik: {e}")

# --- BOT VA DISPATCHER ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# --- FSM STATES (HOLATLAR) ---
class BotStates(StatesGroup):
    waiting_for_cat_name = State()
    waiting_for_batch_videos = State()  # Ketma-ket darslik qo'shish holati
    waiting_for_vip_desc = State()
    waiting_for_vip_grant = State()
    waiting_for_vip_revoke = State()
    waiting_for_broadcast_all = State()
    waiting_for_broadcast_vip = State()
    waiting_for_broadcast_regular = State()
    waiting_for_chan_link = State()
    waiting_for_chan_name = State()
    waiting_for_chan_remove = State()
    # Adminlarni boshqarish holatlari
    waiting_for_new_admin_id = State()
    waiting_for_remove_admin = State()

# --- YORDAMCHI FUNKSIYALAR ---
def is_admin_user(user_id: int, db: Dict[str, Any]) -> bool:
    """Foydalanuvchi asosiy owner yoki tayyorlangan adminlardan biri ekanini tekshiradi."""
    if user_id == db.get("admin_id"):
        return True
    return user_id in db.get("admins", [])

def register_user(user_id: int, first_name: str, username: Optional[str], db: Dict[str, Any]) -> bool:
    """Foydalanuvchini bazaga qo'shadi."""
    users = db.get("users", [])
    exists = any(u["id"] == user_id for u in users)
    if not exists:
        users.append({
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "is_vip": False,
            "registered_at": datetime.now().isoformat()
        })
        db["users"] = users
        save_db(db)
        return True
    return False

async def check_subscription(user_id: int, db: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A'zo bo'lmagan majburiy kanallar ro'yxatini qaytaradi."""
    not_subscribed = []
    channels = db.get("channels", [])
    
    # Asosiy adminlarga tekshiruv shart emas
    if is_admin_user(user_id, db):
        return []

    for chan in channels:
        try:
            member = await bot.get_chat_member(chat_id=chan["id"], user_id=user_id)
            if member.status in ["left", "kicked"]:
                not_subscribed.append(chan)
        except Exception as e:
            logger.warning(f"Kanal a'zoligini tekshirishda xatolik ({chan['id']}): {e}")
            # Agar bot kanalda admin bo'lmasa, a'zolikni tekshira olmaydi, foydalanuvchiga muammo yaratmaslik uchun o'tkazib yuboramiz
            pass
    return not_subscribed

# --- KLAVIATURALAR ---
def get_main_keyboard(user_id: int, db: Dict[str, Any]) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📂 Bo'limlar"), KeyboardButton(text="💎 VIP Bo'lim")]
    ]
    if is_admin_user(user_id, db):
        keyboard.append([KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⚙️ Admin Panel")])
    else:
        keyboard.append([KeyboardButton(text="📊 Statistika")])
        
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard(user_id: int, db: Dict[str, Any]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📂 Bo'lim Yaratish", callback_data="admin_add_cat"),
            InlineKeyboardButton(text="❌ Bo'lim O'chirish", callback_data="admin_del_cat_menu")
        ],
        [
            InlineKeyboardButton(text="🎥 Video/Dars Qo'shish", callback_data="admin_add_lesson"),
            InlineKeyboardButton(text="❌ Dars O'chirish", callback_data="admin_del_les_menu")
        ],
        [
            InlineKeyboardButton(text="🔗 Kanal Qo'shish", callback_data="admin_add_chan"),
            InlineKeyboardButton(text="❌ Kanal O'chirish", callback_data="admin_del_chan_menu")
        ],
        [
            InlineKeyboardButton(text="💎 VIP Berish", callback_data="admin_grant_vip_menu"),
            InlineKeyboardButton(text="➖ VIPni O'chirish", callback_data="admin_revoke_vip_menu")
        ],
        [
            InlineKeyboardButton(text="✍️ VIP Matni", callback_data="admin_set_vip_desc"),
            InlineKeyboardButton(text="📢 Xabar Yuborish", callback_data="admin_broadcast_menu")
        ]
    ]
    
    # Faqat asosiy ownerga adminlarni boshqarish ruxsat etiladi
    if user_id == db.get("admin_id"):
        buttons.append([InlineKeyboardButton(text="👤 Adminlarni Boshqarish", callback_data="owner_manage_admins")])
        
    buttons.append([InlineKeyboardButton(text="❌ Panelni Yopish", callback_data="close_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- START BUYRUG'I ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    db = load_db()
    register_user(user_id, first_name, username, db)
    
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        kb_buttons = []
        for i, chan in enumerate(not_joined):
            kb_buttons.append([InlineKeyboardButton(text=chan["name"], url=chan["link"])])
        
        kb_buttons.append([InlineKeyboardButton(text="🔄 Tekshirish", callback_data="check_subs_status")])
        
        await message.answer(
            f"Salom, **{first_name}**! 👋\n\nBotdan foydalanish uchun quyidagi kanallarimizga a'zo bo'ling:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
            parse_mode="Markdown"
        )
        return

    await message.answer(
        f"Salom, **{first_name}**! 👋\n\nBotimizga xush kelibsiz! Kerakli bo'limni tanlang:",
        reply_markup=get_main_keyboard(user_id, db),
        parse_mode="Markdown"
    )

# --- OBUNALIKNI TEKSHIRISH (CALLBACK) ---
@router.callback_query(F.data == "check_subs_status")
async def check_subs_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = load_db()
    not_joined = await check_subscription(user_id, db)
    
    if not_joined:
        await callback.answer("❌ Hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)
        return
        
    await callback.message.delete()
    await callback.message.answer(
        "Rahmat! Kanallarga obuna tasdiqlandi. 🎉\nBotdan bemalol foydalanishingiz mumkin:",
        reply_markup=get_main_keyboard(user_id, db)
    )

# --- ASOSIY MENYULAR ---
@router.message(F.text == "📂 Bo'limlar")
async def show_categories(message: Message):
    user_id = message.from_user.id
    db = load_db()
    
    # Kanal a'zoligini tekshirish
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        await cmd_start(message, None)
        return
        
    categories = db.get("categories", [])
    if not categories:
        await message.answer("📂 Bo'limlar hozircha mavjud emas.")
        return
        
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=f"cat_view_{cat['id']}")])
        
    await message.answer(
        "📂 **Kurs bo'limlaridan birini tanlang:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )

# --- BO'LIMNI KO'RISH (VIDEOLARNI BIRDANIGA CHIQARISH) ---
@router.callback_query(F.data.startswith("cat_view_"))
async def view_category_lessons(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = load_db()
    
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        await callback.answer("Iltimos, avval obuna bo'ling!", show_alert=True)
        return
        
    cat_id = callback.data.replace("cat_view_", "")
    category = next((c for c in db.get("categories", []) if c["id"] == cat_id), None)
    
    if not category:
        await callback.answer("Bo'lim topilmadi!", show_alert=True)
        return
        
    lessons = [l for l in db.get("lessons", []) if l["category_id"] == cat_id]
    
    if not lessons:
        await callback.message.answer(
            f"📂 **{category['name']}** bo'limida hozircha darsliklar mavjud emas.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_categories")
            ]])
        )
        await callback.answer()
        return
        
    await callback.message.answer(f"📂 **{category['name']}** bo'limi darsliklari yuklanmoqda... (Jami: {len(lessons)} ta)")
    
    # VIP statusini tekshirish
    user_data = next((u for u in db.get("users", []) if u["id"] == user_id), None)
    is_vip = user_data.get("is_vip", False) if user_data else False
    is_admin = is_admin_user(user_id, db)
    
    # Har bir darslikni ketma-ket yuboramiz
    for lesson in lessons:
        if lesson.get("is_vip_only", False) and not is_vip and not is_admin:
            await callback.message.answer(
                f"🔒 **[FAQAT VIP DARSLIK]**\n\n🎥 **{lesson['title']}**\n\n_Ushbu darslik faqat VIP a'zolar uchun! Ko'rish uchun VIP bo'limiga o'tib obuna bo'ling._ 💎",
                parse_mode="Markdown"
            )
            continue
            
        caption = f"🎥 **{lesson['title']}**\n\n"
        if lesson.get("description"):
            caption += f"{lesson['description']}\n\n"
            
        # Video turi fayl bo'lsa
        if lesson.get("video_type") == "file" and lesson.get("video_file_id"):
            try:
                # Video yoki boshqa hujjatni file_id orqali yuboramiz
                await callback.message.answer_video(
                    video=lesson["video_file_id"],
                    caption=caption,
                    parse_mode="Markdown"
                )
            except Exception as e:
                # Agar video yuborish o'xshama-sa (masalan rasm yoki fayl bo'lsa), oddiy hujjat yoki rasm qilib urinamiz
                try:
                    await callback.message.answer_document(
                        document=lesson["video_file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                except Exception as e2:
                    await callback.message.answer(
                        caption + f"\n\n*(Fayl yuklash xatosi, File ID: {lesson['video_file_id']})*"
                    )
        else:
            # Agar video url bo'lsa
            if lesson.get("video_url"):
                caption += f"🔗 **Video Havolasi:** {lesson['video_url']}"
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🎥 Videoni Ko'rish", url=lesson["video_url"])
                ]])
                await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
            else:
                await callback.message.answer(caption, parse_mode="Markdown")
                
        await asyncio.sleep(0.3) # Telegram limiti uchun kichik pauza
        
    await callback.message.answer(
        "📖 Boshqa bo'lim darsliklarini ko'rish uchun quyidagi tugmani bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga bo'limlarga", callback_data="back_to_categories")
        ]])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_categories")
async def back_to_cats_cb(callback: CallbackQuery):
    await callback.message.delete()
    db = load_db()
    categories = db.get("categories", [])
    if not categories:
        await callback.message.answer("📂 Bo'limlar hozircha mavjud emas.")
        return
        
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=f"cat_view_{cat['id']}")])
        
    await callback.message.answer(
        "📂 **Kurs bo'limlaridan birini tanlang:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- VIP BO'LIM ---
@router.message(F.text == "💎 VIP Bo'lim")
async def show_vip_section(message: Message):
    user_id = message.from_user.id
    db = load_db()
    
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        await cmd_start(message, None)
        return
        
    user_data = next((u for u in db.get("users", []) if u["id"] == user_id), None)
    is_vip = user_data.get("is_vip", False) if user_data else False
    
    vip_status = "💎 Sizda VIP a'zolik faol!" if is_vip else "❌ Siz hali VIP a'zo emassiz."
    vip_desc = db.get("vip_desc", "VIP darsliklar orqali yanada ko'proq foydali darslarni ko'rishingiz mumkin. VIP sotib olish uchun adminga murojaat qiling.")
    
    await message.answer(
        f"💎 **VIP A'ZOLIK BO'LIMI**\n\n"
        f"**Sizning holatingiz:** {vip_status}\n\n"
        f"ℹ️ **VIP haqida:**\n{vip_desc}",
        parse_mode="Markdown"
    )

# --- STATISTIKA (FOYDALANUVCHILAR VA ADMINLAR ALOHIDA) ---
@router.message(F.text == "📊 Statistika")
async def show_statistics(message: Message):
    user_id = message.from_user.id
    db = load_db()
    
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        await cmd_start(message, None)
        return
        
    user_data = next((u for u in db.get("users", []) if u["id"] == user_id), None)
    is_vip = user_data.get("is_vip", False) if user_data else False
    is_admin = is_admin_user(user_id, db)
    
    reg_date = "Noma'lum"
    if user_data and user_data.get("registered_at"):
        try:
            reg_date = datetime.fromisoformat(user_data["registered_at"]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            reg_date = user_data["registered_at"]
            
    total_users = len(db.get("users", []))
    total_vips = sum(1 for u in db.get("users", []) if u.get("is_vip"))
    
    msg = f"📊 **Sizning Statistika:**\n\n"
    msg += f"👤 Ism: {message.from_user.first_name}\n"
    msg += f"💎 VIP status: {'Faol 💎' if is_vip else 'Noaktiv ❌'}\n"
    msg += f"📅 Ro'yxatdan o'tgan sana: {reg_date}\n\n"
    
    msg += f"🌐 **Bot statistikasi:**\n"
    if is_admin:
        # Faqat adminlar jami foydalanuvchilar va vip a'zolar sonini ko'ra oladi!
        msg += f"👥 Jami foydalanuvchilar: {total_users} ta\n"
        msg += f"💎 VIP a'zolar: {total_vips} ta\n"
    else:
        # Oddiy foydalanuvchilar buni ko'rmaydi
        pass
        
    msg += f"📚 Jami bo'limlar: {len(db.get('categories', []))} ta\n"
    msg += f"🎥 Jami darsliklar: {len(db.get('lessons', []))} ta\n"
    
    await message.answer(msg, parse_mode="Markdown")

# --- ADMIN PANEL BOSHLANISHI ---
@router.message(F.text == "⚙️ Admin Panel")
async def open_admin_panel(message: Message):
    user_id = message.from_user.id
    db = load_db()
    if not is_admin_user(user_id, db):
        return
        
    await message.answer(
        "⚙️ **Admin boshqaruv paneliga xush kelibsiz!**\n\nKerakli buyruqni tanlang:",
        reply_markup=get_admin_keyboard(user_id, db),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_cb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db = load_db()
    if not is_admin_user(user_id, db):
        return
        
    # Agarda video ketma-ket yuklashda yakunlangan bo'lsa
    current_state = await state.get_state()
    if current_state == BotStates.waiting_for_batch_videos:
        data = await state.get_data()
        pending = data.get("pending_lessons", [])
        if pending:
            db["lessons"].extend(pending)
            save_db(db)
            await callback.message.answer(f"✅ Seans yakunlandi! {len(pending)} ta darslik saqlandi.")
        else:
            await callback.message.answer("⚠️ Hech narsa yuklanmadi.")
            
    await state.clear()
    await callback.message.edit_text(
        "⚙️ **Admin boshqaruv paneliga xush kelibsiz!**\n\nKerakli buyruqni tanlang:",
        reply_markup=get_admin_keyboard(user_id, db),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "close_admin")
async def close_admin_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Admin panel yopildi.")
    await callback.answer()

# --- ADMIN: BO'LIM YARATISH ---
@router.callback_query(F.data == "admin_add_cat")
async def add_cat_cb(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
    await state.set_state(BotStates.waiting_for_cat_name)
    await callback.message.edit_text(
        "📂 **Yangi bo'lim (kategoriya) nomini yuboring:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_cat_name)
async def process_cat_name(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    cat_name = message.text.strip()
    new_cat = {
        "id": f"cat_{int(datetime.now().timestamp())}",
        "name": cat_name
    }
    db["categories"].append(new_cat)
    save_db(db)
    
    await state.clear()
    await message.answer(
        f"✅ Yangi bo'lim **\"{cat_name}\"** muvaffaqiyatli yaratildi!",
        reply_markup=get_main_keyboard(message.from_user.id, db),
        parse_mode="Markdown"
    )
    # Admin panelga qaytarish
    await message.answer("Boshqarishda davom etish:", reply_markup=get_admin_keyboard(message.from_user.id, db))

# --- ADMIN: BO'LIM O'CHIRISH ---
@router.callback_query(F.data == "admin_del_cat_menu")
async def del_cat_menu(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    categories = db.get("categories", [])
    if not categories:
        await callback.answer("Hozircha bo'limlar mavjud emas!", show_alert=True)
        return
        
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=f"❌ {cat['name']}", callback_data=f"admin_del_cat_{cat['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "❌ **O'chirmoqchi bo'lgan bo'limingizni tanlang:**\n*(Eslatma: O'chirilgan bo'lim ichidagi barcha videolar ham o'chib ketadi)*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_del_cat_"))
async def process_del_cat(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    cat_id = callback.data.replace("admin_del_cat_", "")
    cat = next((c for c in db.get("categories", []) if c["id"] == cat_id), None)
    
    if not cat:
        await callback.answer("Bo'lim topilmadi!", show_alert=True)
        return
        
    # Bo'lim va darsliklarni o'chiramiz
    db["categories"] = [c for c in db["categories"] if c["id"] != cat_id]
    db["lessons"] = [l for l in db["lessons"] if l["category_id"] != cat_id]
    save_db(db)
    
    await callback.answer(f"\"{cat['name']}\" bo'limi muvaffaqiyatli o'chirildi!", show_alert=True)
    await del_cat_menu(callback)

# --- ADMIN: KETMA-KET VIDEO QO'SHISH (YANGI TIZIM) ---
@router.callback_query(F.data == "admin_add_lesson")
async def add_lesson_select_cat(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    categories = db.get("categories", [])
    if not categories:
        await callback.answer("❌ Video qo'shish uchun avval kamida bitta bo'lim yaratishingiz kerak!", show_alert=True)
        return
        
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=f"admin_batch_select_cat_{cat['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "📂 **Qaysi bo'limga darslik yoki videolarni yuklamoqchisiz?**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_batch_select_cat_"))
async def process_batch_select_cat(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    cat_id = callback.data.replace("admin_batch_select_cat_", "")
    category = next((c for c in db["categories"] if c["id"] == cat_id), None)
    if not category:
        await callback.answer("Bo'lim topilmadi!", show_alert=True)
        return
        
    await state.set_state(BotStates.waiting_for_batch_videos)
    await state.update_data(category_id=cat_id, is_vip_only=False, pending_lessons=[])
    
    await callback.message.edit_text(
        f"📂 **\"{category['name']}\" bo'limi tanlandi!**\n\n"
        f"Hozir darsliklar: **✅ Oddiy (barcha uchun ochiq)** tarzda saqlanadi.\n\n"
        f"📥 **Endi ushbu bo'limga videolarni, fayllarni yoki YouTube/veb havolalarni ketma-ket yuborishingiz (tashlashingiz) mumkin!** Bot ularni vaqtincha to'plab boradi.\n\n"
        f"• Yuborayotgan darsligingizning **izohi (caption)** dars sarlavhasi sifatida saqlanadi.\n"
        f"• Agar izohsiz bo'lsa, bot avtomatik ravishda \"Darslik #[N]\" deb nomlaydi.\n\n"
        f"🛑 **Yuklab bo'lgach, hammasini saqlab yakunlash uchun /tugadi deb yozib yuboring yoki quyidagi tugmani bosing!**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Faqat VIP uchun qilish", callback_data=f"admin_batch_toggle_vip_{cat_id}")],
            [InlineKeyboardButton(text="⏹️ Saqlash va yakunlash", callback_data="back_to_admin")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_batch_toggle_vip_"))
async def batch_toggle_vip(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    current_state = await state.get_state()
    if current_state != BotStates.waiting_for_batch_videos:
        await callback.answer("Seans muddati tugagan. Qaytadan urinib ko'ring.", show_alert=True)
        return
        
    cat_id = callback.data.replace("admin_batch_toggle_vip_", "")
    category = next((c for c in db["categories"] if c["id"] == cat_id), None)
    
    data = await state.get_data()
    is_vip_only = not data.get("is_vip_only", False)
    await state.update_data(is_vip_only=is_vip_only)
    
    status_text = "💎 Faqat VIP foydalanuvchilar uchun" if is_vip_only else "✅ Oddiy (barcha uchun ochiq)"
    btn_text = "✅ Oddiy (barcha uchun) qilish" if is_vip_only else "💎 Faqat VIP uchun qilish"
    pending_count = len(data.get("pending_lessons", []))
    
    await callback.message.edit_text(
        f"📂 **\"{category['name']}\" bo'limi tanlangan!**\n\n"
        f"Hozir darsliklar: **{status_text}** tarzda saqlanadi.\n\n"
        f"📥 **Ketma-ket videolarni yoki havolalarni yuborishda davom eting!**\n\n"
        f"• Hozirgi seansda yuborilgan darsliklar: **{pending_count} ta**\n"
        f"🛑 **Yuklab bo'lgach, hammasini saqlab yakunlash uchun /tugadi deb yozib yuboring!**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin_batch_toggle_vip_{cat_id}")],
            [InlineKeyboardButton(text="⏹️ Saqlash va yakunlash", callback_data="back_to_admin")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- TERMINATION COMMAND FOR BATCH ADDING ---
@router.message(BotStates.waiting_for_batch_videos, Command("tugadi"))
@router.message(BotStates.waiting_for_batch_videos, F.text.lower() == "tugadi")
async def batch_upload_finished(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db = load_db()
    if not is_admin_user(user_id, db):
        return
        
    data = await state.get_data()
    cat_id = data.get("category_id")
    category = next((c for c in db["categories"] if c["id"] == cat_id), None)
    
    pending = data.get("pending_lessons", [])
    
    if not category:
        await message.answer("❌ Xatolik: Bo'lim topilmadi. Yuklash bekor qilindi.")
        await state.clear()
        return

    if not pending:
        await message.answer("⚠️ Hech qanday darslik yoki video yuklanmadi.")
    else:
        db["lessons"].extend(pending)
        save_db(db)
        await message.answer(
            f"✅ **Barcha darsliklar muvaffaqiyatli saqlandi!**\n\n"
            f"• **Bo'lim:** {category['name']}\n"
            f"• **Saqlangan darsliklar soni:** {len(pending)} ta\n\n"
            f"Ular barcha foydalanuvchilarga taqdim etildi! 🚀",
            reply_markup=get_main_keyboard(user_id, db),
            parse_mode="Markdown"
        )
        
    await state.clear()
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(user_id, db))

# --- HANDLER FOR NEW VIDEO/FILE/TEXT DURING BATCH UPLOAD ---
@router.message(BotStates.waiting_for_batch_videos)
async def process_batch_upload_item(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db = load_db()
    if not is_admin_user(user_id, db):
        return
        
    data = await state.get_data()
    cat_id = data.get("category_id")
    is_vip_only = data.get("is_vip_only", False)
    pending_lessons = data.get("pending_lessons", [])
    
    category = next((c for c in db["categories"] if c["id"] == cat_id), None)
    if not category:
        await message.answer("❌ Xatolik: Bo'lim topilmadi.")
        await state.clear()
        return
        
    already_saved_count = sum(1 for l in db.get("lessons", []) if l["category_id"] == cat_id)
    total_count = already_saved_count + len(pending_lessons)
    
    lesson_title = ""
    lesson_desc = ""
    video_url = ""
    video_file_id = ""
    video_type = "file"
    
    # Check media type
    if message.video:
        video_file_id = message.video.file_id
        video_type = "file"
        text = message.caption or ""
    elif message.document:
        video_file_id = message.document.file_id
        video_type = "file"
        text = message.caption or ""
    elif message.photo:
        video_file_id = message.photo[-1].file_id
        video_type = "file"
        text = message.caption or ""
    elif message.animation:
        video_file_id = message.animation.file_id
        video_type = "file"
        text = message.caption or ""
    else:
        # Just text (could be a link)
        text = message.text or ""
        video_type = "url"
        
    # Parse title and description
    if text:
        text_lines = [l.strip() for l in text.split("\n") if l.strip()]
        if text_lines:
            lesson_title = text_lines[0]
            if len(text_lines) > 1:
                lesson_desc = "\n".join(text_lines[1:])
            else:
                lesson_desc = text
                
    if not lesson_title:
        lesson_title = f"Darslik #{total_count + 1}"
        lesson_desc = f"Telegram orqali yuklangan darslik #{total_count + 1}"
        
    # Handle URLs
    if video_type == "url" and text:
        is_url = text.startswith("http://") or text.startswith("https://") or "youtube.com" in text or "youtu.be" in text
        if is_url:
            video_url = text.split("\n")[0].strip()
            if len(text.split("\n")) > 1:
                lesson_title = f"Darslik #{total_count + 1}"
                lesson_desc = "\n".join(text.split("\n")[1:])
        else:
            lesson_title = text[:40] + ("..." if len(text) > 40 else "")
            lesson_desc = text
            video_url = ""
            
    # Create temp lesson object
    new_lesson = {
        "id": f"les_{int(datetime.now().timestamp())}_{total_count}",
        "category_id": cat_id,
        "title": lesson_title,
        "description": lesson_desc,
        "video_url": video_url,
        "video_file_id": video_file_id,
        "video_type": video_type,
        "is_vip_only": is_vip_only,
        "created_at": datetime.now().isoformat()
    }
    
    pending_lessons.append(new_lesson)
    await state.update_data(pending_lessons=pending_lessons)
    
    status_text = "💎 VIP darslik" if is_vip_only else "✅ Oddiy darslik"
    file_label = "📁 Telegram fayl" if video_file_id else ("🔗 Havola" if video_url else "📝 Matn")
    btn_text = "✅ Oddiy (barcha uchun) qilish" if is_vip_only else "💎 Faqat VIP uchun qilish"
    
    await message.answer(
        f"📥 **Darslik vaqtincha qabul qilindi!**\n\n"
        f"• **Bo'lim:** {category['name']}\n"
        f"• **Sarlavha:** {lesson_title}\n"
        f"• **Turi:** {file_label}\n"
        f"• **Status:** {status_text}\n\n"
        f"💡 Ushbu seansda yuklangan jami darsliklar: **{len(pending_lessons)} ta**\n\n"
        f"📥 Yana video, rasm, fayl yoki havolalar yuborishingiz mumkin. Bot ularni to'plab boradi.\n\n"
        f"🛑 **Yuklashni tugatish va barchasini saqlash uchun:** /tugadi deb yozib yuboring!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data=f"admin_batch_toggle_vip_{cat_id}")],
            [InlineKeyboardButton(text="⏹| Saqlash va yakunlash", callback_data="back_to_admin")]
        ]),
        parse_mode="Markdown"
    )

# --- ADMIN: DARSLIKNI O'CHIRISH ---
@router.callback_query(F.data == "admin_del_les_menu")
async def del_lesson_select_cat(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    categories = db.get("categories", [])
    if not categories:
        await callback.answer("Hozircha bo'limlar mavjud emas!", show_alert=True)
        return
        
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=f"admin_del_les_cat_{cat['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "📂 **Qaysi bo'limdagi darslikni o'chirmoqchisiz?**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_del_les_cat_"))
async def del_lesson_list(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    cat_id = callback.data.replace("admin_del_les_cat_", "")
    category = next((c for c in db["categories"] if c["id"] == cat_id), None)
    
    if not category:
        await callback.answer("Bo'lim topilmadi!", show_alert=True)
        return
        
    lessons = [l for l in db["lessons"] if l["category_id"] == cat_id]
    if not lessons:
        await callback.message.edit_text(
            f"📂 **{category['name']}** bo'limida darsliklar mavjud emas.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_del_les_menu")
            ]])
        )
        await callback.answer()
        return
        
    buttons = []
    for l in lessons:
        vip_tag = "[💎] " if l.get("is_vip_only") else ""
        buttons.append([InlineKeyboardButton(text=f"❌ {vip_tag}{l['title']}", callback_data=f"admin_del_item_{l['id']}_{cat_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_del_les_menu")])
    
    await callback.message.edit_text(
        f"❌ **\"{category['name']}\" bo'limidagi darslikni tanlang:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_del_item_"))
async def process_del_lesson(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    parts = callback.data.replace("admin_del_item_", "").split("_")
    les_id = parts[0] + "_" + parts[1] # JSON structure of ID is 'les_timestamp'
    cat_id = parts[2]
    
    db["lessons"] = [l for l in db["lessons"] if l["id"] != les_id]
    save_db(db)
    
    await callback.answer("Darslik o'chirildi!", show_alert=True)
    
    # Callbackni darsliklar ro'yxatiga qaytaramiz
    callback.data = f"admin_del_les_cat_{cat_id}"
    await del_lesson_list(callback)

# --- ADMIN: KANALLARNI BOSHQARISH ---
@router.callback_query(F.data == "admin_add_chan")
async def add_channel_cb(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
    await state.set_state(BotStates.waiting_for_chan_link)
    await callback.message.edit_text(
        "🔗 **Yangi kanal taklif havolasini yuboring (Masalan: https://t.me/kanal_nomi yoki @kanal_nomi):**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_chan_link)
async def process_chan_link(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    link = message.text.strip()
    await state.update_data(link=link)
    await state.set_state(BotStates.waiting_for_chan_name)
    await message.answer(
        "✍️ **Kanal uchun sarlavha yuboring (Masalan: \"Bizning Asosiy Kanal\"):**"
    )

@router.message(BotStates.waiting_for_chan_name)
async def process_chan_name(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    data = await state.get_data()
    link = data.get("link")
    name = message.text.strip()
    
    # ID ni aniqlash
    chan_id = ""
    if "@" in link:
        chan_id = link
    elif "t.me/" in link:
        parts = link.split("t.me/")
        chan_id = "@" + parts[1].replace("+", "").split("/")[0]
    else:
        # Linkdan ID topilmasa o'zini yozadi
        chan_id = link
        
    # Bot kanal adminimi tekshirish
    try:
        await bot.get_chat(chat_id=chan_id)
    except Exception as e:
        await message.answer(
            f"⚠️ **Eslatma:** Bot bu kanalni topa olmadi yoki u yerda admin emas. "
            f"Foydalanuvchilar a'zoligini tekshirish uchun bot kanalda admin bo'lishi shart!\n\n"
            f"Kanal: {chan_id}\n\nKanal baribir qo'shildi."
        )

    new_chan = {
        "id": chan_id,
        "name": name,
        "link": link
    }
    
    db["channels"].append(new_chan)
    save_db(db)
    
    await state.clear()
    await message.answer(f"✅ Kanal **\"{name}\"** muvaffaqiyatli qo'shildi!")
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

@router.callback_query(F.data == "admin_del_chan_menu")
async def del_chan_menu(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    channels = db.get("channels", [])
    if not channels:
        await callback.answer("Hozircha majburiy obuna kanallari yo'q!", show_alert=True)
        return
        
    buttons = []
    for chan in channels:
        buttons.append([InlineKeyboardButton(text=f"❌ {chan['name']}", callback_data=f"admin_del_chan_{chan['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "❌ **O'chirmoqchi bo'lgan majburiy kanalni tanlang:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_del_chan_"))
async def process_del_chan(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    chan_id = callback.data.replace("admin_del_chan_", "")
    db["channels"] = [c for c in db["channels"] if c["id"] != chan_id]
    save_db(db)
    
    await callback.answer("Kanal muvaffaqiyatli o'chirildi!", show_alert=True)
    await del_chan_menu(callback)

# --- ADMIN: VIP HOLATINI BOSHQARISH ---
@router.callback_query(F.data == "admin_grant_vip_menu")
async def grant_vip_menu(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
    await state.set_state(BotStates.waiting_for_vip_grant)
    await callback.message.edit_text(
        "👤 **VIP bermoqchi bo'lgan foydalanuvchining Telegram ID raqamini yoki Username'ini yuboring:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_vip_grant)
async def process_grant_vip(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    input_val = message.text.strip()
    users = db.get("users", [])
    target_user = None
    
    # ID yoki username bo'yicha qidirish
    if input_val.isdigit():
        uid = int(input_val)
        target_user = next((u for u in users if u["id"] == uid), None)
    else:
        username = input_val.replace("@", "")
        target_user = next((u for u in users if u.get("username") and u["username"].lower() == username.lower()), None)
        
    if not target_user:
        await message.answer(f"❌ Foydalanuvchi **\"{input_val}\"** bot ma'lumotlar bazasida topilmadi. Avval u botni boshlashi kerak!")
        await state.clear()
        return
        
    target_user["is_vip"] = True
    save_db(db)
    
    # Foydalanuvchiga xabar yuborish
    try:
        await bot.send_message(
            chat_id=target_user["id"],
            text="💎 **Tabriklaymiz! Sizga botda VIP a'zolik taqdim etildi!**\nSiz endi barcha VIP darsliklarni ko'rishingiz mumkin! 🎉"
        )
    except Exception:
        pass
        
    await state.clear()
    await message.answer(f"✅ Foydalanuvchi **{target_user['first_name']}** (ID: {target_user['id']}) ga muvaffaqiyatli VIP a'zolik berildi!")
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

@router.callback_query(F.data == "admin_revoke_vip_menu")
async def revoke_vip_menu(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
    await state.set_state(BotStates.waiting_for_vip_revoke)
    await callback.message.edit_text(
        "👤 **VIP statusini o'chirmoqchi bo'lgan foydalanuvchining Telegram ID yoki Username'ini yuboring:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_vip_revoke)
async def process_revoke_vip(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    input_val = message.text.strip()
    users = db.get("users", [])
    target_user = None
    
    if input_val.isdigit():
        uid = int(input_val)
        target_user = next((u for u in users if u["id"] == uid), None)
    else:
        username = input_val.replace("@", "")
        target_user = next((u for u in users if u.get("username") and u["username"].lower() == username.lower()), None)
        
    if not target_user:
        await message.answer("❌ Foydalanuvchi topilmadi!")
        await state.clear()
        return
        
    target_user["is_vip"] = False
    save_db(db)
    
    try:
        await bot.send_message(
            chat_id=target_user["id"],
            text="❌ **Sizning VIP a'zolik muddatingiz tugadi yoki bekor qilindi.**\nOddiy darsliklardan foydalanishda davom etishingiz mumkin."
        )
    except Exception:
        pass
        
    await state.clear()
    await message.answer(f"✅ **{target_user['first_name']}** dan VIP a'zolik muvaffaqiyatli o'chirildi!")
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

# --- ADMIN: VIP MA'LUMOTINI O'ZGARTIRISH ---
@router.callback_query(F.data == "admin_set_vip_desc")
async def set_vip_desc_cb(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
    await state.set_state(BotStates.waiting_for_vip_desc)
    await callback.message.edit_text(
        "✍️ **VIP bo'limda ko'rinadigan yangi ma'lumot (tariflar, shartlar, aloqa) matnini yuboring:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_vip_desc)
async def process_vip_desc(message: Message, state: FSMContext):
    db = load_db()
    if not is_admin_user(message.from_user.id, db):
        return
        
    db["vip_desc"] = message.text.strip()
    save_db(db)
    
    await state.clear()
    await message.answer("✅ VIP ma'lumot matni muvaffaqiyatli o'zgartirildi!")
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

# --- ADMIN: XABAR TARQATISH (REKLAMA) ---
@router.callback_query(F.data == "admin_broadcast_menu")
async def broadcast_menu(callback: CallbackQuery):
    db = load_db()
    if not is_admin_user(callback.from_user.id, db):
        return
        
    buttons = [
        [InlineKeyboardButton(text="👥 Jami a'zolarga", callback_data="admin_bc_all")],
        [InlineKeyboardButton(text="💎 Faqat VIP a'zolarga", callback_data="admin_bc_vip")],
        [InlineKeyboardButton(text="👤 Faqat Oddiy a'zolarga", callback_data="admin_bc_regular")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")]
    ]
    await callback.message.edit_text(
        "📢 **Xabarni kimlarga yubormoqchisiz?**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_bc_all")
async def bc_all_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_broadcast_all)
    await callback.message.edit_text("📢 **Jami foydalanuvchilarga yuboriladigan xabarni (matn, rasm, video) yuboring:**")
    await callback.answer()

@router.callback_query(F.data == "admin_bc_vip")
async def bc_vip_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_broadcast_vip)
    await callback.message.edit_text("💎 **Faqat VIP foydalanuvchilarga yuboriladigan xabarni yuboring:**")
    await callback.answer()

@router.callback_query(F.data == "admin_bc_regular")
async def bc_reg_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_broadcast_regular)
    await callback.message.edit_text("👤 **Faqat Oddiy foydalanuvchilarga yuboriladigan xabarni yuboring:**")
    await callback.answer()

async def send_broadcast(message: Message, users_list: List[Dict[str, Any]]):
    sent = 0
    failed = 0
    for u in users_list:
        try:
            # Send message based on type
            await message.copy_to(chat_id=u["id"])
            sent += 1
            await asyncio.sleep(0.05) # anti-flood
        except Exception:
            failed += 1
            
    await message.answer(f"📢 **Xabar tarqatish yakunlandi!**\n\n✅ Muvaffaqiyatli: {sent} ta\n❌ Muvaffaqiyatsiz: {failed} ta")

@router.message(BotStates.waiting_for_broadcast_all)
async def process_bc_all(message: Message, state: FSMContext):
    db = load_db()
    users = db.get("users", [])
    await state.clear()
    await message.answer("🚀 Xabar yuborish boshlandi...")
    await send_broadcast(message, users)
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

@router.message(BotStates.waiting_for_broadcast_vip)
async def process_bc_vip(message: Message, state: FSMContext):
    db = load_db()
    users = [u for u in db.get("users", []) if u.get("is_vip")]
    await state.clear()
    await message.answer("🚀 VIP a'zolarga xabar yuborish boshlandi...")
    await send_broadcast(message, users)
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

@router.message(BotStates.waiting_for_broadcast_regular)
async def process_bc_reg(message: Message, state: FSMContext):
    db = load_db()
    users = [u for u in db.get("users", []) if not u.get("is_vip")]
    await state.clear()
    await message.answer("🚀 Oddiy a'zolarga xabar yuborish boshlandi...")
    await send_broadcast(message, users)
    await message.answer("Boshqaruv paneli:", reply_markup=get_admin_keyboard(message.from_user.id, db))

# ==============================================================================
# --- OWNER: ADMINLARNI BOSHQARISH (FAQAT MAIN OWNER UCHUN) ---
# ==============================================================================
@router.callback_query(F.data == "owner_manage_admins")
async def manage_admins_menu(callback: CallbackQuery):
    db = load_db()
    user_id = callback.from_user.id
    if user_id != db.get("admin_id"):
        await callback.answer("Ushbu bo'limga faqat asosiy bot egasi kira oladi!", show_alert=True)
        return
        
    admins = db.get("admins", [])
    
    text = "👤 **ADMINLARNI BOSHQARISH PANELI**\n\n"
    text += f"👑 **Asosiy Ega (Owner) ID:** `{db['admin_id']}`\n\n"
    
    if admins:
        text += "👥 **Hozirgi Adminlar ro'yxati:**\n"
        for i, adm_id in enumerate(admins, 1):
            # Username topishga harakat qilamiz
            u_info = next((u for u in db.get("users", []) if u["id"] == adm_id), None)
            name_tag = f" - {u_info['first_name']}" if u_info else ""
            user_tag = f" (@{u_info['username']})" if u_info and u_info.get("username") else ""
            text += f"{i}. ID: `{adm_id}`{name_tag}{user_tag}\n"
    else:
        text += "ℹ️ Hozircha qo'shimcha adminlar tayinlanmagan."
        
    buttons = [
        [
            InlineKeyboardButton(text="➕ Yangi Admin Qo'shish", callback_data="owner_add_admin"),
            InlineKeyboardButton(text="❌ Adminni O'chirish", callback_data="owner_del_admin_menu")
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_admin")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "owner_add_admin")
async def owner_add_admin_cb(callback: CallbackQuery, state: FSMContext):
    db = load_db()
    if callback.from_user.id != db.get("admin_id"):
        return
        
    await state.set_state(BotStates.waiting_for_new_admin_id)
    await callback.message.edit_text(
        "➕ **Yangi admin qilinadigan foydalanuvchining Telegram ID raqamini kiriting:**\n\n"
        "_Eslatma: Admin qilinayotgan foydalanuvchi avval botni kamida 1 marta ishga tushirgan bo'lishi shart._",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="owner_manage_admins")
        ]]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(BotStates.waiting_for_new_admin_id)
async def process_new_admin_id(message: Message, state: FSMContext):
    db = load_db()
    if message.from_user.id != db.get("admin_id"):
        return
        
    input_text = message.text.strip()
    if not input_text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat Telegram ID kiriting!")
        return
        
    new_admin_id = int(input_text)
    
    # Asosiy egasini o'zini admin ro'yxatiga qo'shishiga yo'l qo'ymaymiz
    if new_admin_id == db.get("admin_id"):
        await message.answer("⚠️ Siz allaqachon bot egasisiz, o'zingizni qo'shish shart emas!")
        await state.clear()
        return
        
    admins = db.get("admins", [])
    if new_admin_id in admins:
        await message.answer("⚠️ Ushbu foydalanuvchi allaqachon adminlar ro'yxatida bor!")
        await state.clear()
        return
        
    # Foydalanuvchi bazada bormi
    user_info = next((u for u in db.get("users", []) if u["id"] == new_admin_id), None)
    if not user_info:
        await message.answer(
            "⚠️ **Ushbu ID egasi botimiz bazasida topilmadi.**\n"
            "Admin tayinlash uchun u avval botimizga kirib /start bosgan bo'lishi kerak."
        )
        await state.clear()
        return
        
    admins.append(new_admin_id)
    db["admins"] = admins
    save_db(db)
    
    # Yangi adminga xabar berish
    try:
        await bot.send_message(
            chat_id=new_admin_id,
            text="⚙️ **Tabriklaymiz! Siz ushbu botga Admin qilib tayinlandingiz!**\nSiz endi admin panel va boshqaruv pultiga kirishingiz mumkin. /start yuboring!"
        )
    except Exception:
        pass
        
    await state.clear()
    await message.answer(f"✅ Foydalanuvchi **{user_info['first_name']}** (ID: `{new_admin_id}`) muvaffaqiyatli admin etib tayinlandi!")
    # Qayta boshqarish menyusi
    await message.answer("Adminlarni boshqarish:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Adminlar ro'yxatiga qaytish", callback_data="owner_manage_admins")
    ]]))

@router.callback_query(F.data == "owner_del_admin_menu")
async def owner_del_admin_menu_cb(callback: CallbackQuery):
    db = load_db()
    if callback.from_user.id != db.get("admin_id"):
        return
        
    admins = db.get("admins", [])
    if not admins:
        await callback.answer("Hozircha o'chirish uchun qo'shimcha adminlar yo'q!", show_alert=True)
        return
        
    buttons = []
    for adm_id in admins:
        u_info = next((u for u in db.get("users", []) if u["id"] == adm_id), None)
        label = u_info["first_name"] if u_info else f"ID: {adm_id}"
        buttons.append([InlineKeyboardButton(text=f"❌ {label}", callback_data=f"owner_del_admin_action_{adm_id}")])
        
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="owner_manage_admins")])
    
    await callback.message.edit_text(
        "❌ **O'chirmoqchi bo'lgan adminingizni tanlang:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("owner_del_admin_action_"))
async def process_owner_del_admin(callback: CallbackQuery):
    db = load_db()
    if callback.from_user.id != db.get("admin_id"):
        return
        
    target_id = int(callback.data.replace("owner_del_admin_action_", ""))
    
    db["admins"] = [adm for adm in db.get("admins", []) if adm != target_id]
    save_db(db)
    
    # Adminga xabar berish
    try:
        await bot.send_message(
            chat_id=target_id,
            text="❌ **Sizning ushbu botdagi adminlik huquqlaringiz bekor qilindi.**"
        )
    except Exception:
        pass
        
    await callback.answer("Admin muvaffaqiyatli o'chirildi!", show_alert=True)
    await manage_admins_menu(callback)


# ==============================================================================
# --- BOTGA KELGAN BOSHQA TEXT HABARLAR TIZIMI ---
# ==============================================================================
@router.message()
async def handle_any_other_messages(message: Message, state: FSMContext):
    # Agar foydalanuvchi obuna bo'lmagan bo'lsa majburiy obuna ko'rsatiladi
    user_id = message.from_user.id
    db = load_db()
    not_joined = await check_subscription(user_id, db)
    if not_joined:
        await cmd_start(message, state)
        return
        
    # Agar biror tushunarsiz buyruq yoki matn bo'lsa, start buyrug'i kabi bosh sahifani ochamiz
    await message.answer(
        "💡 **Noma'lum buyruq yoki xabar.**\nKerakli darsliklarni ko'rish uchun quyidagi bo'limlardan foydalaning:",
        reply_markup=get_main_keyboard(user_id, db),
        parse_mode="Markdown"
    )

# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    db = load_db()
    logger.info(f"Bot muvaffaqiyatli tayyorlandi. Asosiy Owner ID: {db.get('admin_id')}")
    
    dp.include_router(router)
    
    # Eskidan qolgan barcha so'rovlarni o'chirib yuboramiz (webhookni tozalash va toza boshlash)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Pollingni boshlash
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
