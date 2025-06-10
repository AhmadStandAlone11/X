import logging
import os
import sys
from datetime import timedelta, datetime
import json
from typing import Dict, Any
from decimal import Decimal
from telegram.ext import PicklePersistence, PersistenceInput
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

# Add the directory containing modules to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import local modules
from database import get_database
from config import get_config
from log_manager import get_log_manager
from admin import AdminPanel
from recharge import get_recharge_manager
from purchase import get_purchase_manager
from product_manager import ProductManager  
from product_handlers import get_product_management_handler
from keyboards import Keyboards

from handlers import *

# Initialize components
config = get_config()
db = get_database()
log_manager = get_log_manager()
keyboards = Keyboards()
product_manager = ProductManager()

# Constants for conversation states
(
    WAITING_FOR_AMOUNT,
    WAITING_FOR_PAYMENT_PROOF,
    WAITING_FOR_TXID,
    WAITING_FOR_RATE,
    WAITING_FOR_GAME_ID,
    WAITING_FOR_PRICE_UPDATE,
    WAITING_FOR_REJECT_REASON,
    EDITING_ENV_VALUE,
    HANDLE_SYRIATEL_NUMBERS,
    HANDLE_USDT_WALLETS,
    WAITING_FOR_SHAMCASH_TYPE,
    WAITING_FOR_APP_QUANTITY,
    WAITING_FOR_APP_ID
) = range(13)

async def check_updates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic task to check for updates and maintenance."""
    try:
        # Check database connection
        await db.ping()
        
        # Cleanup expired transactions
        expiry_time = datetime.now() - timedelta(hours=24)
        expired_count = await db.cleanup_expired_transactions(expiry_time)
        
        if expired_count > 0:
            await log_manager.log_action(
                context=context,
                action="Cleanup",
                details=f"Cleaned up {expired_count} expired transactions",
                level="info"
            )
            
        # Reload products if needed
        if await product_manager.should_reload_products():
            await product_manager.reload_products()
            
    except Exception as e:
        await log_manager.log_error(
            context=context,
            error=e,
            custom_msg="Error in periodic updates"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced error handler."""
    try:
        await log_manager.log_error(
            context=context,
            error=context.error,
            user_id=update.effective_user.id if update and update.effective_user else None,
            custom_msg=f"Update: {update.to_dict() if update else 'No update'}"
        )

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ عذراً، حدث خطأ غير متوقع\n"
                "🔄 يرجى المحاولة مرة أخرى لاحقاً\n"
                "📞 إذا استمرت المشكلة، يرجى التواصل مع الدعم الفني",
                reply_markup=keyboards.main_menu()
            )

    except Exception as e:
        logging.error(f"Critical error in error handler: {e}")

def main() -> None:
    """Enhanced main function."""
    try:
        # Validate essential configurations
        if not config.BOT_TOKEN:
            raise ValueError("Bot token not found in environment variables")

        # Initialize components
        # product_manager.init()  # تم حذف هذا السطر
        
        # Initialize application with persistence
        persistence = PicklePersistence(
            filepath="conversation_states.pkl",
            store_data=PersistenceInput(
                bot_data=True,
                chat_data=True,
                user_data=True,
                callback_data=True
            )
        )

        application = (
            Application.builder()
            .token(config.BOT_TOKEN)
            .persistence(persistence)
            .concurrent_updates(True)
            .connection_pool_size(8)
            .pool_timeout(30.0)
            .build()
        )

        # Initialize managers
        admin_panel = AdminPanel()
        recharge_manager = get_recharge_manager()
        
        # 1. الحصول على بيانات المنتجات:
        products = product_manager.get_all_products()
        game_products = products.get('games', {})
        app_products = products.get('apps', {})

        purchase_manager = get_purchase_manager(game_products=game_products, app_products=app_products) # تم التعديل هنا

        # Create main conversation handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", start_command),
                CommandHandler("admin", admin_panel.admin_panel),
                CallbackQueryHandler(handle_subscription_check, pattern="^check_subscription$"),
            ],
            states={
                CHECK_SUBSCRIPTION: [
                    CallbackQueryHandler(handle_subscription_check, pattern="^check_subscription$")
                ],
                WAITING_FOR_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_manager.handle_amount)
                ],
                WAITING_FOR_PAYMENT_PROOF: [
                    MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, recharge_manager.handle_txid)
                ],
                WAITING_FOR_TXID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_manager.handle_txid)
                ],
                WAITING_FOR_GAME_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_manager.handle_game_id)
                ],
                WAITING_FOR_APP_QUANTITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_manager.handle_app_quantity)
                ],
                WAITING_FOR_APP_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_manager.handle_app_id)
                ],
                WAITING_FOR_PRICE_UPDATE: [
                    #MessageHandler(filters.TEXT & ~filters.COMMAND, product_manager.handle_price_update)  # تم التعليق هنا
                    
                ],
                WAITING_FOR_REJECT_REASON: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_manager.handle_reject_reason)
                ],
                WAITING_FOR_SHAMCASH_TYPE: [
                    CallbackQueryHandler(recharge_manager.handle_shamcash_type, pattern=r"^sham_(syp|usd)$")
                ],
            },
            fallbacks=[
               # CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
                CallbackQueryHandler(back_to_main_callback, pattern="^back_to_main$"),
            ],
            name="main_conversation",
            persistent=True,
            allow_reentry=True,
        )

        # Add handlers
        application.add_handler(conv_handler)
        application.add_handler(admin_panel.get_conversation_handler())
        application.add_handler(get_product_management_handler())

        # Add callback handlers
        application.add_handler(CallbackQueryHandler(
            recharge_manager.handle_payment_type,
            pattern=r"^pay_type_"
        ))
        application.add_handler(CallbackQueryHandler(
            recharge_manager.handle_crypto_payment,
            pattern=r"^pay_crypto_"
        ))
        application.add_handler(CallbackQueryHandler(
            purchase_manager.handle_buy_game,
            pattern=r"^buy_game_"
        ))
        application.add_handler(CallbackQueryHandler(
            purchase_manager.handle_buy_app,
            pattern=r"^buy_app_"
        ))

        # Set up error handler
        application.add_error_handler(error_handler)

        # Set up periodic tasks
        job_queue = application.job_queue
        job_queue.run_repeating(
            check_updates,
            interval=timedelta(minutes=30),
            first=10
        )

        # Log startup
        startup_message = (
            "\n" + "=" * 50 + "\n"
            "✅ تم تشغيل البوت بنجاح\n"
            f"⏰ وقت التشغيل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"👤 المطور: @{config.SUPPORT_USERNAME}\n"
            f"🤖 معرف البوت: @{config.BOT_USERNAME}\n"
            f"💰 سعر صرف الدولار: {config.USD_RATE:,} ل.س\n"
            f"💰 سعر صرف USDT: {config.USDT_RATE:,} ل.س\n"
            "📊 النسخة: 2.2\n"
            + "=" * 50 + "\n"
        )
        print(startup_message)
        logging.info("Bot started successfully")

        # Start the bot
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Exception as e:
        logging.critical(f"Critical error during startup: {e}")
        print(f"\n❌ خطأ حرج: {e}")
        print("\nتفاصيل الخطأ:")
        import traceback
        print(traceback.format_exc())
    finally:
        print("\n⚠️ تم إيقاف البوت")
        logging.info("Bot stopped")

if __name__ == "__main__":
    main()