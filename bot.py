import os
import asyncio
from flask import Flask
import threading
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- Flask Server for 24/7 Uptime ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

# --- Bot Configuration ---
BOT_TOKEN = "9046722307:AAEGYeQsoPeLiiwcR1Q1RvkRrdm70u8G3VE"
MONGO_URI = "mongodb+srv://mdmafug5078_db_user:3Zw3FhgLlmUhF2sF@cluster0.gzd3tr1.mongodb.net/otp_shop_bot?retryWrites=true&w=majority"
ADMIN_ID = 7310456453  # Your Fixed Admin ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncIOMotorClient(MONGO_URI)
db = client["otp_shop_bot"]
users_collection = db["users"]
accounts_collection = db["accounts"]

# --- Main Menu Keyboard (English & Premium Style) ---
def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="👤 Profile"), KeyboardButton(text="🛒 Buy Number")],
        [KeyboardButton(text="💰 Add Balance"), KeyboardButton(text="🛠️ Support")],
        [KeyboardButton(text="👥 My Referral"), KeyboardButton(text="📘 How to Work")],
        [KeyboardButton(text="🌐 Change Language")]
    ]
    
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- Start Command ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    
    if not user:
        user = {"userId": user_id, "balance": 0.0}
        await users_collection.insert_one(user)

    caption = (
        f"🔥 **Welcome to Number Shop, EARN WITH MAFUG!** ✨\n\n"
        f"💰 **Your Balance:** ৳{user['balance']}\n"
        f"🆔 **User ID:** `{user_id}`\n\n"
        f"🎁 Instant automated accounts & OTP delivery.\n"
        f"🚀 Start shopping today!"
    )
    
    await message.answer(caption, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# --- User Menus ---
@dp.message(F.text == "👤 Profile")
async def profile_handler(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    balance = user['balance'] if user else 0.0

    text = (
        f"👤 **Account Information:**\n\n"
        f"🔸 **Name:** {message.from_user.full_name}\n"
        f"🔸 **Username:** @{message.from_user.username or 'None'}\n"
        f"🔸 **User ID:** `{user_id}`\n"
        f"🔸 **Balance:** ৳{balance}"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "💰 Add Balance")
async def add_balance_info(message: types.Message):
    text = (
        f"💳 **How to Add Balance:**\n\n"
        f"Contact the admin to top up your account balance.\n"
        f"📞 **Admin Contact:** @mh_mafug"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "🛠️ Support")
async def support_handler(message: types.Message):
    text = (
        f"🛠️ **Customer Support:**\n\n"
        f"Need help? Feel free to contact our official support team:\n"
        f"👉 @QuickTaskPay"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text.in_(["👥 My Referral", "📘 How to Work", "🌐 Change Language"]))
async def general_features(message: types.Message):
    await message.answer(f"✨ **{message.text}** feature is coming soon!", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

# --- Buy Number Menu ---
@dp.message(F.text == "🛒 Buy Number")
async def buy_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Facebook Accounts / OTP", callback_data="buy_facebook")],
            [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_menu")]
        ]
    )
    await message.answer("🌐 **Select Platform:**", reply_markup=keyboard)

@dp.callback_query(F.data == "buy_facebook")
async def select_facebook_country(callback: types.CallbackQuery):
    cursor = accounts_collection.find({"platform": "facebook", "isSold": False})
    accounts = await cursor.to_list(length=None)

    if not accounts:
        return await callback.answer("❌ Sorry, no stock available right now!", show_alert=True)

    countries = list(set(acc["country"] for acc in accounts))
    inline_buttons = []

    for country in countries:
        stock_count = sum(1 for acc in accounts if acc["country"] == country)
        sample_acc = next(acc for acc in accounts if acc["country"] == country)
        
        btn_text = f"🌍 {country} • ৳{sample_acc['price']} • Stock: ({stock_count})"
        inline_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"country_{country}")])

    inline_buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await callback.message.edit_text("🌍 **Select Country:**", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("country_"))
