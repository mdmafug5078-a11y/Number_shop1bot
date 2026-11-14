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

@dp.message(Deposit
