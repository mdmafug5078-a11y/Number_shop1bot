import os
import asyncio
import pandas as pd
from flask import Flask
import threading
from bson import ObjectId
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
SUPPORT_USERNAME = "@mh_mafug" # সাপোর্টের ইউজারনেম

# ডিপোজিট নাম্বার কনফিগারেশন
BKASH_NUMBER = "01712345678"
NAGAD_NUMBER = "01812345678"
MIN_DEPOSIT = 50.0

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

client = AsyncIOMotorClient(MONGO_URI)
db = client["otp_shop_bot"]
users_collection = db["users"]
accounts_collection = db["accounts"]
channels_collection = db["channels"]
deposits_collection = db["deposits"]

# --- FSM States ---
class AddStockState(StatesGroup):
    waiting_for_country = State()
    waiting_for_file = State()
    waiting_for_price = State()

class UserInfoState(StatesGroup):
    waiting_for_uid = State()

class BalanceActionState(StatesGroup):
    waiting_for_amount = State()

class DepositState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_trxid = State()

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

# --- Force Subscription & Ban Check ---
async def check_user_access(user_id: int):
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return False, "banned"

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
    
    allowed, data = await check_user_access(user_id)
    if not allowed:
        if data == "banned":
            return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")
        
        inline_buttons = [[InlineKeyboardButton(text=f"Join {ch['name']}", url=ch['invite_link'])] for ch in data]
        inline_buttons.append([InlineKeyboardButton(text="Joined, Check Again", callback_data="check_subscription")])
        return await message.answer("You must join our official channels to use this bot.", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons))

    user = await users_collection.find_one({"userId": user_id})
    if not user:
        await users_collection.insert_one({"userId": user_id, "balance": 0.0, "isBanned": False, "boughtCount": 0})
        user = {"balance": 0.0}

    caption = (
        f"Welcome to Number Shop, EARN WITH MAFUG!\n\n"
        f"Your Balance: ৳{user.get('balance', 0.0)}\n"
        f"User ID: `{user_id}`\n\n"
        f"Instant automated accounts & OTP delivery.\n"
        f"Start shopping today!"
    )
    await message.answer(caption, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.callback_query(F.data == "check_subscription")
async def process_check_sub(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    allowed, _ = await check_user_access(user_id)
    if allowed:
        await callback.message.delete()
        user = await users_collection.find_one({"userId": user_id})
        if not user:
            await users_collection.insert_one({"userId": user_id, "balance": 0.0, "isBanned": False, "boughtCount": 0})
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
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")
    
    balance = user['balance'] if user else 0.0
    text = f"Account Information:\n\nName: {message.from_user.full_name}\nUser ID: `{user_id}`\nBalance: ৳{balance}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# --- Manual Deposit Flow ---
@dp.message(F.text == "Add Balance")
async def add_balance_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")
    
    await state.set_state(DepositState.waiting_for_amount)
    await message.answer(
        f"Deposit System\n\n"
        f"Minimum Deposit: {MIN_DEPOSIT} BDT\n\n"
        f"Please enter the amount you want to deposit (e.g., 100):",
        parse_mode="Markdown"
    )

@dp.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")

    try:
        amount = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid amount! Please enter a valid number.")

    if amount < MIN_DEPOSIT:
        return await message.reply(f"Minimum deposit amount is {MIN_DEPOSIT} BDT. Please enter a higher amount:")

    await state.update_data(deposit_amount=amount)
    await state.set_state(DepositState.waiting_for_trxid)

    text = (
        f"Deposit Amount: {amount} BDT\n\n"
        f"Please Send Money to our numbers below:\n\n"
        f"bKash (Personal): `{BKASH_NUMBER}`\n"
        f"Nagad (Personal): `{NAGAD_NUMBER}`\n\n"
        f"Note: You must use 'Send Money' option.\n\n"
        f"After sending money, please reply with your Transaction ID (TrxID):"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(DepositState.waiting_for_trxid)
async def process_deposit_trxid(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")

    trxid = message.text.strip()
    data = await state.get_data()
    amount = data.get("deposit_amount")
    user_full_name = message.from_user.full_name

    await state.clear()

    deposit_doc = {
        "userId": user_id,
        "amount": amount,
        "trxid": trxid,
        "status": "pending"
    }
    result = await deposits_collection.insert_one(deposit_doc)
    deposit_id = str(result.inserted_id)

    await message.reply("Your deposit request has been submitted successfully! Please wait for admin approval.")

    admin_text = (
        f"New Deposit Request!\n\n"
        f"User: {user_full_name} (`{user_id}`)\n"
        f"Amount: {amount} BDT\n"
        f"TrxID: `{trxid}`"
    )
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Approve", callback_data=f"dep_approve_{deposit_id}"),
            InlineKeyboardButton(text="Reject", callback_data=f"dep_reject_{deposit_id}")
        ]
    ])
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup)
    except Exception as e:
        print(f"Failed to send deposit notification to admin: {e}")

