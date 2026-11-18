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
NOTIFICATION_CHANNEL = "@QuickTaskPay"  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

client = AsyncIOMotorClient(MONGO_URI)
db = client["otp_shop_bot"]
users_collection = db["users"]
accounts_collection = db["accounts"]
channels_collection = db["channels"]
deposits_collection = db["deposits"]
settings_collection = db["settings"] 

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

class PaymentSettingsState(StatesGroup):
    waiting_for_bkash = State()
    waiting_for_nagad = State()
    waiting_for_min_deposit = State()
    waiting_for_support = State()
    waiting_for_how_to_work = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class UpdatePriceState(StatesGroup):
    waiting_for_new_price = State()

class AddChannelState(StatesGroup):
    waiting_for_name = State()
    waiting_for_link = State()

# --- Helper Functions for Settings ---
async def get_bot_settings():
    settings = await settings_collection.find_one({"type": "payment_numbers"})
    if not settings:
        default_settings = {
            "type": "payment_numbers", 
            "bkash": "01610184434", 
            "nagad": "01610184434",
            "min_deposit": 20.0,
            "support": "@mh_mafug",
            "how_to_work": "How to work video/link is not set by admin yet."
        }
        await settings_collection.insert_one(default_settings)
        return default_settings
    return settings

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
    user_full_name = message.from_user.full_name
    
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")

    allowed, data = await check_user_access(user_id)
    if not allowed:
        if data == "banned":
            return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
        
        inline_buttons = [[InlineKeyboardButton(text=f"Join {ch['name']}", url=ch['invite_link'])] for ch in data]
        inline_buttons.append([InlineKeyboardButton(text="Joined, Check Again", callback_data="check_subscription")])
        return await message.answer("You must join our official channels to use this bot.", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_buttons))

    user = await users_collection.find_one({"userId": user_id})
    if not user:
        await users_collection.insert_one({"userId": user_id, "balance": 0.0, "isBanned": False, "boughtCount": 0})
        user = {"balance": 0.0}

    caption = (
        f"Welcome to Number Shop, {user_full_name}!\n\n"
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
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
    
    balance = user['balance'] if user else 0.0
    text = f"Account Information:\n\nName: {message.from_user.full_name}\nUser ID: `{user_id}`\nBalance: ৳{balance}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "Support")
async def support_handler(message: types.Message):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
        
    await message.answer(f"Customer Support:\n👉 {support_user}", parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "How to Work")
async def how_to_work_handler(message: types.Message):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
        
    how_to_work_content = settings.get("how_to_work", "How to work details coming soon.")
    await message.answer(how_to_work_content, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "My Referral")
async def referral_handler(message: types.Message):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
        
    await message.answer("My Referral feature is coming soon!", parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# --- Manual Deposit Flow ---
@dp.message(F.text == "Add Balance")
async def add_balance_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")
    
    await state.clear()
    min_dep = settings.get("min_deposit", 20.0)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="bKash", callback_data="dep_method_bKash"),
            InlineKeyboardButton(text="Nagad", callback_data="dep_method_Nagad")
        ]
    ])
    await message.answer(
        f"Deposit System\n\n"
        f"Minimum Deposit: {min_dep} BDT\n\n"
        f"Please select your payment method:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@dp.callback_query(F.data.startswith("dep_method_"))
async def select_deposit_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.replace("dep_method_", "")
    settings = await get_bot_settings()
    min_dep = settings.get("min_deposit", 20.0)

    await state.update_data(deposit_method=method)
    await state.set_state(DepositState.waiting_for_amount)

    await callback.message.edit_text(
        f"Selected Method: {method}\n"
        f"Minimum Deposit: {min_dep} BDT\n\n"
        f"Please enter the amount you want to deposit (e.g., 100):",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")

    try:
        amount = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid amount! Please enter a valid number.")

    min_dep = settings.get("min_deposit", 20.0)

    if amount < min_dep:
        return await message.reply(f"Minimum deposit amount is {min_dep} BDT. Please enter a higher amount:")

    data = await state.get_data()
    method = data.get("deposit_method", "bKash")

    await state.update_data(deposit_amount=amount)
    await state.set_state(DepositState.waiting_for_trxid)

    target_number = settings.get("bkash", "01610184434") if method == "bKash" else settings.get("nagad", "01610184434")

    text = (
        f"Method: {method}\n"
        f"Deposit Amount: {amount} BDT\n\n"
        f"Please Send Money to our {method} number below:\n\n"
        f"{method} (Personal): `{target_number}`\n\n"
        f"Note: You must use 'Send Money' option.\n\n"
        f"After sending money, please reply with your Transaction ID (TrxID):"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(DepositState.waiting_for_trxid)
async def process_deposit_trxid(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")

    trxid = message.text.strip()
    data = await state.get_data()
    amount = data.get("deposit_amount")
    method = data.get("deposit_method", "bKash")
    user_full_name = message.from_user.full_name

    await state.clear()

    deposit_doc = {
        "userId": user_id,
        "method": method,
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
        f"Method: {method}\n"
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

# --- Buy Number Menu ---
@dp.message(F.text == "Buy Number")
async def buy_menu(message: types.Message):
    user_id = message.from_user.id
    settings = await get_bot_settings()
    support_user = settings.get("support", "@mh_mafug")
    
    user = await users_collection.find_one({"userId": user_id})
    if user and user.get("isBanned", False):
        return await message.answer(f"You are banned from this bot!\nFor support contact: {support_user}")

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
        f"Please use the account within 1 hour."
    )
    await callback.message.edit_text(success_text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Main Menu:", parse_mode="Markdown", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

# --- ADMIN PANEL & HIGH SECURITY CONTROLS ---
@dp.message(F.text == "Admin Panel")
async def admin_panel_button(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Access Denied!")
    
    admin_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="User Info", callback_data="admin_user_info")],
            [InlineKeyboardButton(text="Number Management", callback_data="admin_stock")],
            [InlineKeyboardButton(text="Payment Numbers Setup", callback_data="admin_pay_settings")],
            [InlineKeyboardButton(text="Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="Bot Status", callback_data="admin_status")]
        ]
    )
    await message.answer("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)

# --- Manage Channels Feature ---
@dp.callback_query(F.data == "admin_channels")
async def admin_channels_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
        
    cursor = channels_collection.find({})
    channels = await cursor.to_list(length=None)
    
    inline_buttons = []
    for ch in channels:
        inline_buttons.append([
            InlineKeyboardButton(text=f"{ch['name']}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_ch_{ch['chat_id']}")
        ])
        
    inline_buttons.append([InlineKeyboardButton(text="Add New Channel", callback_data="add_new_channel")])
    inline_buttons.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await callback.message.edit_text("Manage Force Join Channels", parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "add_new_channel")
async def start_add_channel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AddChannelState.waiting_for_name)
    await callback.message.answer("Please enter the Button Name (e.g., Official Group):")
    await callback.answer()

@dp.message(AddChannelState.waiting_for_name)
async def process_channel_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(channel_name=message.text)
    await state.set_state(AddChannelState.waiting_for_link)
    await message.answer("Please enter the Channel Link or @username (e.g. https://t.me/Channel or @Channel):")

@dp.message(AddChannelState.waiting_for_link)
async def process_channel_link(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    name = data.get("channel_name")
    link = message.text.strip()
    
    if link.startswith("@"):
        chat_id = link
    else:
        chat_id = "@" + link.split("/")[-1] if "t.me/" in link else link

    await channels_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"name": name, "chat_id": chat_id, "invite_link": link}},
        upsert=True
    )
    
    await state.clear()
    await message.reply(f"Successfully added channel:\n<b>{name}</b>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_ch_"))
async def delete_channel_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    chat_id = callback.data.replace("del_ch_", "")
    await channels_collection.delete_one({"chat_id": chat_id})
    await callback.answer("Channel removed successfully!", show_alert=True)
    
    cursor = channels_collection.find({})
    channels = await cursor.to_list(length=None)
    
    inline_buttons = []
    for ch in channels:
        inline_buttons.append([
            InlineKeyboardButton(text=f"{ch['name']}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_ch_{ch['chat_id']}")
        ])
    inline_buttons.append([InlineKeyboardButton(text="Add New Channel", callback_data="add_new_channel")])
    inline_buttons.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await callback.message.edit_reply_markup(reply_markup=keyboard)

@dp.callback_query(F.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

# --- Broadcast Feature ---
@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
    
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.answer("Please send the message, photo, or media you want to broadcast to all members:", parse_mode="Markdown")
    await callback.answer()

@dp.message(BroadcastState.waiting_for_message)
async def execute_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await state.clear()
    status_msg = await message.reply("Broadcast started...")
    
    cursor = users_collection.find({})
    users = await cursor.to_list(length=None)
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        uid = user.get("userId")
        try:
            await message.send_copy(chat_id=uid)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1
            
    await status_msg.edit_text(f"Broadcast Completed!\n\nSuccess: {success_count}\nFailed: {fail_count}")

# --- Payment Numbers & Support Settings Admin ---
@dp.callback_query(F.data == "admin_pay_settings")
async def admin_payment_settings(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
    
    settings = await get_bot_settings()
    
    text = (
        f"Payment & Support Settings\n\n"
        f"bKash Number: `{settings.get('bkash')}`\n"
        f"Nagad Number: `{settings.get('nagad')}`\n"
        f"Minimum Deposit: `{settings.get('min_deposit')} BDT`\n"
        f"Support Username: `{settings.get('support')}`\n\n"
        f"Manage below:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Change bKash", callback_data="set_bkash"), InlineKeyboardButton(text="Change Nagad", callback_data="set_nagad")],
        [InlineKeyboardButton(text="Minimum Deposit", callback_data="set_mindep"), InlineKeyboardButton(text="Support Username", callback_data="set_support")],
        [InlineKeyboardButton(text="How to Work Setup", callback_data="set_howtowork")],
        [InlineKeyboardButton(text="Pending Deposits", callback_data="admin_pending_deps")],
        [InlineKeyboardButton(text="Back", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data == "admin_pending_deps")
async def show_pending_deposits(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Unauthorized!", show_alert=True)
        
    cursor = deposits_collection.find({"status": "pending"})
    pending_list = await cursor.to_list(length=None)
    
    if not pending_list:
        return await callback.answer("No pending deposit requests found!", show_alert=True)
        
    await callback.message.delete()
    for dep in pending_list:
        dep_id = str(dep["_id"])
        method = dep.get("method", "Unknown")
        text = (
            f"Pending Deposit\n\n"
            f"User ID: `{dep['userId']}`\n"
            f"Method: {method}\n"
            f"Amount: {dep['amount']} BDT\n"
            f"TrxID: `{dep['trxid']}`"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"dep_approve_{dep_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"dep_reject_{dep_id}")
            ]
        ])
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data == "set_bkash")
async def prompt_set_bkash(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(PaymentSettingsState.waiting_for_bkash)
    await callback.message.answer("Please send the new bKash personal number:", parse_mode="Markdown")
    await callback.answer()

@dp.message(PaymentSettingsState.waiting_for_bkash)
async def save_bkash_number(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_bkash = message.text.strip()
    settings = await get_bot_settings()
    
    await settings_collection.update_one(
        {"type": "payment_numbers"},
        {"$set": {
            "bkash": new_bkash, 
            "nagad": settings.get("nagad"), 
            "min_deposit": settings.get("min_deposit"),
            "support": settings.get("support"),
            "how_to_work": settings.get("how_to_work")
        }},
        upsert=True
    )
    await state.clear()
    await message.reply(f"Successfully updated bKash number to: `{new_bkash}`", parse_mode="Markdown")

@dp.callback_query(F.data == "set_nagad")
async def prompt_set_nagad(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(PaymentSettingsState.waiting_for_nagad)
    await callback.message.answer("Please send the new Nagad personal number:", parse_mode="Markdown")
    await callback.answer()

@dp.message(PaymentSettingsState.waiting_for_nagad)
async def save_nagad_number(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_nagad = message.text.strip()
    settings = await get_bot_settings()
    
    await settings_collection.update_one(
        {"type": "payment_numbers"},
        {"$set": {
            "bkash": settings.get("bkash"), 
            "nagad": new_nagad, 
            "min_deposit": settings.get("min_deposit"),
            "support": settings.get("support"),
            "how_to_work": settings.get("how_to_work")
        }},
        upsert=True
    )
    await state.clear()
    await message.reply(f"Successfully updated Nagad number to: `{new_nagad}`", parse_mode="Markdown")

@dp.callback_query(F.data == "set_mindep")
async def prompt_set_mindep(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(PaymentSettingsState.waiting_for_min_deposit)
    await callback.message.answer("Please enter the new Minimum Deposit amount (e.g. 20):", parse_mode="Markdown")
    await callback.answer()

@dp.message(PaymentSettingsState.waiting_for_min_deposit)
async def save_min_deposit(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_min = float(message.text.strip())
    except ValueError:
        return await message.reply("Invalid amount!")
        
    settings = await get_bot_settings()
    await settings_collection.update_one(
        {"type": "payment_numbers"},
        {"$set": {
            "bkash": settings.get("bkash"), 
            "nagad": settings.get("nagad"), 
            "min_deposit": new_min,
            "support": settings.get("support"),
            "how_to_work": settings.get("how_to_work")
        }},
        upsert=True
    )
    await state.clear()
    await message.reply(f"Successfully updated Minimum Deposit to: `৳{new_min}`", parse_mode="Markdown")

@dp.callback_query(F.data == "set_support")
async def prompt_set_support(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(PaymentSettingsState.waiting_for_support)
    await callback.message.answer("Please enter the new Support Username (e.g. @mh_mafug):", parse_mode="Markdown")
    await callback.answer()

@dp.message(PaymentSettingsState.waiting_for_support)
async def save_support_username(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_support = message.text.strip()
    if not new_support.startswith("@"):
        new_support = "@" + new_support
        
    settings = await get_bot_settings()
    await settings_collection.update_one(
        {"type": "payment_numbers"},
        {"$set": {
            "bkash": settings.get("bkash"), 
            "nagad": settings.get("nagad"), 
            "min_deposit": settings.get("min_deposit"),
            "support": new_support,
            "how_to_work": settings.get("how_to_work")
        }},
        upsert=True
    )
    await state.clear()
    await message.reply(f"Successfully updated Support Username to: `{new_support}`", parse_mode="Markdown")

@dp.callback_query(F.data == "set_howtowork")
async def prompt_set_howtowork(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(PaymentSettingsState.waiting_for_how_to_work)
    await callback.message.answer("Please send the 'How to Work' text, video link, or instructions:", parse_mode="Markdown")
    await callback.answer()

@dp.message(PaymentSettingsState.waiting_for_how_to_work)
async def save_how_to_work(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_content = message.text.strip()
    settings = await get_bot_settings()
    
    await settings_collection.update_one(
        {"type": "payment_numbers"},
        {"$set": {
            "bkash": settings.get("bkash"), 
            "nagad": settings.get("nagad"), 
            "min_deposit": settings.get("min_deposit"),
            "support": settings.get("support"),
            "how_to_work": new_content
        }},
        upsert=True
    )
    await state.clear()
    await message.reply("Successfully updated 'How to Work' content!", parse_mode="Markdown")

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

# --- Number Management ---
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
        [InlineKeyboardButton(text="Payment Numbers Setup", callback_data="admin_pay_settings")],
        [InlineKeyboardButton(text="Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="Manage Channels", callback_data="admin_channels"), InlineKeyboardButton(text="BotStatus", callback_data="admin_status")]
    ])
    await callback.message.edit_text("ADMIN PANEL\n-----------------------------------------", parse_mode="Markdown", reply_markup=admin_markup)
    await callback.answer()

async def main():
    print("Secure Bot is running smoothly...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
