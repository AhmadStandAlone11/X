import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)
from telegram.helpers import escape_markdown

from config import get_config
from keyboards import Keyboards
from utils import format_currency
from database import get_database
from log_manager import get_log_manager
from product_manager import ProductManager  # تم التعديل هنا

# Initialize components
config = get_config()
db = get_database()
log_manager = get_log_manager()
keyboards = Keyboards()
product_manager = ProductManager() # تم التعديل هنا

# States for product management
(
    WAITING_FOR_PRODUCT_ID,
    WAITING_FOR_PRODUCT_NAME,
    WAITING_FOR_PRODUCT_ICON,
    WAITING_FOR_PACKAGE_INFO,
    WAITING_FOR_PRICE,
    WAITING_FOR_PACKAGE_SIZE,
    WAITING_FOR_CONFIRM,
    SELECTING_PRODUCT_TO_UPDATE,
    SELECTING_PACKAGE_TO_UPDATE,
    UPDATING_PACKAGE_PRICE,
    CONFIRMING_DELETE
) = range(11)

async def edit_prices_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the main product management menu."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("🎮 الألعاب", callback_data="manage_games"),
            InlineKeyboardButton("📱 التطبيقات", callback_data="manage_apps")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]

    await query.message.edit_text(
        "🛠 إدارة المنتجات\n\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def manage_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show management options for a category."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_')[1]
    context.user_data['category'] = category
    
    products = product_manager.get_all_products(category)[category]
    
    keyboard = []
    for product_id, product in products.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{product['icon']} {product['name']}",
                callback_data=f"edit_{category}_{product_id}"
            )
        ])
    
    keyboard.extend([
        [InlineKeyboardButton("➕ إضافة منتج جديد", callback_data=f"add_{category}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="edit_prices")]
    ])

    category_name = "الألعاب" if category == "games" else "التطبيقات"
    await query.message.edit_text(
        f"🛠 إدارة {category_name}\n\n"
        "اختر المنتج الذي تريد تعديله أو أضف منتجاً جديداً:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_PRODUCT_TO_UPDATE

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of adding a new product."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_')[1]
    context.user_data['category'] = category
    
    await query.message.edit_text(
        "🆕 إضافة منتج جديد\n\n"
        "أدخل معرف المنتج (بالإنجليزية فقط، مثال: pubg):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
        ]])
    )
    return WAITING_FOR_PRODUCT_ID

async def handle_product_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the product ID input."""
    product_id = update.message.text.strip().lower()
    category = context.user_data['category']
    
    # Validate product ID
    if not product_id.isalnum():
        await update.message.reply_text(
            "❌ معرف المنتج يجب أن يحتوي على أحرف وأرقام فقط\n"
            "حاول مرة أخرى:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
            ]])
        )
        return WAITING_FOR_PRODUCT_ID
    
    # Check if product exists
    if product_manager.get_product(category, product_id):
        await update.message.reply_text(
            "❌ هذا المعرف مستخدم بالفعل\n"
            "أدخل معرفاً آخر:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
            ]])
        )
        return WAITING_FOR_PRODUCT_ID
    
    context.user_data['product_id'] = product_id
    await update.message.reply_text(
        "✅ تم حفظ المعرف\n\n"
        "أدخل اسم المنتج:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
        ]])
    )
    return WAITING_FOR_PRODUCT_NAME

async def handle_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the product name input."""
    product_name = update.message.text.strip()
    category = context.user_data['category']
    
    context.user_data['name'] = product_name
    await update.message.reply_text(
        "✅ تم حفظ الاسم\n\n"
        "أدخل رمز المنتج (إيموجي):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
        ]])
    )
    return WAITING_FOR_PRODUCT_ICON

