import logging
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

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

# Conversation states
(
    WAITING_FOR_GAME_ID,
    WAITING_FOR_APP_QUANTITY,
    WAITING_FOR_APP_ID
) = range(3)

class PurchaseManager:
    """Enhanced purchase management system."""
    
    def __init__(self, game_products: Dict[str, Any], app_products: Dict[str, Any]):
        """Initialize the purchase manager."""
        self.logger = logging.getLogger(__name__)
        self.game_products = game_products
        self.app_products = app_products

    def get_product_details(self, product_type: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Get product details from products dictionary."""
        products = self.game_products if product_type == 'game' else self.app_products
        return products.get(product_id)

    async def handle_buy_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle game purchase process."""
        query = update.callback_query
        await query.answer()

        # Parse product information
        _, product_type, product_id, package_index = query.data.split('_')
        package_index = int(package_index)
        
        product = self.get_product_details('game', product_id)
        if not product:
            await query.message.edit_text("❌ عذراً، المنتج غير متوفر حالياً")
            return ConversationHandler.END

        package = product['packages'][package_index]
        package_name, price = package

        # Store in context
        context.user_data.update({
            'product_type': 'game',
            'product_id': product_id,
            'product_name': product['name'],
            'package_name': package_name,
            'price': Decimal(str(price)),
            'icon': product['icon']
        })

        await query.message.edit_text(
            f"🎮 {product['name']} {product['icon']}\n"
            f"📦 الباقة: {package_name}\n"
            f"💰 السعر: {format_currency(price)} ل.س\n\n"
            "📝 أدخل الـ ID الخاص بحسابك:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"game_{product_id}")
            ]])
        )
        return WAITING_FOR_GAME_ID

    async def handle_buy_app(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle app purchase process."""
        query = update.callback_query
        await query.answer()

        # Parse product information
        _, product_type, product_id = query.data.split('_')
        
        product = self.get_product_details('app', product_id)
        if not product:
            await query.message.edit_text("❌ عذراً، المنتج غير متوفر حالياً")
            return ConversationHandler.END

        # Store in context
        context.user_data.update({
            'product_type': 'app',
            'product_id': product_id,
            'product_name': product['name'],
            'base_price': Decimal(str(product['price'])),
            'min_quantity': product['package_size'],
            'icon': product['icon']
        })

        # Calculate price per unit
        price_per_unit = context.user_data['base_price'] / product['package_size']

        await query.message.edit_text(
            f"📱 {product['name']} {product['icon']}\n\n"
            f"💎 كل {product['package_size']} = {format_currency(product['price'])} ل.س\n"
            f"💰 سعر الوحدة: {format_currency(price_per_unit)} ل.س\n\n"
            f"📝 أدخل الكمية المطلوبة (الحد الأدنى {product['package_size']}):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="apps")
            ]])
        )
        return WAITING_FOR_APP_QUANTITY

    async def handle_app_quantity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle app quantity input."""
        try:
            quantity = int(update.message.text.strip())
            min_quantity = context.user_data['min_quantity']
            
            if quantity < min_quantity:
                await update.message.reply_text(
                    f"❌ الكمية المدخلة أقل من الحد الأدنى ({min_quantity})",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 رجوع", callback_data="apps")
                    ]])
                )
                return WAITING_FOR_APP_QUANTITY

            # Calculate total price
            base_price = context.user_data['base_price']
            units = quantity / min_quantity
            total_price = base_price * units

            # Update context
            context.user_data.update({
                'quantity': quantity,
                'price': total_price
            })

            await update.message.reply_text(
                f"📱 {context.user_data['product_name']} {context.user_data['icon']}\n"
                f"📦 الكمية: {quantity}\n"
                f"💰 السعر الإجمالي: {format_currency(total_price)} ل.س\n\n"
                "📝 أدخل الـ ID الخاص بحسابك:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="apps")
                ]])
            )
            return WAITING_FOR_APP_ID

        except ValueError:
            await update.message.reply_text(
                "❌ الرجاء إدخال رقم صحيح",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="apps")
                ]])
            )
            return WAITING_FOR_APP_QUANTITY

    async def handle_game_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle game ID input."""
        game_id = update.message.text.strip()
        return await self._process_purchase(update, context, game_id)

    async def handle_app_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle app ID input."""
        app_id = update.message.text.strip()
        return await self._process_purchase(update, context, app_id)

    async def _process_purchase(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> int:
        """Process the purchase for both games and apps."""
        try:
            # Check user balance
            user_balance = await db.get_user_balance(update.effective_user.id)
            price = context.user_data['price']

            if user_balance < price:
                await update.message.reply_text(
                    "❌ رصيدك غير كافٍ لإتمام عملية الشراء\n\n"
                    f"💰 رصيدك الحالي: {format_currency(user_balance)} ل.س\n"
                    f"💸 سعر المنتج: {format_currency(price)} ل.س"
                )
                return ConversationHandler.END

            # Create order
            order_id = await db.create_order(
                user_id=update.effective_user.id,
                product_type=context.user_data['product_type'],
                product_id=context.user_data['product_id'],
                game_id=user_id,
                price=price
            )

            if not order_id:
                await update.message.reply_text("❌ حدث خطأ أثناء إنشاء الطلب")
                return ConversationHandler.END

            # Update user balance
            if not await db.update_user_balance(update.effective_user.id, -price):
                await update.message.reply_text("❌ حدث خطأ أثناء خصم الرصيد")
                return ConversationHandler.END

            # Format user notification
            product_type = "🎮" if context.user_data['product_type'] == 'game' else "📱"
            if context.user_data['product_type'] == 'game':
                details = f"📦 الباقة: {context.user_data['package_name']}"
            else:
                details = f"📦 الكمية: {context.user_data['quantity']}"

            await update.message.reply_text(
                "✅ تم استلام طلبك بنجاح\n\n"
                f"{product_type} المنتج: {context.user_data['product_name']}\n"
                f"{details}\n"
                f"📝 الـ ID: {user_id}\n"
                f"💰 السعر: {format_currency(price)} ل.س\n\n"
                "⏳ سيتم تنفيذ طلبك في أقرب وقت ممكن"
            )

            # Format admin notification
            user = update.effective_user
            chat_url = f"@{user.username}" if user.username else f"tg://user?id={user.id}"
            
            admin_text = (
                "📦 طلب جديد\n\n"
                f"👤 المستخدم: {user.full_name} ({user.id})\n"
                f"🔗 للتواصل: {chat_url}\n\n"
                f"{product_type} المنتج: {context.user_data['product_name']} {context.user_data['icon']}\n"
                f"{details}\n"
                f"📝 الـ ID: {user_id}\n"
                f"💰 السعر: {format_currency(price)} ل.س"
            )

            # Send notification to admin group
            await context.bot.send_message(
                chat_id=config.PURCHASE_GROUP_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد", callback_data=f"complete_order_{order_id}"),
                        InlineKeyboardButton("❌ رفض", callback_data=f"cancel_order_{order_id}")
                    ]
                ])
            )

            # Log the order
            await log_manager.log_action(
                context,
                action="New Order",
                details=f"Order ID: {order_id}\nProduct: {context.user_data['product_name']}\nPrice: {price}",
                user_id=update.effective_user.id,
                amount=price,
                level="info",
                notify_admin=False
            )

            context.user_data.clear()
            return ConversationHandler.END

        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                user_id=update.effective_user.id,
                custom_msg="Error processing purchase"
            )
            await update.message.reply_text("❌ حدث خطأ غير متوقع")
            return ConversationHandler.END

    async def confirm_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Confirm an order."""
        query = update.callback_query
        await query.answer()
        
        order_id = query.data.split('_')[2]
        admin_name = f"@{query.from_user.username}" if query.from_user.username else query.from_user.full_name

        try:
            # Get order details
            order = await db.get_order(order_id)
            if not order:
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ لم يتم العثور على الطلب"
                )
                return

            if order['status'] != 'pending':
                await query.edit_message_text(
                    f"{query.message.text}\n\n⚠️ تم معالجة هذا الطلب مسبقاً"
                )
                return

            # Update order status
            if not await db.update_order_status(order_id, 'completed', query.from_user.id):
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ حدث خطأ أثناء تأكيد الطلب"
                )
                return

            # Update message
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"✅ تم التأكيد بواسطة {admin_name}\n"
                f"⏰ {get_damascus_time()}"
            )

            # Notify user
            product = self.get_product_details(
                order['product_type'], 
                order['product_id']
            )
            
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=(
                    "✅ تم تنفيذ طلبك بنجاح\n\n"
                    f"🎮 المنتج: {product['name']} {product['icon']}\n"
                    f"📝 الـ ID: {order['game_id']}\n"
                    "💎 شكراً لثقتك بمتجر الدايموند"
                )
            )

            # Log the action
            await log_manager.log_action(
                context,
                action="Order Confirmed",
                details=f"Order ID: {order_id}\nProduct: {product['name']}\nConfirmed by: {admin_name}",
                user_id=order['user_id'],
                level="info",
                notify_admin=False
            )

        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                custom_msg=f"Error confirming order {order_id}"
            )
            await query.edit_message_text(
                f"{query.message.text}\n\n❌ حدث خطأ غير متوقع"
            )

    async def reject_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reject an order and refund the user."""
        query = update.callback_query
        await query.answer()
        
        order_id = query.data.split('_')[2]
        admin_name = f"@{query.from_user.username}" if query.from_user.username else query.from_user.full_name

        try:
            # Get order details
            order = await db.get_order(order_id)
            if not order:
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ لم يتم العثور على الطلب"
                )
                return

            if order['status'] != 'pending':
                await query.edit_message_text(
                    f"{query.message.text}\n\n⚠️ تم معالجة هذا الطلب مسبقاً"
                )
                return

            # Refund user and update order status
            if not await db.reject_order(order_id, query.from_user.id):
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ حدث خطأ أثناء رفض الطلب"
                )
                return

            # Update message
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"❌ تم الرفض بواسطة {admin_name}\n"
                f"⏰ {get_damascus_time()}"
            )

            # Notify user
            product = self.get_product_details(
                order['product_type'], 
                order['product_id']
            )
            
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=(
                    "❌ تم رفض طلبك\n\n"
                    f"🎮 المنتج: {product['name']} {product['icon']}\n"
                    f"📝 الـ ID: {order['game_id']}\n"
                    f"💰 تم إرجاع {format_currency(order['price'])} ل.س إلى رصيدك"
                )
            )

            # Log the action
            await log_manager.log_action(
                context,
                action="Order Rejected",
                details=f"Order ID: {order_id}\nProduct: {product['name']}\nRejected by: {admin_name}",
                user_id=order['user_id'],
                amount=order['price'],
                level="info",
                notify_admin=False
            )

        except Exception as e:
            await log_manager.log_error(
                context,
                error=e,
                custom_msg=f"Error rejecting order {order_id}"
            )
            await query.edit_message_text(
                f"{query.message.text}\n\n❌ حدث خطأ غير متوقع"
            )

# Create singleton instance
_purchase_manager = None

def get_purchase_manager(game_products: Dict[str, Any] = None, 
                       app_products: Dict[str, Any] = None) -> PurchaseManager:
    """Get the PurchaseManager instance."""
    global _purchase_manager
    if _purchase_manager is None:
        if game_products is None or app_products is None:
            raise ValueError("Products must be provided for first initialization")
        _purchase_manager = PurchaseManager(game_products, app_products)
    return _purchase_manager