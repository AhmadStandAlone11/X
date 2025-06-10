import logging
import os
import random
import string
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown

from config import get_config
from database import get_database
from keyboards import Keyboards
from log_manager import get_log_manager
from utils import format_currency, get_damascus_time

# Initialize components
config = get_config()
db = get_database()
log_manager = get_log_manager()
keyboards = Keyboards()

# Constants for conversation states
(
    WAITING_FOR_AMOUNT,
    WAITING_FOR_PAYMENT_PROOF,
    WAITING_FOR_TXID,
    WAITING_FOR_REJECT_REASON,
    WAITING_FOR_SHAMCASH_TYPE
) = range(5)

# Payment method configurations
PAYMENT_METHODS = {
    'crypto': {
        'name': 'USDT',
        'options': [
            ('Coinex', {'value': config.USDT_WALLET_COINEX, 'note': 'Coinex Wallet', 'currency': 'USDT'}),
            ('CWallet', {'value': config.USDT_WALLET_CWALLET, 'note': 'CWallet Address', 'currency': 'USDT'}),
            ('Payeer', {'value': config.USD_WALLET_PAYEER, 'note': 'Payeer Wallet', 'currency': 'USD'}),
            ('PEB20', {'value': config.USDT_WALLET_PEB20, 'note': 'PEB20 Address', 'currency': 'USDT'})
        ]
    },
    'syriatel': {
        'name': 'سيرياتيل كاش',
        'numbers': config.SYRIATEL_CASH_NUMBERS
    },
    'mtn': {
        'name': 'MTN كاش',
        'numbers': config.MTN_CASH_NUMBERS
    },
    'shamcash': {
        'name': 'شام كاش',
        'numbers': config.SHAMCASH_NUMBERS,
        'options': [
            ('syp', 'تحويل ليرة سوري'),
            ('usd', 'تحويل USD')
        ]
    }
}