async def handle_product_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the product icon input."""
    icon = update.message.text.strip()
    category = context.user_data['category']
    
    context.user_data['icon'] = icon
    
    if category == 'games':
        await update.message.reply_text(
            "✅ تم حفظ الرمز\n\n"
            "أدخل معلومات الباقات بالتنسيق التالي:\n"
            "اسم الباقة | السعر\n"
            "مثال:\n"
            "60 UC | 9500\n"
            "120 UC | 19000\n\n"
            "أدخل كل باقة في سطر منفصل:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
            ]])
        )
        return WAITING_FOR_PACKAGE_INFO
    else:
        await update.message.reply_text(
            "✅ تم حفظ الرمز\n\n"
            "أدخل حجم الباقة:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")
            ]])
        )
        return WAITING_FOR_PACKAGE_SIZE

async def handle_package_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the app package size input."""
    try:
        package_size = int(update.message.text.strip())
        context.user_data['package_size'] = package_size
        
        await update.message.reply_text(
            "✅ تم حفظ حجم الباقة\n\n"
            "أدخل سعر الباقة:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="manage_apps")
            ]])
        )
        return WAITING_FOR_PRICE
        
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح\n"
            "حاول مرة أخرى:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="manage_apps")
            ]])
        )
        return WAITING_FOR_PACKAGE_SIZE

async def handle_package_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the game packages input."""
    try:
        packages_text = update.message.text.strip()
        packages = []
        
        for line in packages_text.split('\n'):
            if not line.strip():
                continue
            name, price = line.split('|')
            packages.append([name.strip(), float(price.strip())])
        
        context.user_data['packages'] = packages
        
        # Show confirmation
        category = context.user_data['category']
        product_id = context.user_data['product_id']
        
        confirm_text = (
            "📝 مراجعة المعلومات:\n\n"
            f"المعرف: {product_id}\n"
            f"الاسم: {context.user_data['name']}\n"
            f"الرمز: {context.user_data['icon']}\n\n"
            "الباقات:\n"
        )
        
        for package in packages:
            confirm_text += f"• {package[0]} - {format_currency(package[1])} ل.س\n"
        
        confirm_text += "\nهل تريد حفظ المنتج؟"
        
        await update.message.reply_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ حفظ", callback_data="confirm_add"),
                    InlineKeyboardButton("❌ إلغاء", callback_data=f"manage_{category}")
                ]
            ])
        )
        return WAITING_FOR_CONFIRM
        
    except Exception as e:
        await update.message.reply_text(
            "❌ تنسيق غير صحيح\n"
            "الرجاء استخدام التنسيق التالي:\n"
            "اسم الباقة | السعر\n"
            "مثال:\n"
            "60 UC | 9500\n"
            "حاول مرة أخرى:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="manage_games")
            ]])
        )
        return WAITING_FOR_PACKAGE_INFO

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the app price input."""
    try:
        price = float(update.message.text.strip())
        context.user_data['price'] = price
        
        # Show confirmation
        product_id = context.user_data['product_id']
        
        confirm_text = (
            "📝 مراجعة المعلومات:\n\n"
            f"المعرف: {product_id}\n"
            f"الاسم: {context.user_data['name']}\n"
            f"الرمز: {context.user_data['icon']}\n"
            f"حجم الباقة: {context.user_data['package_size']}\n"
            f"السعر: {format_currency(price)} ل.س\n\n"
            "هل تريد حفظ المنتج؟"
        )
        
        await update.message.reply_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ حفظ", callback_data="confirm_add"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="manage_apps")
                ]
            ])
        )
        return WAITING_FOR_CONFIRM
        
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح\n"
            "حاول مرة أخرى:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="manage_apps")
            ]])
        )
        return WAITING_FOR_PRICE

