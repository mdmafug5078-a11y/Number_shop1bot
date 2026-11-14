import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী সেট করা) ---
BOT_TOKEN = "9046722307:AAEGYeQsoPeLiiwcR1Q1RvkRrdm70u8G3VE"      # আপনার বটের আসল টোকেনটি এখানে বসিয়ে দিন
CHANNEL_ID = "@QuickTaskPay"    # আপনার চ্যানেল ইউজারনেম (যেমন: @my_channel)
ADMIN_ID = 7310456453                  # আপনার টেলিগ্রাম আইডি

# MongoDB ক্লাউড ডাটাবেস কানেকশন
MONGO_URL = "mongodb+srv://mdmafug3016_db_user:YOUR_PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority"
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["telegram_shop_db"]

users_col = db["users"]
stocks_col = db["stocks"]

bot = Bot(token=BOT_TOKEN, parse_html=True)
dp = Dispatcher()

# --- ১. চ্যানেল মেম্বারশিপ চেক ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "creator", "administrator"]:
            return True
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
    return False

# --- ২. /start কমান্ড এবং চ্যানেল সাবস্ক্রিপশন চেক ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 আমাদের চ্যানেলে জয়েন করুন", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
            [InlineKeyboardButton(text="✅ জয়েন করেছি, চেক করুন", callback_data="check_join")]
        ])
        await message.answer(
            "⚠️ **বটটি ব্যবহার করতে হলে অবশ্যই আমাদের অফিশিয়াল চ্যানেলে জয়েন করতে হবে!**\n\n"
            "প্রথমে চ্যানেলে জয়েন করুন, তারপর নিচের বাটনে চাপ দিন।",
            reply_markup=keyboard
        )
        return

    # ইউজারের ডেটাবেস চেক বা ক্রিয়েট
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({"user_id": user_id, "balance": 10.0}) # টেস্টের জন্য ফ্রি ১০ টাকা

    await send_main_menu(message)