# Admin Deposit Approve / Reject Action
@dp.callback_query(F.data.startswith("dep_approve_") | F.data.startswith("dep_reject_"))
async def handle_deposit_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
    
    action, deposit_id = callback.data.split("_")[1], callback.data.split("_")[2]
    deposit = await deposits_collection.find_one({"_id": ObjectId(deposit_id)})
    
    if not deposit:
        return await callback.answer("Deposit request not found!", show_alert=True)
    
    if deposit["status"] != "pending":
        return await callback.answer(f"This request is already {deposit['status']}!", show_alert=True)
    
    target_uid = deposit["userId"]
    amount = deposit["amount"]
    
    if action == "approve":
        await deposits_collection.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "approved"}})
        await users_collection.update_one({"userId": target_uid}, {"$inc": {"balance": amount}}, upsert=True)
        
        await callback.message.edit_text(callback.message.text + f"\n\nStatus: Approved (Added ৳{amount})", parse_mode="Markdown")
        await callback.answer("Deposit approved successfully!")
        
        try:
            await bot.send_message(target_uid, f"Your deposit of ৳{amount} has been approved and added to your balance!")
        except Exception:
            pass
    else:
        await deposits_collection.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "rejected"}})
        await callback.message.edit_text(callback.message.text + f"\n\nStatus: Rejected", parse_mode="Markdown")
        await callback.answer("Deposit rejected!")
        
        try:
            await bot.send_message(target_uid, f"Your deposit request of ৳{amount} has been rejected by admin.")
        except Exception:
            pass

