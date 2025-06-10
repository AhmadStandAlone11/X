from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional

class Keyboards:
    """Enhanced keyboard manager with improved organization and flexibility."""
    
    
    @staticmethod
    def subscription_keyboard() -> InlineKeyboardMarkup:
        """Create a beautiful subscription keyboard."""
        buttons = [
            [
                InlineKeyboardButton(
                    "🌟 اشترك في قناتنا الرسمية",
                    url="https://t.me/{FORCED_CHANNEL_USERNAME}"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ تحقق من الاشتراك",
                    callback_data="check_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    "💎 متجر الدايموند",
                    url="https://t.me/diamond_store_sy_bot"
                )
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def force_subscription() -> InlineKeyboardMarkup:
        """Keyboard for forcing subscription."""
        buttons = [
            [
                InlineKeyboardButton(
                    "📢 اشترك الآن",
                    url="https://t.me/{FORCED_CHANNEL_USERNAME}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 تحديث",
                    callback_data="check_subscription"
                )
            ]
        ]
        return InlineKeyboardMarkup(buttons)
    @staticmethod
    def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
        """Main menu keyboard with improved organization."""
        buttons = [
            [InlineKeyboardButton("💎 المتجر", callback_data="shop")],
            [InlineKeyboardButton("💰 شحن رصيد", callback_data="charge")],
            [
                InlineKeyboardButton("💳 رصيدي", callback_data="my_balance"),
                InlineKeyboardButton("📦 طلباتي", callback_data="my_orders")
            ]
        ]
        if is_admin:
            buttons.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def shop_menu() -> InlineKeyboardMarkup:
        """Shop menu keyboard."""
        buttons = [
            [
                InlineKeyboardButton("🎮 الألعاب", callback_data="games"),
                InlineKeyboardButton("📱 التطبيقات", callback_data="apps")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def payment_methods() -> InlineKeyboardMarkup:
        """Enhanced payment methods keyboard with new payment options."""
        buttons = [
            # Cryptocurrency options
            [InlineKeyboardButton("💎 USDT/USD", callback_data="pay_type_crypto")],
            # Mobile payment options
            [
                InlineKeyboardButton("📱 سيرياتيل كاش", callback_data="pay_type_syriatel"),
                InlineKeyboardButton("📱 MTN كاش", callback_data="pay_type_mtn")
            ],
            # Sham Cash
            [InlineKeyboardButton("💰 شام كاش", callback_data="pay_type_shamcash")],
            # Back button
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def crypto_payment_options() -> InlineKeyboardMarkup:
        """Cryptocurrency payment options keyboard."""
        buttons = [
            [
                InlineKeyboardButton("💰 Coinex (USDT)", callback_data="pay_crypto_coinex"),
                InlineKeyboardButton("💰 CWallet (USDT)", callback_data="pay_crypto_cwallet")
            ],
            [
                InlineKeyboardButton("💵 Payeer (USD)", callback_data="pay_crypto_payeer"),
                InlineKeyboardButton("💰 PEB20 (USDT)", callback_data="pay_crypto_peb20")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="charge")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def shamcash_options() -> InlineKeyboardMarkup:
        """Sham Cash payment options keyboard."""
        buttons = [
            [
                InlineKeyboardButton("💵 تحويل ليرة سوري", callback_data="sham_syp"),
                InlineKeyboardButton("💰 تحويل USD", callback_data="sham_usd")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="charge")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def admin_panel() -> InlineKeyboardMarkup:
        """Enhanced admin panel keyboard."""
        buttons = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [
                InlineKeyboardButton("👥 المستخدمين", callback_data="manage_users"),
                InlineKeyboardButton("💰 المنتجات", callback_data="manage_products")
            ],
            [
                InlineKeyboardButton("💳 طلبات الشحن", callback_data="admin_recharges"),
                InlineKeyboardButton("📦 الطلبات", callback_data="admin_orders")
            ],
            [
                InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin_settings"),
                InlineKeyboardButton("💱 أسعار الصرف", callback_data="admin_rates")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def manage_products() -> InlineKeyboardMarkup:
        """Product management keyboard."""
        buttons = [
            [
                InlineKeyboardButton("🎮 الألعاب", callback_data="manage_games"),
                InlineKeyboardButton("📱 التطبيقات", callback_data="manage_apps")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def product_management(product_id: str, category: str) -> InlineKeyboardMarkup:
        """Individual product management keyboard."""
        buttons = [
            [InlineKeyboardButton("✏️ تعديل المعلومات", callback_data=f"edit_info_{category}_{product_id}")],
            [InlineKeyboardButton("💰 تعديل الأسعار", callback_data=f"edit_prices_{category}_{product_id}")],
            [InlineKeyboardButton("🗑 حذف المنتج", callback_data=f"delete_{category}_{product_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"manage_{category}")]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def confirm_action(action: str, data: str) -> InlineKeyboardMarkup:
        """Generic confirmation keyboard."""
        buttons = [
            [
                InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_{action}_{data}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{action}_{data}")
            ]
        ]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def back_button(callback_data: str) -> InlineKeyboardMarkup:
        """Generic back button."""
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=callback_data)
        ]])

    @staticmethod
    def user_contact(user_id: int, username: Optional[str] = None) -> InlineKeyboardMarkup:
        """Enhanced user contact button."""
        if username:
            url = f"https://t.me/{username}"
            buttons = [[InlineKeyboardButton("💬 تواصل", url=url)]]
        else:
            url = f"tg://user?id={user_id}"
            buttons = [[InlineKeyboardButton("💬 تواصل", url=url)]]
        return InlineKeyboardMarkup(buttons)
    
    
def get_start_keyboard(self) -> InlineKeyboardMarkup:
    """Get the start keyboard."""
    return self.main_menu()

def get_admin_keyboard(self) -> InlineKeyboardMarkup:
    """Get admin panel keyboard."""
    return self.admin_panel()

def get_cancel_keyboard(self) -> InlineKeyboardMarkup:
    """Get cancel keyboard."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel")
    ]])