# --- মেইন মেনু ---
async def send_main_menu(event: types.Message | CallbackQuery):
    user_id = event.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    balance = user["balance"] if user else 0.0
    
    text = (
        f"<tg-emoji emoji-id='5435908178313227506'>🎉</tg-emoji> **অটো শপে স্বাগতম!**\n\n"
        f"এখানে খুব সহজে সোশ্যাল মিডিয়া অ্যাকাউন্ট ও ওটিপি কিনতে পারবেন।\n"
        f"💰 আপনার বর্তমান ব্যালেন্স: **৳{balance}**"
    )
    
    keyboard_buttons = [
        [InlineKeyboardButton(text="🛒 নাম্বার / অ্যাকাউন্ট কিনুন", callback_data="buy_menu")],
        [InlineKeyboardButton(text="👤 প্রফাইল", callback_data="profile"),
         InlineKeyboardButton(text="💳 ব্যালেন্স রিচার্জ", callback_data="add_balance")]
    ]
    
    # যদি ইউজার এডমিন হয়, তবে এডমিন প্যানেল বাটন দেখাবে
    if user_id == ADMIN_ID:
        keyboard_buttons.append([InlineKeyboardButton(text="🛠️ এডমিন প্যানেল", callback_data="admin_panel")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="📞 হেল্প ও সাপোর্ট", url="https://t.me/YourUsername")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    if isinstance(event, types.Message):
        await event.answer_sticker("CAACAgUAAxkBAAEJ...") 
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
        await callback.answer("❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)

# --- ৩. বাই মেনু ও কান্ট্রি স্টক লিস্ট ---
@dp.callback_query(F.data == "buy_menu")
async def process_buy_menu(callback: CallbackQuery):
    # ডাটাবেস থেকে উপলব্ধ কান্ট্রি ও স্টক গুনে বের করা
    pipeline = [{"$group": {"_id": "$country", "count": {"$sum": 1}, "price": {"$first": "$price"}}}]
    cursor = stocks_col.aggregate(pipeline)
    countries = await cursor.to_list(length=100)
    
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
    
    # স্টক থেকে প্রথম অ্যাভেইলেবল আইটেমটি নেওয়া
    item = await stocks_col.find_one({"country": country_name})
    if not item:
        await callback.answer("❌ দুঃখিত, এই মুহূর্তে এই কান্ট্রির স্টক শেষ!", show_alert=True)
        return
    
    price = item["price"]
    user = await users_col.find_one({"user_id": user_id})
    
    if user["balance"] < price:
        await callback.answer(f"❌ আপনার পর্যাপ্ত ব্যালেন্স নেই! প্রয়োজন ৳{price}", show_alert=True)
        return
    
    # ব্যালেন্স কাটা এবং ডেটাবেস থেকে স্টক ডিলিট করা
    await users_col.update_one({"user_id": user_id}, {"$inc": {"balance": -price}})
    await stocks_col.delete_one({"_id": item["_id"]})
    
    delivery_text = (
        f"✅ **সফলভাবে ক্রয় সম্পন্ন হয়েছে!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 **কান্ট্রি:** {country_name}\n"
        f"📱 **নম্বার:** `{item['number']}`\n"
        f"🔑 **পাসওয়ার্ড:** `{item['password']}`\n"
        f"📩 **OTP / কোড:** `{item['otp']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *নোট: ২৪ ঘণ্টার মধ্যে অ্যাকাউন্টটি লগইন করে ব্যাকআপ নিন।*"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 আরও কিনুন", callback_data="buy_menu")],
        [InlineKeyboardButton(text="🏠 মূল মেনু", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(delivery_text, reply_markup=keyboard)

# --- ৫. এডমিন প্যানেল (কোড পরিবর্তন ছাড়াই সব নিয়ন্ত্রণ) ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ আপনার এই অপশনে প্রবেশ করার অনুমতি নেই!", show_alert=True)
        return
    
    total_users = await users_col.count_documents({})
    total_stock = await stocks_col.count_documents({})
    
    text = (
        f"🛠️ **এডমিন কন্ট্রোল প্যানেল**\n\n"
        f"👥 মোট ইউজার: `{total_users}`\n"
        f"📦 মোট স্টক সংখ্যা: `{total_stock}`\n\n"
        f"স্টক যোগ করতে নিচের ফরম্যাট ব্যবহার করুন:\n"
        f"`/addstock কান্ট্রি_নাম | নাম্বার | ওটিপি | পাসওয়ার্ড | দাম`\n\n"
        f"উদাহরণ:\n`/addstock Italy | +393123456789 | 482910 | Pass123 | 1.0`"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 স্টক স্ট্যাটাস", callback_data="admin_stocks")],
        [InlineKeyboardButton(text="🏠 মূল মেনু", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)

# এডমিন কর্তৃক স্টক অ্যাড করার কমান্ড
@dp.message(Command("addstock"))
async def add_stock_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        # /addstock Italy | +39... | otp | pass | 1.0
        data_text = message.text.replace("/addstock", "").strip()
        parts = [p.strip() for p in data_text.split("|")]
        
        if len(parts) != 5:
            await message.reply("❌ ভুল ফরম্যাট! সঠিক নিয়মে দিন:\n`/addstock কান্ট্রি | নাম্বার | ওটিপি | পাসওয়ার্ড | দাম`")
            return
        
        country, number, otp, password, price = parts
        
        await stocks_col.insert_one({
            "country": country,
            "number": number,
            "otp": otp,
            "password": password,
            "price": float(price)
        })
        
        await message.reply(f"✅ সফলভাবে স্টক যোগ করা হয়েছে!\n🌍 কান্ট্রি: {country}\n📱 নাম্বার: {number}")
    except Exception as e:
        await message.reply(f"❌ ত্রুটি ঘটেছে: {e}")

# অন্যান্য শর্টকাট
@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await send_main_menu(callback)

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    balance = user["balance"] if user else 0.0
    text = f"👤 **আপনার প্রফাইল:**\n\n🆔 আইডি: `{callback.from_user.id}`\n💰 ব্যালেন্স: **৳{balance}**"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ পেছনে", callback_data="main_menu")]])
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "add_balance")
async def add_balance_prompt(callback: CallbackQuery):
    await callback.message.edit_text("💳 ব্যালেন্স রিচার্জ করতে এডমিনের সাথে যোগাযোগ করুন:\n👉 @YourUsername", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ পেছনের", callback_data="main_menu")]]))

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot with Admin Panel & MongoDB is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
