import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from motor.motor_asyncio import AsyncIOMotorClient

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী সেট করা) ---
BOT_TOKEN = "9046722307:AAEGYeQsoPeLiiwcR1Q1RvkRrdm70u8G3VE"      
CHANNEL_ID = "@QuickTaskPay"    # আপনার অফিশিয়াল চ্যানেল
ADMIN_ID = 7310456453                  # আপনার টেলিগ্রাম আইডি

# MongoDB ক্লাউড ডাটাবেস কানেকশন (আপনার পাসওয়ার্ডটি বসিয়ে নিন)
MONGO_URL = "mongodb+srv://mdmafug3016_db_user:YOUR_PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority"
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["telegram_shop_db"]

users_col = db["users"]
stocks_col = db["stocks"]

# HTML পার্স মোড সহ বট ইনিশিয়ালাইজেশন
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- ১. চ্যানেল মেম্বারশিপ চেক ---
async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:  # এডমিনের জন্য চ্যানেল চেক বাইপাস
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "creator", "administrator"]:
            return True
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
    return False

# --- ২. /start কমান্ড ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        channel_link = f"https://t.me/{CHANNEL_ID.replace('@', '')}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 আমাদের চ্যানেলে জয়েন করুন", url=channel_link)],
            [InlineKeyboardButton(text="✅ জয়েন করেছি, চেক করুন", callback_data="check_join")]
        ])
        await message.answer(
            "⚠️ <b>বটটি ব্যবহার করতে হলে অবশ্যই আমাদের অফিশিয়াল চ্যানেলে জয়েন করতে হবে!</b>\n\n"
            "প্রথমে চ্যানেলে জয়েন করুন, তারপর নিচের বাটনে চাপ দিন।",
            reply_markup=keyboard
        )
        return

    # ইউজার ডাটাবেসে না থাকলে অ্যাড করা
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({"user_id": user_id, "balance": 10.0})

    await send_main_menu(message)

# --- মেইন মেনু ---
async def send_main_menu(event: types.Message | CallbackQuery):
    user_id = event.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    balance = user["balance"] if user else 0.0
    
    text = (
        f"🎉 <b>অটো নাম্বার শপে স্বাগতম!</b>\n\n"
        f"এখানে খুব সহজে সোশ্যাল মিডিয়া অ্যাকাউন্ট ও ওটিপি কিনতে পারবেন।\n"
        f"💰 আপনার বর্তমান ব্যালেন্স: <b>৳{balance}</b>"
    )
    
    keyboard_buttons = [
        [InlineKeyboardButton(text="🛒 নাম্বার / অ্যাকাউন্ট কিনুন", callback_data="buy_menu")],
        [InlineKeyboardButton(text="👤 প্রফাইল", callback_data="profile"),
         InlineKeyboardButton(text="💳 ব্যালেন্স রিচার্জ", callback_data="add_balance")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard_buttons.append([InlineKeyboardButton(text="⚙️ এডমিন প্যানেল", callback_data="admin_panel")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=keyboard)
    else:
        await event.message.edit_text(text, reply_markup=keyboard)
        await event.answer()

@dp.callback_query(F.data == "check_join")
async def process_check_join(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        if not await users_col.find_one({"user_id": user_id}):
            await users_col.insert_one({"user_id": user_id, "balance": 10.0})
        await callback.message.delete()
        await send_main_menu(callback)
    else:
        await callback.answer("❌ আপনি এখনো চ্যানেলে জয়েন করেননি! আগে জয়েন করুন।", show_alert=True)

# --- ৩. বাই মেনু ও কান্ট্রি স্টক লিস্ট ---
@dp.callback_query(F.data == "buy_menu")
async def process_buy_menu(callback: CallbackQuery):
    pipeline = [{"$group": {"_id": "$country", "count": {"$sum": 1}, "price": {"$first": "$price"}}}]
    cursor = stocks_col.aggregate(pipeline)
    countries = await cursor.to_list(length=100)
    
    if not countries:
        await callback.answer("❌ এই মুহূর্তে কোনো স্টক নেই!", show_alert=True)
        return

    keyboard_buttons = []
    for c in countries:
        country_name = c["_id"]
        count = c["count"]
        price = c["price"]
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📌 {country_name} - ৳{price} [স্টক: {count}]", callback_data=f"buy_country_{country_name}")
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ মূল মেনু", callback_data="main_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text("<b>যে দেশের অ্যাকাউন্ট বা নাম্বার কিনতে চান সিলেক্ট করুন:</b>", reply_markup=keyboard)
    await callback.answer()

# --- ৪. অ্যাকাউন্ট ক্রয় ও ডেলিভারি ---
@dp.callback_query(F.data.startswith("buy_country_"))
async def process_buy_item(callback: CallbackQuery):
    country_name = callback.data.replace("buy_country_", "")
    user_id = callback.from_user.id
    
    item = await stocks_col.find_one({"country": country_name})
    if not item:
        await callback.answer("❌ দুঃখিত, এই কান্ট্রির স্টক শেষ!", show_alert=True)
        return
    
    price = item["price"]
    user = await users_col.find_one({"user_id": user_id})
    
    if not user or user["balance"] < price:
        await callback.answer(f"❌ পর্যাপ্ত ব্যালেন্স নেই! প্রয়োজন ৳{price}", show_alert=True)
        return
    
    await users_col.update_one({"user_id": user_id}, {"$inc": {"balance": -price}})
    await stocks_col.delete_one({"_id": item["_id"]})
    
    delivery_text = (
        f"✅ <b>সফলভাবে ক্রয় সম্পন্ন হয়েছে!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>কান্ট্রি:</b> {country_name}\n"
        f"📱 <b>নম্বার:</b> <code>{item['number']}</code>\n"
        f"🔑 <b>পাসওয়ার্ড:</b> <code>{item['password']}</code>\n"
        f"📩 <b>OTP / কোড:</b> <code>{item['otp']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>নোট: ২৪ ঘণ্টার মধ্যে অ্যাকাউন্টটি লগইন করে ব্যাকআপ নিন।</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 আরও কিনুন", callback_data="buy_menu")],
        [InlineKeyboardButton(text="🏠 মূল মেনু", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(delivery_text, reply_markup=keyboard)

# --- ৫. এডমিন প্যানেল ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ অনুমতি নেই!", show_alert=True)
        return
    
    total_users = await users_col.count_documents({})
    total_stock = await stocks_col.count_documents({})
    
    text = (
        f"🛠️ <b>এডমিন কন্ট্রোল প্যানেল</b>\n\n"
        f"👥 মোট ইউজার: <code>{total_users}</code>\n"
        f"📦 মোট স্টক: <code>{total_stock}</code>\n\n"
        f"<b>স্টক যোগ করার নিয়ম:</b>\n"
        f"<code>/addstock কান্ট্রি | নাম্বার | ওটিপি | পাসওয়ার্ড | দাম</code>\n\n"
        f"<b>উদাহরণ:</b>\n<code>/addstock Italy | +393123456789 | 482910 | Pass123 | 1.0</code>\n\n"
        f"<b>ব্যালেন্স দেওয়ার নিয়ম:</b>\n"
        f"<code>/addbal ইউজার_আইডি টাকার_পরিমাণ</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 মূল মেনু", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)

# স্টক অ্যাড কমান্ড
@dp.message(Command("addstock"))
async def add_stock_command(message: types.Message):
    if message.from_user.
