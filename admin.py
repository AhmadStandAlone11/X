import logging
from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)

from config import get_config
from database import get_database
from keyboards import Keyboards

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    ADMIN_PANEL,
    ADMIN_BAN_USER,
    ADMIN_UNBAN_USER,
    ADMIN_MODIFY_BALANCE,
    ADMIN_MODIFY_BALANCE_AMOUNT,
    EDIT_ENV_VALUE,
    EDIT_RATE,
    EDIT_SYRIATEL,
    EDIT_USDT_WALLETS,
) = range(9)

class AdminPanel:
    """Enhanced Admin Panel Handler with improved functionality and error handling."""
    
    def __init__(self):
        """Initialize the admin panel with necessary components."""
        self.config = get_config()
        self.db = get_database()
        self.keyboards = Keyboards()
        self.damascus_tz = timezone(timedelta(hours=3))

    async def format_currency(self, amount: Decimal) -> str:
        """Format currency with thousand separators."""
        return f"{amount:,.2f}"

    async def get_user_info_text(self, stats: Dict) -> str:
        """Format user information text."""
        damascus_time = lambda dt: dt.astimezone(self.damascus_tz)
        
        return (
            f"👤 معلومات المستخدم\n\n"
            f"🆔 معرف المستخدم: {stats['user_id']}\n"
            f"👤 اسم المستخدم: {stats['username'] or 'غير محدد'}\n"
            f"📝 الاسم: {stats['first_name'] or 'غير محدد'}\n"
            f"💰 الرصيد الحالي: ${await self.format_currency(stats['current_balance'])}\n"
            f"📅 تاريخ الانضمام: {damascus_time(stats['join_date']).strftime('%Y-%m-%d %H:%M')}\n"
            f"⏱ آخر نشاط: {damascus_time(stats['last_active']).strftime('%Y-%m-%d %H:%M')}\n"
            f"📊 إحصائيات المعاملات:\n"
            f"   • عدد المعاملات: {stats['total_transactions']}\n"
            f"   • مجموع الإيداعات: ${await self.format_currency(stats['total_deposits'])}\n"
            f"   • مجموع السحوبات: ${await self.format_currency(stats['total_withdrawals'])}\n"
            f"🛒 إحصائيات الطلبات:\n"
            f"   • عدد الطلبات: {stats['total_orders']}\n"
            f"   • مجموع المشتريات: ${await self.format_currency(stats['total_spent'])}\n"
            f"🚦 الحالة: {'محظور ⛔️' if stats['is_banned'] else 'نشط ✅'}"
        )

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Display the main admin panel with statistics."""
        user_id = update.effective_user.id
        if not await self.db.is_admin(user_id):
            await update.message.reply_text(
                "⛔️ عذراً، هذا الأمر متاح للمشرفين فقط.",
                reply_markup=self.keyboards.get_start_keyboard()
            )
            return ConversationHandler.END

        try:
            total_users = await self.db.get_total_users()
            active_users = await self.db.get_active_users_last_24h()
            total_volume = await self.db.get_total_transaction_volume()
            
            stats_message = (
                "📊 لوحة التحكم\n\n"
                f"👥 إجمالي المستخدمين: {total_users:,}\n"
                f"✅ المستخدمين النشطين (24h): {active_users:,}\n"
                f"💰 إجمالي حجم التداول: ${await self.format_currency(total_volume)}\n\n"
                "💱 أسعار الصرف الحالية:\n"
                f"   • USD: {self.config.USD_RATE:,} ل.س\n"
                f"   • USDT: {self.config.USDT_RATE:,} ل.س"
            )

            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    stats_message,
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            else:
                await update.message.reply_text(
                    stats_message,
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            return ADMIN_PANEL
            
        except Exception as e:
            logger.error(f"Error in admin panel: {e}")
            error_message = "⚠️ حدث خطأ أثناء تحميل لوحة التحكم. الرجاء المحاولة مرة أخرى."
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(error_message)
            else:
                await update.message.reply_text(error_message)
            return ConversationHandler.END

    async def handle_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the user ban process."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🚫 حظر مستخدم\n\n"
            "الرجاء إرسال معرف المستخدم أو رقم الهوية الخاص به.",
            reply_markup=self.keyboards.get_cancel_keyboard()
        )
        return ADMIN_BAN_USER

    async def execute_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Execute the ban user action."""
        try:
            user_input = update.message.text.strip()
            admin_id = update.effective_user.id
            
            # Convert username/ID to user_id
            user_id = (int(user_input) if user_input.isdigit() 
                      else await self.db.get_user_id_by_username(user_input))
            
            if not user_id:
                await update.message.reply_text(
                    "❌ لم يتم العثور على المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                return ADMIN_PANEL

            # Get user stats before banning
            user_stats = await self.db.get_user_stats(user_id)
            if not user_stats:
                await update.message.reply_text(
                    "❌ خطأ في جلب معلومات المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                return ADMIN_PANEL

            # Execute ban
            if await self.db.ban_user(user_id, admin_id):
                user_info = await self.get_user_info_text(user_stats)
                await update.message.reply_text(
                    f"✅ تم حظر المستخدم بنجاح\n\n{user_info}",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ حدث خطأ أثناء حظر المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error in execute_ban_user: {e}")
            await update.message.reply_text(
                "⚠️ حدث خطأ غير متوقع.",
                reply_markup=self.keyboards.get_admin_keyboard()
            )
        
        return ADMIN_PANEL

    async def handle_unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the user unban process."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "✅ إلغاء حظر مستخدم\n\n"
            "الرجاء إرسال معرف المستخدم أو رقم الهوية الخاص به.",
            reply_markup=self.keyboards.get_cancel_keyboard()
        )
        return ADMIN_UNBAN_USER

    async def execute_unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Execute the unban user action."""
        try:
            user_input = update.message.text.strip()
            admin_id = update.effective_user.id
            
            user_id = (int(user_input) if user_input.isdigit() 
                      else await self.db.get_user_id_by_username(user_input))
            
            if not user_id:
                await update.message.reply_text(
                    "❌ لم يتم العثور على المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                return ADMIN_PANEL

            if await self.db.unban_user(user_id, admin_id):
                user_stats = await self.db.get_user_stats(user_id)
                user_info = await self.get_user_info_text(user_stats)
                await update.message.reply_text(
                    f"✅ تم إلغاء حظر المستخدم بنجاح\n\n{user_info}",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ حدث خطأ أثناء إلغاء حظر المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error in execute_unban_user: {e}")
            await update.message.reply_text(
                "⚠️ حدث خطأ غير متوقع.",
                reply_markup=self.keyboards.get_admin_keyboard()
            )
        
        return ADMIN_PANEL

    async def handle_modify_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the balance modification process."""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "💰 تعديل رصيد مستخدم\n\n"
            "الرجاء إرسال معرف المستخدم أو رقم الهوية الخاص به.",
            reply_markup=self.keyboards.get_cancel_keyboard()
        )
        return ADMIN_MODIFY_BALANCE

    async def handle_modify_balance_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the balance amount input step."""
        try:
            user_input = update.message.text.strip()
            user_id = (int(user_input) if user_input.isdigit() 
                      else await self.db.get_user_id_by_username(user_input))
            
            if not user_id:
                await update.message.reply_text(
                    "❌ لم يتم العثور على المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                return ADMIN_PANEL

            user_stats = await self.db.get_user_stats(user_id)
            if not user_stats:
                await update.message.reply_text(
                    "❌ خطأ في جلب معلومات المستخدم.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                return ADMIN_PANEL

            context.user_data['target_user_id'] = user_id
            context.user_data['current_balance'] = user_stats['current_balance']
            
            await update.message.reply_text(
                f"💰 تعديل الرصيد\n\n"
                f"الرصيد الحالي: ${await self.format_currency(user_stats['current_balance'])}\n\n"
                "الرجاء إدخال المبلغ المراد تعديله:\n"
                "• استخدم الإشارة + للإضافة (مثال: +100)\n"
                "• استخدم الإشارة - للخصم (مثال: -100)",
                reply_markup=self.keyboards.get_cancel_keyboard()
            )
            return ADMIN_MODIFY_BALANCE_AMOUNT
            
        except Exception as e:
            logger.error(f"Error in handle_modify_balance_amount: {e}")
            await update.message.reply_text(
                "⚠️ حدث خطأ غير متوقع.",
                reply_markup=self.keyboards.get_admin_keyboard()
            )
            return ADMIN_PANEL

    async def execute_modify_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Execute the balance modification."""
        try:
            amount_str = update.message.text.strip()
            user_id = context.user_data.get('target_user_id')
            admin_id = update.effective_user.id
            
            try:
                # Handle both +/- prefixed and plain numbers
                amount = (Decimal(amount_str) if amount_str.startswith(('+', '-')) 
                         else Decimal(f"+{amount_str}"))
            except:
                await update.message.reply_text(
                    "❌ الرجاء إدخال رقم صحيح.",
                    reply_markup=self.keyboards.get_cancel_keyboard()
                )
                return ADMIN_MODIFY_BALANCE_AMOUNT

            if await self.db.modify_user_balance(user_id, amount, admin_id):
                user_stats = await self.db.get_user_stats(user_id)
                user_info = await self.get_user_info_text(user_stats)
                await update.message.reply_text(
                    f"✅ تم تعديل الرصيد بنجاح\n\n{user_info}",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ حدث خطأ أثناء تعديل الرصيد.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error in execute_modify_balance: {e}")
            await update.message.reply_text(
                "⚠️ حدث خطأ غير متوقع.",
                reply_markup=self.keyboards.get_admin_keyboard()
            )
            
        return ADMIN_PANEL

    async def handle_rate_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle exchange rate update request."""
        query = update.callback_query
        await query.answer()
        
        currency = query.data.split('_')[-1]
        context.user_data['currency'] = currency
        current_rate = (self.config.USD_RATE if currency == 'USD' 
                       else self.config.USDT_RATE)
        
        await query.edit_message_text(
            f"💱 تعديل سعر صرف {currency}\n\n"
            f"السعر الحالي: {current_rate:,} ل.س\n"
            "أدخل السعر الجديد:",
            reply_markup=self.keyboards.get_cancel_keyboard()
        )
        return EDIT_RATE

    async def execute_rate_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Execute the exchange rate update."""
        try:
            rate_str = update.message.text.strip()
            currency = context.user_data.get('currency')
            
            try:
                new_rate = Decimal(rate_str)
                if new_rate <= 0:
                    raise ValueError("Rate must be positive")
            except:
                await update.message.reply_text(
                    "❌ الرجاء إدخال رقم صحيح وموجب.",
                    reply_markup=self.keyboards.get_cancel_keyboard()
                )
                return EDIT_RATE

            # Update rate based on currency
            if currency == 'USD':
                success = self.config.update_usd_rate(str(new_rate))
            else:
                success = self.config.update_usdt_rate(str(new_rate))

            if success:
                await update.message.reply_text(
                    f"✅ تم تحديث سعر صرف {currency} إلى {new_rate:,} ل.س بنجاح.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"❌ حدث خطأ أثناء تحديث سعر الصرف.",
                    reply_markup=self.keyboards.get_admin_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error in execute_rate_update: {e}")
            await update.message.reply_text(
                "⚠️ حدث خطأ غير متوقع.",
                reply_markup=self.keyboards.get_admin_keyboard()
            )
            
        return ADMIN_PANEL

    def get_conversation_handler(self) -> ConversationHandler:
        """Get the conversation handler for the admin panel."""
        return ConversationHandler(
            entry_points=[
                CommandHandler('admin', self.admin_panel),
                CallbackQueryHandler(self.admin_panel, pattern='^admin_panel$')
            ],
            states={
                ADMIN_PANEL: [
                    CallbackQueryHandler(self.admin_panel, pattern='^admin_stats$'),
                    CallbackQueryHandler(self.handle_ban_user, pattern='^ban_user$'),
                    CallbackQueryHandler(self.handle_unban_user, pattern='^unban_user$'),
                    CallbackQueryHandler(self.handle_modify_balance, pattern='^modify_balance$'),
                    CallbackQueryHandler(self.handle_rate_update, pattern='^rate_(USD|USDT)$'),
                ],
                ADMIN_BAN_USER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.execute_ban_user)
                ],
                ADMIN_UNBAN_USER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.execute_unban_user)
                ],
                ADMIN_MODIFY_BALANCE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_modify_balance_amount)
                ],
                ADMIN_MODIFY_BALANCE_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.execute_modify_balance)
                ],
                EDIT_RATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.execute_rate_update)
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_panel, pattern='^cancel$'),
                CommandHandler('cancel', self.admin_panel)
            ],
            name="admin_panel",
            persistent=True
        )