class RechargeManager:
    """Enhanced recharge management system with multiple payment methods."""
    
    def __init__(self):
        """Initialize the recharge manager."""
        self.logger = logging.getLogger(__name__)

    def generate_transaction_id(self, length: int = 12) -> str:
        """Generate a unique transaction ID."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    async def handle_recharge_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Display the main recharge menu."""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("💳 USDT/USD", callback_data="pay_type_crypto")],
            [
                InlineKeyboardButton("📱 سيرياتيل كاش", callback_data="pay_type_syriatel"),
                InlineKeyboardButton("📱 MTN كاش", callback_data="pay_type_mtn")
            ],
            [InlineKeyboardButton("💰 شام كاش", callback_data="pay_type_shamcash")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
        ]
        
        await query.message.edit_text(
            "💰 اختر طريقة الشحن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    async def handle_payment_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle payment type selection."""
        query = update.callback_query
        await query.answer()
        
        payment_type = query.data.split('_')[2]
        context.user_data['payment_type'] = payment_type
        
        if payment_type == 'crypto':
            keyboard = [
                [InlineKeyboardButton(f"{name} ({details['currency']})", 
                                    callback_data=f"pay_crypto_{name.lower()}")] 
                for name, details in PAYMENT_METHODS['crypto']['options']
            ]
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="charge")])
            
            await query.message.edit_text(
                "💰 اختر محفظة التحويل:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END
            
        elif payment_type == 'shamcash':
            keyboard = [
                [InlineKeyboardButton(text, callback_data=f"sham_{option}")]
                for option, text in PAYMENT_METHODS['shamcash']['options']
            ]
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="charge")])
            
            await query.message.edit_text(
                "💰 اختر نوع التحويل:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING_FOR_SHAMCASH_TYPE
            
        else:  # syriatel or mtn
            numbers = PAYMENT_METHODS[payment_type]['numbers']
            numbers_text = "\n".join([f"📱 {num}" for num in numbers])
            
            context.user_data['payment_method'] = payment_type
            
            await query.message.edit_text(
                f"📱 {PAYMENT_METHODS[payment_type]['name']}\n\n"
                "أرقامنا المعتمدة:\n"
                f"{numbers_text}\n\n"
                "أرسل المبلغ المراد شحنه (بالليرة السورية)",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="charge")
                ]])
            )
            return WAITING_FOR_AMOUNT

    async def handle_crypto_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle crypto payment method selection."""
        query = update.callback_query
        await query.answer()
        
        payment_method = query.data.split('_')[2]
        selected_wallet = None
        
        for name, details in PAYMENT_METHODS['crypto']['options']:
            if name.lower() == payment_method:
                selected_wallet = details
                break
        
        if not selected_wallet:
            await query.message.edit_text(
                "❌ خطأ في اختيار المحفظة",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="charge")
                ]])
            )
            return ConversationHandler.END
        
        context.user_data.update({
            'payment_method': 'crypto',
            'wallet_details': selected_wallet,
            'currency': selected_wallet['currency']
        })
        
        message_text = (
            f"💰 طريقة الدفع: {selected_wallet['currency']}\n"
            f"🏦 المحفظة: {selected_wallet['note']}\n"
            f"<code>{selected_wallet['value']}</code>\n\n"
            f"أرسل المبلغ المراد شحنه بالـ {selected_wallet['currency']}\n\n"
            f"⚠️ سيتم تحويل المبلغ إلى الليرة السورية حسب سعر الصرف الحالي:\n"
            f"1 {selected_wallet['currency']} = {format_currency(config.USDT_RATE if selected_wallet['currency'] == 'USDT' else config.USD_RATE)} ل.س"
        )
        
        await query.message.edit_text(
            message_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="charge")
            ]])
        )
        return WAITING_FOR_AMOUNT

    async def handle_shamcash_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle Sham Cash payment type selection."""
        query = update.callback_query
        await query.answer()
        
        sham_type = query.data.split('_')[1]
        context.user_data.update({
            'payment_method': 'shamcash',
            'sham_type': sham_type
        })
        
        numbers = PAYMENT_METHODS['shamcash']['numbers']
        numbers_text = "\n".join([f"📱 {num}" for num in numbers])
        
        if sham_type == 'usd':
            message_text = (
                "💰 شام كاش (تحويل USD)\n\n"
                "أرقامنا المعتمدة:\n"
                f"{numbers_text}\n\n"
                f"سعر الصرف الحالي: {format_currency(config.USD_RATE)} ل.س\n\n"
                "أرسل المبلغ المراد شحنه بالـ USD"
            )
        else:
            message_text = (
                "💰 شام كاش (تحويل ليرة سوري)\n\n"
                "أرقامنا المعتمدة:\n"
                f"{numbers_text}\n\n"
                "أرسل المبلغ المراد شحنه بالليرة السورية"
            )
        
        await query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="charge")
            ]])
        )
        return WAITING_FOR_AMOUNT

    async def handle_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle amount input for any payment method."""
        try:
            amount = Decimal(update.message.text.strip())
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            payment_method = context.user_data.get('payment_method')
            
            # Calculate amounts based on payment method
            if payment_method == 'crypto':
                currency = context.user_data['currency']
                rate = config.USDT_RATE if currency == 'USDT' else config.USD_RATE
                syp_amount = amount * rate
                context.user_data.update({
                    'original_amount': amount,
                    'original_currency': currency,
                    'amount': syp_amount
                })
                
                await update.message.reply_text(
                    f"💰 المبلغ: {amount} {currency}\n"
                    f"💵 ما يعادل: {format_currency(syp_amount)} ل.س\n\n"
                    "🔢 أرسل رقم العملية"
                )
                
            elif payment_method == 'shamcash':
                sham_type = context.user_data.get('sham_type')
                if sham_type == 'usd':
                    syp_amount = amount * config.USD_RATE
                    context.user_data.update({
                        'original_amount': amount,
                        'original_currency': 'USD',
                        'amount': syp_amount
                    })
                    await update.message.reply_text(
                        f"💰 المبلغ: {amount} USD\n"
                        f"💵 ما يعادل: {format_currency(syp_amount)} ل.س\n\n"
                        "🔢 أرسل رقم العملية"
                    )
                else:
                    context.user_data['amount'] = amount
                    await update.message.reply_text(
                        f"💰 المبلغ: {format_currency(amount)} ل.س\n\n"
                        "🔢 أرسل رقم العملية"
                    )
                    
            else:  # syriatel or mtn
                context.user_data['amount'] = amount
                await update.message.reply_text(
                    f"💰 المبلغ: {format_currency(amount)} ل.س\n\n"
                    "🔢 أرسل رقم العملية"
                )
                
            return WAITING_FOR_TXID
            
        except ValueError as e:
            await update.message.reply_text(
                "❌ الرجاء إدخال مبلغ صحيح وموجب",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="charge")
                ]])
            )
            return WAITING_FOR_AMOUNT

    async def handle_txid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle transaction ID input."""
        tx_id = update.message.text.strip()
        
        if not tx_id:
            await update.message.reply_text("❌ الرجاء إدخال رقم عملية صحيح")
            return WAITING_FOR_TXID
            
        payment_data = context.user_data
        user_id = update.effective_user.id
        
        try:
            # Create transaction record
            success = await db.create_transaction(
                tx_id=tx_id,
                user_id=user_id,
                amount=payment_data['amount'],
                payment_method=payment_data['payment_method'],
                original_amount=payment_data.get('original_amount'),
                original_currency=payment_data.get('original_currency'),
                payment_details=payment_data
            )
            
            if not success:
                await update.message.reply_text("❌ حدث خطأ أثناء إنشاء العملية")
                return ConversationHandler.END
            
            # Format confirmation message
            if 'original_amount' in payment_data:
                message = (
                    "✅ تم استلام طلب الشحن بنجاح\n\n"
                    f"💰 المبلغ: {payment_data['original_amount']} {payment_data['original_currency']}\n"
                    f"💵 ما يعادل: {format_currency(payment_data['amount'])} ل.س\n"
                )
            else:
                message = (
                    "✅ تم استلام طلب الشحن بنجاح\n\n"
                    f"💰 المبلغ: {format_currency(payment_data['amount'])} ل.س\n"
                )
                
            message += (
                f"💳 طريقة الدفع: {PAYMENT_METHODS[payment_data['payment_method']]['name']}\n"
                f"🔢 رقم العملية: {tx_id}\n\n"
                "⏳ سيتم مراجعة طلبك في أقرب وقت ممكن"
            )
            
            await update.message.reply_text(message)
            
            # Notify admins
            await self.notify_admins(update, context, tx_id, payment_data)
            
            # Log the transaction
            await log_manager.log_transaction(
                context,
                user_id=user_id,
                amount=payment_data['amount'],
                transaction_type="recharge_request",
                status="pending",
                details=f"Payment Method: {payment_data['payment_method']}\nTX ID: {tx_id}"
            )
            
            context.user_data.clear()
            return ConversationHandler.END
            
        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                user_id=user_id,
                custom_msg=f"Error processing transaction {tx_id}"
            )
            await update.message.reply_text("❌ حدث خطأ غير متوقع")
            return ConversationHandler.END

    async def confirm_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Confirm a payment request."""
        query = update.callback_query
        await query.answer()
        
        tx_id = query.data.split('_')[2]
        admin_id = query.from_user.id
        
        try:
            # Get transaction details
            tx_details = await db.get_transaction(tx_id)
            if not tx_details:
                await query.edit_message_text(
                    "❌ لم يتم العثور على العملية",
                    reply_markup=None
                )
                return
                
            if tx_details['status'] != 'pending':
                await query.edit_message_text(
                    "⚠️ هذه العملية مؤكدة أو ملغاة بالفعل",
                    reply_markup=None
                )
                return
            
            # Update transaction status and user balance
            success = await db.confirm_transaction(tx_id, admin_id)
            if not success:
                await query.edit_message_text(
                    "❌ حدث خطأ أثناء تأكيد العملية",
                    reply_markup=None
                )
                return
            
            # Format confirmation message
            admin_name = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name
            
            if tx_details.get('original_amount'):
                message = (
                    f"{query.message.text}\n\n"
                    "✅ تم تأكيد العملية\n"
                    f"👤 بواسطة: {admin_name}\n"
                    f"⏰ {get_damascus_time()}\n"
                    f"💰 المبلغ: {tx_details['original_amount']} {tx_details['original_currency']}\n"
                    f"💵 ما يعادل: {format_currency(tx_details['amount'])} ل.س"
                )
            else:
                message = (
                    f"{query.message.text}\n\n"
                    "✅ تم تأكيد العملية\n"
                    f"👤 بواسطة: {admin_name}\n"
                    f"⏰ {get_damascus_time()}\n"
                    f"💰 المبلغ: {format_currency(tx_details['amount'])} ل.س"
                )
            
            await query.edit_message_text(message, reply_markup=None)
            
            # Notify user
            user_message = (
                "✅ تم تأكيد عملية الشحن\n\n"
                f"🔢 رقم العملية: {tx_id}\n"
            )
            
            if tx_details.get('original_amount'):
                user_message += (
                    f"💰 المبلغ: {tx_details['original_amount']} {tx_details['original_currency']}\n"
                    f"💵 ما يعادل: {format_currency(tx_details['amount'])} ل.س"
                )
            else:
                user_message += f"💰 المبلغ: {format_currency(tx_details['amount'])} ل.س"
            
            await context.bot.send_message(
                chat_id=tx_details['user_id'],
                text=user_message
            )
            
            # Log the confirmation
            await log_manager.log_transaction(
                context,
                user_id=tx_details['user_id'],
                amount=tx_details['amount'],
                transaction_type="recharge_confirmed",
                status="completed",
                details=f"Confirmed by {admin_name}"
            )
            
        except Exception as e:
            await log_manager.log_error(context, error=e)
            await query.edit_message_text(
                "❌ حدث خطأ غير متوقع",
                reply_markup=None
            )

    async def reject_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the payment rejection process."""
        query = update.callback_query
        await query.answer()
        
        tx_id = query.data.split('_')[2]
        context.user_data['reject_tx_id'] = tx_id
        
        await query.edit_message_text(
            "📝 سبب الرفض:\n"
            "أرسل سبب رفض عملية الشحن",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء", callback_data="cancel_reject")
            ]])
        )
        return WAITING_FOR_REJECT_REASON

    async def handle_reject_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the rejection reason and complete the rejection process."""
        try:
            reason = update.message.text.strip()
            tx_id = context.user_data.get('reject_tx_id')
            admin_id = update.effective_user.id
            
            # Get transaction details and update status
            success = await db.reject_transaction(tx_id, admin_id, reason)
            if not success:
                await update.message.reply_text("❌ حدث خطأ أثناء رفض العملية")
                return ConversationHandler.END
            
            tx_details = await db.get_transaction(tx_id)
            admin_name = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name
            
            # Format rejection message
            if tx_details.get('original_amount'):
                message = (
                    f"❌ تم رفض عملية الشحن #{tx_id}\n\n"
                    f"💰 المبلغ: {tx_details['original_amount']} {tx_details['original_currency']}\n"
                    f"💵 ما يعادل: {format_currency(tx_details['amount'])} ل.س\n"
                    f"📝 السبب: {reason}\n"
                    f"👤 بواسطة: {admin_name}\n"
                    f"⏰ {get_damascus_time()}"
                )
            else:
                message = (
                    f"❌ تم رفض عملية الشحن #{tx_id}\n\n"
                    f"💰 المبلغ: {format_currency(tx_details['amount'])} ل.س\n"
                    f"📝 السبب: {reason}\n"
                    f"👤 بواسطة: {admin_name}\n"
                    f"⏰ {get_damascus_time()}"
                )
            
            await update.message.reply_text("✅ تم رفض العملية بنجاح")
            
            # Notify user
            await context.bot.send_message(
                chat_id=tx_details['user_id'],
                text=f"{message}\n\nللمزيد من التفاصيل تواصل مع الدعم الفني"
            )
            
            # Log the rejection
            await log_manager.log_transaction(
                context,
                user_id=tx_details['user_id'],
                amount=tx_details['amount'],
                transaction_type="recharge_rejected",
                status="rejected",
                details=f"Rejected by {admin_name}\nReason: {reason}"
            )
            
            context.user_data.clear()
            return ConversationHandler.END
            
        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                custom_msg="Error processing payment rejection"
            )
            await update.message.reply_text("❌ حدث خطأ غير متوقع")
            return ConversationHandler.END

    async def notify_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          tx_id: str, payment_data: Dict[str, Any]) -> None:
        """Send notification to admin group about new payment request."""
        try:
            user = update.effective_user
            user_identifier = f"@{user.username}" if user.username else user.first_name
            
            message = (
                "📱 طلب شحن جديد\n\n"
                f"👤 المستخدم: {user_identifier} ({user.id})\n"
            )
            
            if payment_data.get('original_amount'):
                message += (
                    f"💰 المبلغ: {payment_data['original_amount']} {payment_data['original_currency']}\n"
                    f"💵 ما يعادل: {format_currency(payment_data['amount'])} ل.س\n"
                )
            else:
                message += f"💰 المبلغ: {format_currency(payment_data['amount'])} ل.س\n"
                
            message += (
                f"💳 طريقة الدفع: {PAYMENT_METHODS[payment_data['payment_method']]['name']}\n"
                f"🔢 رقم العملية: {tx_id}"
            )
            
            await context.bot.send_message(
                chat_id=config.RECHARGE_GROUP_ID,
                text=message,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_payment_{tx_id}"),
                        InlineKeyboardButton("❌ رفض", callback_data=f"reject_payment_{tx_id}")
                    ]
                ])
            )
            
        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                custom_msg=f"Error sending admin notification for TX: {tx_id}"
            )

# Create singleton instance
_recharge_manager = RechargeManager()

def get_recharge_manager() -> RechargeManager:
    """Get the RechargeManager instance."""
    return _recharge_manager