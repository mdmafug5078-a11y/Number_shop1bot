import os
import asyncio
import pandas as pd
from flask import Flask
import threading
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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
NOTIFICATION_CHANNEL = "@QuickTaskPay"  # যে চ্যানেলে স্টক অ্যাড হলে নোটিফিকেশন যাবে

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

client = AsyncIOMotorClient(MONGO_URI)
db = client["otp_shop_bot"]
users_collection = db["users"]
accounts_collection = db["accounts"]
channels_collection = db["channels"]

# --- FSM States ---
class AddStockState(StatesGroup):
    waiting_for_country = State()
    waiting_for_file = State()
    waiting_for_price = State()

class UpdatePriceState(StatesGroup):
    waiting_for_new_price = State()

# --- Main Menu Keyboard ---
def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="Profile"), KeyboardButton(text="Buy Number")],
        [KeyboardButton(text="Add Balance"), KeyboardButton(text="Support")],
        [KeyboardButton(text="My Referral"), KeyboardButton(text="How to Work")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- Force Subscription Check ---
async def check_user_subscriptions(user_id: int):
    if user_id == ADMIN_ID:
        return True, []
    cursor = channels_collection.find({})
    channels = await cursor.to_list(length=None)
    if not channels:
        return True, []
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if member.status not in ["member", "creator", "administrator"]:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    if not_joined:
        return False, not_joined
    return True, []

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_subbed, unjoined = await check_user_subscriptions(user_id)
    
    if not is_subbed:
        inline_buttons = [[InlineKeyboardButton(text=f"Join {ch['name']}", url=ch['invite_link'])] for ch in unjoined]
        inline_buttons.append([InlineKeyboardButton(text="Joined, Check Again", callback_data="check_subscription")])
        await message.answer("You must join our official channels to use this bot.", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons))
        return

    user = await users_collection.find_one({"userId": user_id})
    if not user:
        await users_collection.insert_one({"userId": user_id, "balance": 0.0})
        user = {"balance": 0.0}

    caption = (
        f"Welcome to Number Shop, EARN WITH MAFUG!\n\n"
        f"Your Balance: ৳{user['balance']}\n"
        f"User ID: `{user_id}`\n\n"
        f"Instant automated accounts & OTP delivery.\n"
        f"Start shopping today!"
    )
    await message.answer(caption, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.callback_query(F.data == "check_subscription")
async def process_check_sub(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subbed, _ = await check_user_subscriptions(user_id)
    if is_subbed:
        await callback.message.delete()
        user = await users_collection.find_one({"userId": user_id})
        if not user:
            await users_collection.insert_one({"userId": user_id, "balance": 0.0})
            user = {"balance": 0.0}
        caption = f"Welcome back!\nYour Balance: ৳{user.get('balance', 0.0)}"
        await callback.message.answer(caption, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))
    else:
        await callback.answer("You haven't joined all required channels yet!", show_alert=True)

# --- User Menus ---
@dp.message(F.text == "Profile")
async def profile_handler(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    balance = user['balance'] if user else 0.0
    text = f"Account Information:\n\nName: {message.from_user.full_name}\nUser ID: `{user_id}`\nBalance: ৳{balance}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "Add Balance")
async def add_balance_info(message: types.Message):
    await message.answer("How to Add Balance:\nContact the admin to top up your balance.\nAdmin: @mh_mafug", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "Support")
async def support_handler(message: types.Message):
    await message.answer("Customer Support:\n👉 @QuickTaskPay", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text.in_(["My Referral", "How to Work"]))
async def general_features(message: types.Message):
    await message.answer(f"{message.text} feature is coming soon!", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

# --- Buy Number Menu ---
@dp.message(F.text == "Buy Number")
async def buy_menu(message: types.Message):
    cursor = accounts_collection.find({"isSold": False})
    accounts = await cursor.to_list(length=None)
    if not accounts:
        return await message.answer("Sorry, no stock available right now!")

    countries = list(set(acc["country"] for acc in accounts))
    inline_buttons = []
    for country in countries:
        count = sum(1 for acc in accounts if acc["country"] == country)
        sample = next(acc for acc in accounts if acc["country"] == country)
        inline_buttons.append([InlineKeyboardButton(text=f"{country} • ৳{sample['price']} • Stock: ({count})", callback_data=f"buy_country_{country}")])
    
    inline_buttons.append([InlineKeyboardButton(text="Main Menu", callback_data="back_to_menu")])
    await message.answer("Select Country to Buy:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons))

@dp.callback_query(F.data.startswith("buy_country_"))
async def process_purchase(callback: types.CallbackQuery):
    country = callback.data.replace("buy_country_", "")
    user_id = callback.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    account = await accounts_collection.find_one({"country": country, "isSold": False})

    if not account:
        return await callback.answer("Stock out for this country!", show_alert=True)
    if user["balance"] < account["price"]:
        return await callback.answer(f"Insufficient balance! Required: ৳{account['price']}", show_alert=True)

    await users_collection.update_one({"userId": user_id}, {"$inc": {"balance": -account["price"]}})
    await accounts_collection.update_one({"_id": account["_id"]}, {"$set": {"isSold": True}})

    success_text = (
        f"Purchase Successful!\n\n"
        f"-----------------------------------------\n"
        f"Number: `{account['number']}`\n"
        f"OTP / Code: `{account['otp']}`\n"
        f"Password: `{account['password']}`\n"
        f"-----------------------------------------\n"
        f"Please use the account within 24 hours."
    )
    await callback.message.edit_text(success_text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Main Menu:", parse_mode="Markdown", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

# --- ADMIN PANEL & NUMBER MANAGEMENT ---
@dp.message(F.text == "Admin Panel")
async def admin_panel_button(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Access Denied!")
    
    admin_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Number Management", callback_data="admin_stock")],
            [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="Payment System", callback_data="admin_pay")],
            [InlineKeyboardButton(text="Bot Status", callback_data="admin_status")]
        ]
    )
    await message.answer("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)

@dp.callback_query(F.data == "admin_stock")
async def admin_number_management(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
    
    cursor = accounts_collection.find({})
    accounts = await cursor.to_list(length=None)
    
    countries = list(set(acc["country"] for acc in accounts))
    inline_buttons = []
    
    for country in countries:
        total = sum(1 for acc in accounts if acc["country"] == country)
        sold = sum(1 for acc in accounts if acc["country"] == country and acc["isSold"] == True)
        inline_buttons.append([InlineKeyboardButton(text=f"{country} [Total: {total}, Sold: {sold}]", callback_data=f"manage_country_{country}")])
        
    inline_buttons.append([InlineKeyboardButton(text="Add New Country Stock", callback_data="add_stock_start")])
    inline_buttons.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_back")])
    
    await callback.message.edit_text("Number Management\nSelect a country to manage or add new stock:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons))
    await callback.answer()

# --- Interactive Add Stock Flow (.xlsx & .txt Supported) ---
@dp.callback_query(F.data == "add_stock_start")
async def start_add_stock(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AddStockState.waiting_for_country)
    await callback.message.answer("Please enter the Country Name (e.g., Bangladesh / Italy):", parse_mode="Markdown")
    await callback.answer()

@dp.message(AddStockState.waiting_for_country)
async def process_country_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(country=message.text.strip())
    await state.set_state(AddStockState.waiting_for_file)
    await message.answer("Now send the Excel file (.xlsx) or text file (.txt) containing numbers, OTP, and passwords.", parse_mode="Markdown")

@dp.message(AddStockState.waiting_for_file)
async def process_stock_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    parsed_items = []
    try:
        if message.document:
            file = await bot.get_file(message.document.file_id)
            file_path = file.file_path
            downloaded_file = await bot.download_file(file_path)
            
            # Check if file is .xlsx or .xls
            if message.document.file_name.endswith(('.xlsx', '.xls')):
                temp_filename = f"temp_{message.from_user.id}.xlsx"
                with open(temp_filename, "wb") as f:
                    f.write(downloaded_file)
                
                df = pd.read_excel(temp_filename, header=None)
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                
                for _, row in df.iterrows():
                    if len(row) >= 3 and pd.notna(row[0]) and pd.notna(row[1]) and pd.notna(row[2]):
                        parsed_items.append({
                            "number": str(row[0]).strip(),
                            "otp": str(row[1]).strip(),
                            "password": str(row[2]).strip()
                        })
            else:
                # Text file handling
                text_content = downloaded_file.decode("utf-8")
                lines = text_content.strip().split("\n")
                for line in lines:
                    parts = line.replace(",", "\t").split()
                    if len(parts) >= 3:
                        parsed_items.append({"number": parts[0], "otp": parts[1], "password": parts[2]})
        elif message.text:
            lines = message.text.strip().split("\n")
            for line in lines:
                parts = line.replace(",", "\t").split()
                if len(parts) >= 3:
                    parsed_items.append({"number": parts[0], "otp": parts[1], "password": parts[2]})
    except Exception as e:
        return await message.reply(f"Error reading file: {e}")

    if not parsed_items:
        return await message.reply("Invalid format or empty file! Please send a valid Excel or text file.")

    await state.update_data(items=parsed_items)
    await state.set_state(AddStockState.waiting_for_price)
    await message.reply(f"Successfully read `{len(parsed_items)}` numbers.\nNow enter the Price per Number in BDT (e.g., 0.80 or 1.00):", parse_mode="Markdown")

@dp.message(AddStockState.waiting_for_price)
async def process_stock_price(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid price! Please enter a number.")

    data = await state.get_data()
    country = data.get("country")
    items = data.get("items")

    db_docs = []
    for item in items:
        db_docs.append({
            "platform": "facebook",
            "country": country,
            "price": price,
            "number": item["number"],
            "otp": item["otp"],
            "password": item["password"],
            "isSold": False
        })

    await accounts_collection.insert_many(db_docs)
    await state.clear()

    await message.reply(f"Added `{len(db_docs)}` numbers for **{country}** at **৳{price}** each!", parse_mode="Markdown")

    # Send Notification to Channel with 'Buy Number' Button
    try:
        notification_text = (
            f"<b>{country}</b>\n"
            f"TOTALL : {len(db_docs)} Numbers\n"
            f"OTP Rate: {price:.2f} BDT"
        )
        channel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Buy Number", url=f"https://t.me/{(await bot.get_me()).username}")]
        ])
        await bot.send_message(NOTIFICATION_CHANNEL, notification_text, parse_mode="HTML", reply_markup=channel_keyboard)
    except Exception as e:
        print(f"Notification error: {e}")

# --- Country Management (Stock Add, Price Change, Delete) ---
@dp.callback_query(F.data.startswith("manage_country_"))
async def manage_single_country(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
    
    country = callback.data.replace("manage_country_", "")
    total = await accounts_collection.count_documents({"country": country})
    sold = await accounts_collection.count_documents({"country": country, "isSold": True})
    available = await accounts_collection.count_documents({"country": country, "isSold": False})
    
    sample = await accounts_collection.find_one({"country": country})
    price = sample["price"] if sample else 0.0

    text = (
        f"Country: {country}\n"
        f"Current Price: ৳{price}\n"
        f"Total Stock: {total}\n"
        f"Available: {available}\n"
        f"Sold: {sold}"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Stock Add", callback_data=f"m_add_{country}"), InlineKeyboardButton(text="Price Change", callback_data=f"m_price_{country}")],
        [InlineKeyboardButton(text="Delete Number", callback_data=f"m_del_{country}")],
        [InlineKeyboardButton(text="Back to List", callback_data="admin_stock")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data.startswith("m_price_"))
async def prompt_change_price(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    country = callback.data.replace("m_price_", "")
    await state.update_data(target_country=country)
    await state.set_state(UpdatePriceState.waiting_for_new_price)
    await callback.message.answer(f"Enter new price for **{country}**:", parse_mode="Markdown")
    await callback.answer()

@dp.message(UpdatePriceState.waiting_for_new_price)
async def apply_new_price(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid price!")

    data = await state.get_data()
    country = data.get("target_country")
    await accounts_collection.update_many({"country": country}, {"$set": {"price": new_price}})
    await state.clear()
    await message.reply(f"Price updated to ৳{new_price} for all **{country}** accounts!", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("m_del_"))
async def confirm_delete_country(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    country = callback.data.replace("m_del_", "")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes, Delete All", callback_data=f"confirm_del_{country}")],
        [InlineKeyboardButton(text="Cancel", callback_data=f"manage_country_{country}")]
    ])
    await callback.message.edit_text(f"Are you sure you want to delete all unsold stock for **{country}**?", parse_mode="Markdown", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_del_"))
async def execute_delete_country(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    country = callback.data.replace("confirm_del_", "")
    await accounts_collection.delete_many({"country": country, "isSold": False})
    await callback.message.edit_text(f"Unsold stock for **{country}** has been removed successfully!", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Number Management", callback_data="admin_stock")],
        [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="Payment System", callback_data="admin_pay")],
        [InlineKeyboardButton(text="Bot Status", callback_data="admin_status")]
    ])
    await callback.message.edit_text("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)
    await callback.answer()

async def main():
    print("Bot is running smoothly...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