async def confirm_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product addition confirmation."""
    query = update.callback_query
    await query.answer()
    
    category = context.user_data['category']
    product_id = context.user_data['product_id']
    
    product_data = {
        'name': context.user_data['name'],
        'icon': context.user_data['icon']
    }
    
    if category == 'games':
        product_data['packages'] = context.user_data['packages']
    else:
        product_data.update({
            'package_size': context.user_data['package_size'],
            'price': context.user_data['price']
        })
    
    if product_manager.add_product(category, product_id, product_data):
        await query.message.edit_text(
            "✅ تم إضافة المنتج بنجاح"
        )
        
        # Log the action
        await log_manager.log_action(
            context,
            action="Product Added",
            details=f"Category: {category}\nProduct: {product_id}",
            level="info",
            notify_admin=True
        )
    else:
        await query.message.edit_text(
            "❌ حدث خطأ أثناء إضافة المنتج"
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product editing."""
    query = update.callback_query
    await query.answer()
    
    category, product_id = query.data.split('_')[1:]
    product = product_manager.get_product(category, product_id)
    
    if not product:
        await query.message.edit_text("❌ المنتج غير موجود")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("✏️ تعديل الأسعار", callback_data=f"edit_prices_{category}_{product_id}")],
        [InlineKeyboardButton("🗑 حذف المنتج", callback_data=f"delete_{category}_{product_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")]
    ]
    
    await query.message.edit_text(
        f"🛠 إدارة {product['name']} {product['icon']}\n\n"
        "اختر العملية المطلوبة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

async def edit_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle price editing menu."""
    query = update.callback_query
    await query.answer()
    
    _, category, product_id = query.data.split('_')[1:]
    product = product_manager.get_product(category, product_id)
    
    if not product:
        await query.message.edit_text("❌ المنتج غير موجود")
        return ConversationHandler.END
    
    context.user_data.update({
        'category': category,
        'product_id': product_id
    })
    
    if category == 'games':
        keyboard = []
        for i, package in enumerate(product['packages']):
            keyboard.append([
                InlineKeyboardButton(
                    f"{package[0]} - {format_currency(package[1])} ل.س",
                    callback_data=f"update_package_{i}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"edit_{category}_{product_id}")])
        
        await query.message.edit_text(
            f"💰 تعديل أسعار {product['name']}\n\n"
            "اختر الباقة المراد تعديل سعرها:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_PACKAGE_TO_UPDATE
    else:
        await query.message.edit_text(
            f"💰 تعديل سعر {product['name']}\n\n"
            f"السعر الحالي: {format_currency(product['price'])} ل.س\n\n"
            "أدخل السعر الجديد:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"edit_{category}_{product_id}")
            ]])
        )
        return UPDATING_PACKAGE_PRICE

async def update_package_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle package price update."""
    try:
        new_price = float(update.message.text.strip())
        category = context.user_data['category']
        product_id = context.user_data['product_id']
        
        if 'package_index' in context.user_data:  # For games
            package_index = context.user_data['package_index']
            if product_manager.update_game_package_price(product_id, package_index, new_price):
                success = True
            else:
                success = False
        else:  # For apps
            if product_manager.update_app_price(product_id, new_price):
                success = True
            else:
                success = False
        
        if success:
            await update.message.reply_text(
                "✅ تم تحديث السعر بنجاح"
            )
            # Log the action
            await log_manager.log_action(
                context,
                action="Price Updated",
                details=f"Category: {category}\nProduct: {product_id}\nNew Price: {new_price}",
                level="info",
                notify_admin=True
            )
        else:
            await update.message.reply_text(
                "❌ حدث خطأ أثناء تحديث السعر"
            )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح\n"
            "حاول مرة أخرى:"
        )
        return UPDATING_PACKAGE_PRICE

async def confirm_delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product deletion confirmation."""
    query = update.callback_query
    await query.answer()
    
    _, category, product_id = query.data.split('_')[1:]
    product = product_manager.get_product(category, product_id)
    
    if not product:
        await query.message.edit_text("❌ المنتج غير موجود")
        return ConversationHandler.END
    
    await query.message.edit_text(
        f"⚠️ هل أنت متأكد من حذف {product['name']} {product['icon']}؟\n"
        "هذا الإجراء لا يمكن التراجع عنه!",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_delete_{category}_{product_id}"),
                InlineKeyboardButton("❌ لا، إلغاء", callback_data=f"edit_{category}_{product_id}")
            ]
        ])
    )
    return CONFIRMING_DELETE

async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product deletion."""
    query = update.callback_query
    await query.answer()
    
    _, category, product_id = query.data.split('_')[1:]
    
    if product_manager.delete_product(category, product_id):
        await query.message.edit_text("✅ تم حذف المنتج بنجاح")
        
        # Log the action
        await log_manager.log_action(
            context,
            action="Product Deleted",
            details=f"Category: {category}\nProduct: {product_id}",
            level="warning",
            notify_admin=True
        )
    else:
        await query.message.edit_text("❌ حدث خطأ أثناء حذف المنتج")
    
    return ConversationHandler.END