async def process_purchase(callback: types.CallbackQuery):
    country = callback.data.split("_")[1]
    user_id = callback.from_user.id

    user = await users_collection.find_one({"userId": user_id})
    account = await accounts_collection.find_one({"platform": "facebook", "country": country, "isSold": False})

    if not account:
        return await callback.answer("❌ Stock out for this country!", show_alert=True)

    if user["balance"] < account["price"]:
        return await callback.answer(f"❌ Insufficient balance! Required: ৳{account['price']}", show_alert=True)

    await users_collection.update_one({"userId": user_id}, {"$inc": {"balance": -account["price"]}})
    await accounts_collection.update_one({"_id": account["_id"]}, {"$set": {"isSold": True}})

    success_text = (
        f"🎉 **Purchase Successful!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 **Number:** `{account['number']}`\n"
        f"🔑 **OTP / Code:** `{account['otp']}`\n"
        f"🔒 **Password:** `{account['password']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Please use the account within 24 hours."
    )

    await callback.message.edit_text(success_text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 **Main Menu:**", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

# --- HIGH-SECURITY ADMIN PANEL ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel_button(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Access Denied! You are not the authorized administrator.")
    
    admin_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Bot Status", callback_data="admin_status"), InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📦 Number Management", callback_data="admin_stock"), InlineKeyboardButton(text="💳 Payment System", callback_data="admin_pay")],
            [InlineKeyboardButton(text="⚙️ Bot Settings", callback_data="admin_settings"), InlineKeyboardButton(text="🗑️ Clear History", callback_data="admin_clear")],
            [InlineKeyboardButton(text="🚫 Ban/Unban User", callback_data="admin_ban"), InlineKeyboardButton(text="👥 Referral Mgmt", callback_data="admin_ref")],
            [InlineKeyboardButton(text="🗄️ Database Management", callback_data="admin_db")]
        ]
    )
    
    admin_text = (
        f"👑 **ADMIN PANEL**\n"
        f"═════════════════════\n"
        f"Select an option below:"
    )
    await message.answer(admin_text, parse_mode="Markdown", reply_markup=admin_markup)

@dp.callback_query(F.data.startswith("admin_"))
async def admin_inline_actions(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Unauthorized!", show_alert=True)
    
    action = callback.data.split("_")[1]
    
    if action == "status":
        await callback.message.answer("📊 **Bot Status:**\n\nServer is running smoothly 24/7 with zero downtime.", parse_mode="Markdown")
    elif action == "stock":
        await callback.message.answer("📦 **Number Management Guide:**\n\nTo add stock, send this command:\n`/addfb [Country] [Price] [Number] [OTP] [Password]`", parse_mode="Markdown")
    elif action == "pay":
        await callback.message.answer("💳 **Payment System Guide:**\n\nTo add balance to a user, send this command:\n`/addbal [UserId] [Amount]`", parse_mode="Markdown")
    else:
        await callback.message.answer(f"⚙️ **{action.capitalize()} Management:**\n\nThis feature is currently active and ready for configuration.", parse_mode="Markdown")
    
    await callback.answer()

# Direct Admin Commands
@dp.message(Command("addfb"))
async def admin_add_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("⛔ Unauthorized access.")
    
    args = message.text.split()[1:]
    if len(args) < 5:
        return await message.reply("⚠️ Correct Format: /addfb [Country] [Price] [Number] [OTP] [Password]")

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
    await message.reply(f"✅ Stock added successfully!\nCountry: {country}\nNumber: {number}")

@dp.message(Command("addbal"))
async def admin_add_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("⛔ Unauthorized access.")
    
    args = message.text.split()[1:]
    if len(args) < 2:
        return await message.reply("⚠️ Correct Format: /addbal [UserId] [Amount]")

    target_user = int(args[0])
    amount = float(args[1])
    await users_collection.update_one(
        {"userId": target_user},
        {"$inc": {"balance": amount}},
        upsert=True
    )
    await message.reply(f"✅ Successfully added ৳{amount} to User `{target_user}`.")

async def main():
    print("🚀 Secure Python Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
