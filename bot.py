import os
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# আপনার বটের টোকেন এবং ডাটাবেজ লিংক এখানে সরাসরি সেট করা আছে
BOT_TOKEN = "9046722307:AAEGYeQsoPeLiiwcR1Q1RvkRrdm70u8G3VE"
MONGO_URI = "mongodb+srv://mdmafug5078_db_user:3Zw3FhgLlmUhF2sF@cluster0.gzd3tr1.mongodb.net/otp_shop_bot?retryWrites=true&w=majority"
ADMIN_ID = 7310456453

# বট ও ডাটাবেজ ইনিশিয়ালাইজেশন
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncIOMotorClient(MONGO_URI)
db = client["otp_shop_bot"]
users_collection = db["users"]
accounts_collection = db["accounts"]

# --- ১. স্টার্ট কমান্ড ও মেইন মেনু ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    
    if not user:
        user = {"userId": user_id, "balance": 0.0}
        await users_collection.insert_one(user)

    caption = (
        f"👋 স্বাগতম! আমাদের প্রিমিয়াম অ্যাকাউন্ট ও ওটিপি শপে।\n\n"
        f"💰 আপনার বর্তমান ব্যালেন্স: ৳{user['balance']}\n"
        f"🆔 ইউজার আইডি: `{user_id}`"
    )

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 নাম্বার কিনুন"), KeyboardButton(text="💰 ব্যালেন্স এড করুন")],
            [KeyboardButton(text="👤 আমার প্রোফাইল"), KeyboardButton(text="📞 সাপোর্ট")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(caption, parse_mode="Markdown", reply_markup=keyboard)

# --- ২. বাই মেনু: প্ল্যাটফর্ম সিলেকশন ---
@dp.message(F.text == "🛒 নাম্বার কিনুন")
async def buy_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Facebook Accounts / OTP", callback_data="buy_facebook")],
            [InlineKeyboardButton(text="🔙 মূল মেনু", callback_data="main_menu")]
        ]
    )
    await message.answer("📘 প্ল্যাটফর্ম সিলেক্ট করুন:", reply_markup=keyboard)

# --- ৩. কান্ট্রি ও স্টক সিলেকশন (Facebook) ---
@dp.callback_query(F.data == "buy_facebook")
async def select_facebook_country(callback: types.CallbackQuery):
    cursor = accounts_collection.find({"platform": "facebook", "isSold": False})
    accounts = await cursor.to_list(length=None)

    if not accounts:
        return await callback.answer("❌ দুঃখিত, বর্তমানে ফেসবুকে কোনো স্টক নেই!", show_alert=True)

    countries = list(set(acc["country"] for acc in accounts))
    inline_buttons = []

    for country in countries:
        stock_count = sum(1 for acc in accounts if acc["country"] == country)
        sample_acc = next(acc for acc in accounts if acc["country"] == country)
        
        btn_text = f"🌐 {country} • ৳{sample_acc['price']} • স্টক: ({stock_count}টি)"
        inline_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"country_{country}")])

    inline_buttons.append([InlineKeyboardButton(text="🔙 পেছনে যান", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await callback.message.edit_text("🌍 কান্ট্রি সিলেক্ট করুন:", reply_markup=keyboard)
    await callback.answer()

# --- ৪. ক্রয় ও ডেটা ডেলিভারি লজিক ---
@dp.callback_query(F.data.startswith("country_"))
async def process_purchase(callback: types.CallbackQuery):
    country = callback.data.split("_")[1]
    user_id = callback.from_user.id

    user = await users_collection.find_one({"userId": user_id})
    account = await accounts_collection.find_one({"platform": "facebook", "country": country, "isSold": False})

    if not account:
        return await callback.answer("❌ এই মুহূর্তে এই কান্ট্রির স্টক শেষ!", show_alert=True)

    if user["balance"] < account["price"]:
        return await callback.answer(f"❌ পর্যাপ্ত ব্যালেন্স নেই! আপনার প্রয়োজন ৳{account['price']}", show_alert=True)

    await users_collection.update_one({"userId": user_id}, {"$inc": {"balance": -account["price"]}})
    await accounts_collection.update_one({"_id": account["_id"]}, {"$set": {"isSold": True}})

    success_text = (
        f"🎉 অভিনন্দন! কেনাকাটা সফল হয়েছে。\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 **Number:** `{account['number']}`\n"
        f"🔑 **OTP / Code:** `{account['otp']}`\n"
        f"🔒 **Password:** `{account['password']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ ২৪ ঘণ্টার মধ্যে অ্যাকাউন্ট ব্যবহার করে নিন।"
    )

    await callback.message.edit_text(success_text, parse_mode="Markdown")
    await callback.answer()

# --- ৫. এডমিন কমান্ড: স্টক যোগ করা ---
@dp.message(Command("addfb"))
async def admin_add_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()[1:]
    if len(args) < 5:
        return await message.reply("সঠিক ফরম্যাট: /addfb [Country] [Price] [Number] [OTP] [Password]")

    country, price, number, otp, password = args

    await accounts_collection.insert_one({
        "platform": "facebook",
        "country": country,
        "price": float(price),
        "number": number,
        "otp": otp,
        "password": password,
        "isSold": False
    })

    await message.reply(f"✅ সফলভাবে স্টক যোগ করা হয়েছে!\nকান্ট্রি: {country}\nনাম্বার: {number}")

# --- ৬. এডমিন কমান্ড: ব্যালেন্স এড করা ---
@dp.message(Command("addbal"))
async def admin_add_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply("সঠিক ফরম্যাট: /addbal [UserId] [Amount]")

    target_user = int(args[0])
    amount = float(args[1])

    await users_collection.update_one(
        {"userId": target_user},
        {"$inc": {"balance": amount}},
        upsert=True
    )
    await message.reply(f"✅ User {target_user} কে ৳{amount} ব্যালেন্স দেওয়া হয়েছে।")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()

async def main():
    print("🚀 Python Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