def get_product_management_handler() -> ConversationHandler:
    """Get the conversation handler for product management."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_prices_menu, pattern=r"^edit_prices$"),
            CallbackQueryHandler(manage_category, pattern=r"^manage_(games|apps)$")
        ],
        states={
            SELECTING_PRODUCT_TO_UPDATE: [
                CallbackQueryHandler(add_product_start, pattern=r"^add_(games|apps)$"),
                CallbackQueryHandler(edit_product, pattern=r"^edit_(games|apps)_\w+$"),
                CallbackQueryHandler(edit_prices_menu, pattern="^edit_prices$")
            ],
            WAITING_FOR_PRODUCT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_id)
            ],
            WAITING_FOR_PRODUCT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_name)
            ],
            WAITING_FOR_PRODUCT_ICON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_icon)
            ],
            WAITING_FOR_PACKAGE_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_package_info)
            ],
            WAITING_FOR_PACKAGE_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_package_size)
            ],
                        WAITING_FOR_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)
            ],
            WAITING_FOR_CONFIRM: [
                CallbackQueryHandler(confirm_add_product, pattern="^confirm_add$")
            ],
            SELECTING_PACKAGE_TO_UPDATE: [
                CallbackQueryHandler(
                    lambda u, c: handle_package_selection(u, c),
                    pattern=r"^update_package_\d+$"
                )
            ],
            UPDATING_PACKAGE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, update_package_price)
            ],
            CONFIRMING_DELETE: [
                CallbackQueryHandler(
                    delete_product,
                    pattern=r"^confirm_delete_(games|apps)_\w+$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(edit_prices_menu, pattern="^edit_prices$"),
            CallbackQueryHandler(
                lambda u, c: manage_category(u, c), 
                pattern=r"^manage_(games|apps)$"
            ),
        ],
        name="product_management",
        persistent=True
    )

async def handle_package_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle package selection for price update."""
    query = update.callback_query
    await query.answer()
    
    package_index = int(query.data.split('_')[2])
    category = context.user_data['category']
    product_id = context.user_data['product_id']
    
    product = product_manager.get_product(category, product_id)
    if not product:
        await query.message.edit_text("❌ المنتج غير موجود")
        return ConversationHandler.END
    
    context.user_data['package_index'] = package_index
    
    if category == 'games':
        package = product['packages'][package_index]
        await query.message.edit_text(
            f"💰 تعديل سعر باقة {package[0]}\n\n"
            f"السعر الحالي: {format_currency(package[1])} ل.س\n\n"
            "أدخل السعر الجديد:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"edit_{category}_{product_id}")
            ]])
        )
    else:
        await query.message.edit_text(
            f"💰 تعديل سعر {product['name']}\n\n"
            f"السعر الحالي: {format_currency(product['price'])} ل.س\n\n"
            "أدخل السعر الجديد:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data=f"edit_{category}_{product_id}")
            ]])
        )
    
    return UPDATING_PACKAGE_PRICE