@dp.message(F.text == "Support")
async def support_handler(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")
        
    await message.answer(f"Customer Support:\n👉 {SUPPORT_USERNAME}", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text.in_(["My Referral", "How to Work"]))
async def general_features(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")
        
    await message.answer(f"{message.text} feature is coming soon!", parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

# --- Buy Number Menu ---
@dp.message(F.text == "Buy Number")
async def buy_menu(message: types.Message):
    user_id = message.from_user.id
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {SUPPORT_USERNAME}")

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

    await users_collection.update_one({"userId": user_id}, {"$inc": {"balance": -account["price"], "boughtCount": 1}})
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

# --- ADMIN PANEL & USER INFO / MANAGEMENT ---
@dp.message(F.text == "Admin Panel")
async def admin_panel_button(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Access Denied!")
    
    admin_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="User Info", callback_data="admin_user_info")],
            [InlineKeyboardButton(text="Number Management", callback_data="admin_stock")],
            [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="Payment System", callback_data="admin_pay")],
            [InlineKeyboardButton(text="Bot Status", callback_data="admin_status")]
        ]
    )
    await message.answer("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)

# --- User Info Flow ---
@dp.callback_query(F.data == "admin_user_info")
async def prompt_user_info(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(UserInfoState.waiting_for_uid)
    await callback.message.answer("Please enter the Telegram User ID (UID):", parse_mode="Markdown")
    await callback.answer()

@dp.message(UserInfoState.waiting_for_uid)
async def show_user_details(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_uid = int(message.text.strip())
    except ValueError:
        return await message.reply("Invalid User ID! Please enter a valid number.")

    await state.clear()
    target_user = await users_collection.find_one({"userId": target_uid})
    if not target_user:
        return await message.reply(f"User with ID `{target_uid}` not found in database.", parse_mode="Markdown")

    balance = target_user.get("balance", 0.0)
    bought = target_user.get("boughtCount", 0)
    is_banned = target_user.get("isBanned", False)
    status = "Banned" if is_banned else "Active"
    block_btn_text = "Unban" if is_banned else "Block"

    text = (
        f"User Details\n\n"
        f"User ID: `{target_uid}`\n"
        f"Balance: {balance} BDT\n"
        f"Accounts Bought: {bought}\n"
        f"Status: {status}"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=block_btn_text, callback_data=f"u_block_{target_uid}")],
        [InlineKeyboardButton(text="Balance Add", callback_data=f"u_baladd_{target_uid}"), InlineKeyboardButton(text="Balance Remove", callback_data=f"u_balrem_{target_uid}")],
        [InlineKeyboardButton(text="Back", callback_data="admin_stock")]
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data.startswith("u_block_"))
async def toggle_user_ban(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    target_uid = int(callback.data.replace("u_block_", ""))
    target_user = await users_collection.find_one({"userId": target_uid})
    
    current_status = target_user.get("isBanned", False)
    new_status = not current_status
    
    await users_collection.update_one({"userId": target_uid}, {"$set": {"isBanned": new_status}})
    
    status_str = "Banned" if new_status else "Active"
    block_btn_text = "Unban" if new_status else "Block"
    
    balance = target_user.get("balance", 0.0)
    bought = target_user.get("boughtCount", 0)

    text = (
        f"User Details\n\n"
        f"User ID: `{target_uid}`\n"
        f"Balance: {balance} BDT\n"
        f"Accounts Bought: {bought}\n"
        f"Status: {status_str}"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=block_btn_text, callback_data=f"u_block_{target_uid}")],
        [InlineKeyboardButton(text="Balance Add", callback_data=f"u_baladd_{target_uid}"), InlineKeyboardButton(text="Balance Remove", callback_data=f"u_balrem_{target_uid}")],
        [InlineKeyboardButton(text="Back", callback_data="admin_stock")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await callback.answer(f"User status updated to {status_str}!", show_alert=True)

@dp.callback_query(F.data.startswith("u_baladd_") | F.data.startswith("u_balrem_"))
async def prompt_balance_action(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    action_type, target_uid = callback.data.split("_")[1], int(callback.data.split("_")[2])
    await state.update_data(target_uid=target_uid, action_type=action_type)
    await state.set_state(BalanceActionState.waiting_for_amount)
    
    action_name = "Add" if action_type == "baladd" else "Remove"
    await callback.message.answer(f"Enter the amount to {action_name} for user `{target_uid}` (e.g. 10):", parse_mode="Markdown")
    await callback.answer()

@dp.message(BalanceActionState.waiting_for_amount)
async def process_balance_action(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid amount! Please enter a number.")

    data = await state.get_data()
    target_uid = data.get("target_uid")
    action_type = data.get("action_type")
    await state.clear()

    multiplier = 1 if action_type == "baladd" else -1
    await users_collection.update_one({"userId": target_uid}, {"$inc": {"balance": amount * multiplier}}, upsert=True)
    
    updated_user = await users_collection.find_one({"userId": target_uid})
    new_bal = updated_user.get("balance", 0.0)
    
    action_text = "added to" if action_type == "baladd" else "removed from"
    await message.reply(f"Successfully {action_text} user `{target_uid}`. New balance: ৳{new_bal}", parse_mode="Markdown")

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
            
            if message.document.file_name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(downloaded_file, header=None)
                for _, row in df.iterrows():
                    if len(row) >= 3 and pd.notna(row[0]) and pd.notna(row[1]) and pd.notna(row[2]):
                        parsed_items.append({
                            "number": str(row[0]).strip(),
                            "otp": str(row[1]).strip(),
                            "password": str(row[2]).strip()
                        })
            else:
                text_content = downloaded_file.read().decode("utf-8")
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

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="User Info", callback_data="admin_user_info")],
        [InlineKeyboardButton(text="Number Management", callback_data="admin_stock")],
        [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="Payment System", callback_data="admin_pay")],
        [InlineKeyboardButton(text="Bot Status", callback_data="admin_status")]
    ])
    await callback.message.edit_text("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)
    await callback.answer()

async def main():
    print("Bot is running with Manual Deposit System...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
