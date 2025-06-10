import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from config import get_config
import sys
from keyboards import Keyboards
from utils import format_currency, get_damascus_time
from log_manager import get_log_manager

# Initialize components
config = get_config()
log_manager = get_log_manager()

# States
(
    ADMIN_BAN_USER,
    ADMIN_UNBAN_USER,
    ADMIN_MODIFY_BALANCE,
    WAITING_FOR_AMOUNT,
    WAITING_FOR_PAYMENT_PROOF,
    WAITING_FOR_TXID,
    WAITING_FOR_RATE,
    WAITING_FOR_GAME_ID,
    WAITING_FOR_USER_INPUT,
    WAITING_FOR_EMAIL,
    WAITING_FOR_OPERATION_ID,
    WAITING_FOR_PRICE_UPDATE,
    WAITING_FOR_REJECT_REASON,
    WAITING_FOR_PRODUCT_INFO,
    EDITING_ENV_VALUE,
    HANDLE_SYRIATEL_NUMBERS,
    HANDLE_USDT_WALLETS,
    CHECK_SUBSCRIPTION
) = range(18)

async def create_subscription_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with subscription button and check button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 اشترك في القناة", url=f"https://t.me/{config.FORCED_CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
    ])

async def check_subscription(user_id: int, bot) -> bool:
    """Check if user is subscribed to the required channel."""
    try:
        member = await bot.get_chat_member(config.FORCED_CHANNEL_ID, user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.OWNER, ChatMember.ADMINISTRATOR]
    except Exception as e:
        await log_manager.log_error(None, error=e, custom_msg="Error checking subscription")
        return False

async def handle_subscription_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle subscription check callback."""
    query = update.callback_query
    await query.answer()
    
    if await check_subscription(query.from_user.id, context.bot):
        await start_after_subscription(update, context)
        return ConversationHandler.END
    else:
        await query.message.edit_text(
            "⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً\n"
            "اضغط على زر الاشتراك ثم تحقق من الاشتراك",
            reply_markup=await create_subscription_keyboard()
        )
        return CHECK_SUBSCRIPTION

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /start command."""
    user = update.effective_user
    
    if not await check_subscription(user.id, context.bot):
        await update.message.reply_text(
            "🌟 مرحباً بك في متجر الدايموند\n\n"
            "للاستمرار، يرجى الاشتراك في قناتنا الرسمية أولاً\n"
            "ثم اضغط على زر التحقق من الاشتراك",
            reply_markup=await create_subscription_keyboard()
        )
        return CHECK_SUBSCRIPTION
    
    return await start_after_subscription(update, context)

async def start_after_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bot functionality after subscription check."""
    user = update.effective_user
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        now = datetime.now()
        
        # Update or create user record
        c.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, joined_date, last_activity)
            VALUES (?, ?, ?, COALESCE((SELECT joined_date FROM users WHERE user_id = ?), ?), ?)
        ''', (user.id, user.username, user.first_name, user.id, now, now))
        conn.commit()

        welcome_text = (
            f"👋 مرحباً {user.first_name}\n\n"
            "💎 أهلاً بك في متجر الدايموند\n"
            "🏪 نقدم أفضل الأسعار وخدمة فورية\n\n"
            "📢 عروض اليوم:\n"
            "• شحن PUBG بأفضل الأسعار 🔫\n"
            "• كود شحن مباشر من الموقع الرسمي 🎮\n"
            "• شحن Free Fire بأرخص الأسعار 🔥\n"
            "• خصومات على جميع التطبيقات 📱\n\n"
            "💳 طرق الدفع المتاحة:\n"
            "• USDT (Coinex/CWallet/PEB20) 💰\n"
            "• USD (PAYEER) 💰\n"
            "• سيرياتيل كاش 📱\n"
            "• MTN كاش 📱\n"
            "• شام كاش 💰\n\n"
            "💱 أسعار الصرف:\n"
            f"• الدولار: {format_currency(float(config.USD_RATE))}\n"
            f"• USDT: {format_currency(float(config.USDT_RATE))}\n\n"
            "اختر من القائمة:"
        )

        if update.callback_query:
            await update.callback_query.message.edit_text(
                welcome_text,
                reply_markup=Keyboards.main_menu(is_admin(user.id))
            )
        else:
            await update.message.reply_text(
                welcome_text,
                reply_markup=Keyboards.main_menu(is_admin(user.id))
            )

        return ConversationHandler.END

    except sqlite3.Error as e:
        await log_manager.log_error(
            context,
            error=e,
            user_id=user.id,
            custom_msg="Error in start_command"
        )
        error_text = "❌ عذراً، حدث خطأ. يرجى المحاولة مرة أخرى"
        if update.callback_query:
            await update.callback_query.message.edit_text(error_text)
        else:
            await update.message.reply_text(error_text)
        return ConversationHandler.END

    finally:
        if 'conn' in locals():
            conn.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
    help_text = (
        "💎 مرحباً بك في متجر الدايموند\n\n"
        "📝 الأوامر المتاحة:\n"
        "/start - بدء البوت\n"
        "/help - عرض هذه المساعدة\n"
        "/cancel - إلغاء العملية الحالية\n\n"
        "👋 للبدء، اضغط على الأزرار في القائمة الرئيسية\n\n"
        f"💬 للدعم الفني تواصل مع: @{config.SUPPORT_USERNAME}"
    )
    await update.message.reply_text(help_text)
    
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restarts the bot."""
    user_id = update.message.from_user.id
    if user_id in config.ADMINS:
        await update.message.reply_text("جاري إعادة تشغيل البوت...")
        await context.application.shutdown()
        os.execl(sys.executable, sys.executable, *sys.argv)
    else:
        await update.message.reply_text("ليس لديك صلاحية لتنفيذ هذا الأمر.")
    
def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in config.ADMINS

async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to main menu."""
    query = update.callback_query
    await query.answer()
    
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    user = update.effective_user
    
    await update.message.reply_text(
        "❌ تم إلغاء العملية الحالية",
        reply_markup=Keyboards.main_menu(is_admin(user.id))
    )
    context.user_data.clear()
    return ConversationHandler.END