# Public shop handlers

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the shop callback."""
    query = update.callback_query
    await query.answer()

    await query.message.edit_text(
        "🛒 اختر القسم:",
        reply_markup=keyboards.shop_menu()
    )
    return ConversationHandler.END

async def games_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the games callback."""
    query = update.callback_query
    await query.answer()

    products = product_manager.get_all_products('games')['games']
    
    buttons = []
    for product_id, product in products.items():
        buttons.append([
            InlineKeyboardButton(
                f"{product['icon']} {product['name']}",
                callback_data=f"game_packages_{product_id}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="shop")])

    await query.message.edit_text(
        "🎮 اختر اللعبة:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END

async def apps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the apps callback."""
    query = update.callback_query
    await query.answer()

    products = product_manager.get_all_products('apps')['apps']
    
    buttons = []
    for product_id, product in products.items():
        buttons.append([
            InlineKeyboardButton(
                f"{product['icon']} {product['name']}",
                callback_data=f"app_packages_{product_id}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="shop")])

    await query.message.edit_text(
        "📱 اختر التطبيق:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END

async def game_packages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the game packages callback."""
    query = update.callback_query
    await query.answer()

    product_id = query.data.split('_')[2]
    product = product_manager.get_product('games', product_id)
    
    if not product:
        await query.message.edit_text("❌ المنتج غير متوفر حالياً")
        return ConversationHandler.END

    buttons = []
    for i, package in enumerate(product['packages']):
        amount, price = package
        buttons.append([
            InlineKeyboardButton(
                f"{amount} - {format_currency(price)} ل.س",
                callback_data=f"buy_game_{product_id}_{i}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="games")])

    message_text = f"📦 {product['name']} {product['icon']}\n"
    if product.get('note'):
        message_text += f"\n{product['note']}\n"
    message_text += "\nاختر الباقة:"

    await query.message.edit_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END

async def app_packages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the app packages callback."""
    query = update.callback_query
    await query.answer()

    product_id = query.data.split('_')[2]
    product = product_manager.get_product('apps', product_id)
    
    if not product:
        await query.message.edit_text("❌ المنتج غير متوفر حالياً")
        return ConversationHandler.END

    price_per_unit = product['price'] / product['package_size']
    
    message_text = (
        f"📱 {product['name']} {product['icon']}\n\n"
        f"💎 كل {product['package_size']} = {format_currency(product['price'])} ل.س\n"
        f"💰 سعر الوحدة: {format_currency(price_per_unit)} ل.س\n"
        f"📦 الحد الأدنى للطلب: {product['package_size']}"
    )

    buttons = [
        [InlineKeyboardButton("🛒 شراء", callback_data=f"buy_app_{product_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="apps")]
    ]

    await query.message.edit_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's balance."""
    try:
        user_id = update.effective_user.id
        balance = await db.get_user_balance(user_id)
        
        text = f"💳 رصيدك الحالي: {format_currency(balance)} ل.س"
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
            
    except Exception as e:
        await log_manager.log_error(
            context,
            error=e,
            user_id=update.effective_user.id,
            custom_msg="Error showing balance"
        )
        
        error_text = "❌ حدث خطأ أثناء عرض الرصيد"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(error_text)
        else:
            await update.message.reply_text(error_text)

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's order history."""
    try:
        user_id = update.effective_user.id
        orders = await db.get_user_orders(user_id)
        
        if not orders:
            text = "📦 لا يوجد لديك طلبات سابقة"
        else:
            text = "📦 طلباتك السابقة:\n\n"
            for order in orders:
                product = product_manager.get_product(
                    order['product_type'],
                    order['product_id']
                )
                
                if product:
                    text += (
                        f"🔢 رقم الطلب: {order['order_id']}\n"
                        f"📦 المنتج: {product['name']} {product['icon']}\n"
                        f"💰 السعر: {format_currency(order['price'])} ل.س\n"
                        f"📝 الحالة: {order['status']}\n"
                        f"⏰ التاريخ: {order['created_at']}\n\n"
                    )
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
            
    except Exception as e:
        await log_manager.log_error(
            context,
            error=e,
            user_id=update.effective_user.id,
            custom_msg="Error showing orders"
        )
        
        error_text = "❌ حدث خطأ أثناء عرض الطلبات"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(error_text)
        else:
            await update.message.reply_text(error_text)
