import os
from dotenv import load_dotenv
from typing import Optional, Dict
from decimal import Decimal

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

class Config:
    """
    إعدادات التكوين الخاصة بالبوت.

    هذا الكلاس يستخدم نمط Singleton لضمان وجود نسخة واحدة فقط من الإعدادات.
    """

    _instance = None  # النسخة الوحيدة من الكلاس

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if self.__initialized:
            return
        self.__initialized = True
        
        # تحميل جميع متغيرات البيئة
        self._load_env_vars()

    def _load_env_vars(self):
        """
        تحميل جميع متغيرات البيئة مع تحويل الأنواع المناسبة.
        """
        # تكوين البوت
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')  # رمز البوت من Telegram
        self.BOT_USERNAME = os.getenv('BOT_USERNAME', 'diamond_store_sy_bot')  # اسم مستخدم البوت
        self.SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME')  # اسم مستخدم الدعم الفني

        # تكوين المسؤول
        self.OWNER_ID = int(os.getenv('OWNER_ID', '1631827811'))  # معرف مالك البوت
        self.ADMINS = [int(x) for x in os.getenv('ADMINS', str(self.OWNER_ID)).split(',')]  # قائمة بمعرفات المسؤولين

        # تكوين القناة
        self.FORCED_CHANNEL_ID = int(os.getenv('FORCED_CHANNEL_ID', '-1001234567890'))  # معرف القناة الإجبارية
        self.FORCED_CHANNEL_USERNAME = os.getenv('FORCED_CHANNEL_USERNAME', 'example_channel')  # اسم مستخدم القناة الإجبارية

        # تكوين المجموعة
        self.RECHARGE_GROUP_ID = int(os.getenv('RECHARGE_GROUP_ID', '-1001234567890'))  # معرف مجموعة الشحن
        self.PURCHASE_GROUP_ID = int(os.getenv('PURCHASE_GROUP_ID', '-1001234567890'))  # معرف مجموعة الشراء

        # تكوين سعر الصرف
        self.USD_RATE = Decimal(os.getenv('USD_RATE', '10000'))  # سعر صرف الدولار
        self.USDT_RATE = Decimal(os.getenv('USDT_RATE', '10000'))  # سعر صرف USDT

        # تكوين الدفع
        self.SYRIATEL_CASH_NUMBERS = [
            num.strip() for num in os.getenv('SYRIATEL_CASH_NUMBERS', '').split(',') if num.strip()
        ]  # أرقام سيرياتيل كاش
        self.USDT_WALLET_COINEX = os.getenv('USDT_WALLET_COINEX')  # محفظة USDT على Coinex
        self.USDT_WALLET_CWALLET = os.getenv('USDT_WALLET_CWALLET')  # محفظة USDT على CWallet
        self.USD_WALLET_PAYEER = os.getenv('USD_WALLET_PAYEER')  # محفظة USD على Payeer
        self.USDT_WALLET_PEB20 = os.getenv('USDT_WALLET_PEB20')  # محفظة USDT على PEB20
        self.MTN_CASH_NUMBERS = [num.strip() for num in os.getenv('MTN_CASH_NUMBERS', '').split(',')]  # أرقام MTN كاش
        self.SHAMCASH_NUMBERS = [num.strip() for num in os.getenv('SHAMCASH_NUMBERS', '').split(',')]  # أرقام شام كاش

        # تكوين قاعدة البيانات
        self.DB_PATH = "diamond_store.db"  # مسار قاعدة البيانات

    def reload_config(self) -> bool:
        """
        إعادة تحميل جميع التكوينات من متغيرات البيئة.
        """
        try:
            load_dotenv(override=True)
            self._load_env_vars()
            return True
        except Exception as e:
            print(f"Error reloading config: {e}")
            return False

    def update_usd_rate(self, new_rate: str) -> bool:
        """
        تحديث سعر صرف الدولار بشكل فوري.
        """
        try:
            if self._update_env_variable('USD_RATE', new_rate):
                self.USD_RATE = Decimal(new_rate)
                return True
            return False
        except (ValueError, TypeError) as e:
            print(f"Error updating USD rate: {e}")
            return False

    def update_usdt_rate(self, new_rate: str) -> bool:
        """
        تحديث سعر صرف USDT بشكل فوري.
        """
        try:
            if self._update_env_variable('USDT_RATE', new_rate):
                self.USDT_RATE = Decimal(new_rate)
                return True
            return False
        except (ValueError, TypeError) as e:
            print(f"Error updating USDT rate: {e}")
            return False

    def update_syriatel_numbers(self, numbers: list[str]) -> bool:
        """
        تحديث أرقام سيرياتيل كاش بشكل فوري.
        """
        try:
            numbers = [num.strip() for num in numbers if num.strip()]
            numbers_str = ','.join(numbers)
            if self._update_env_variable('SYRIATEL_CASH_NUMBERS', numbers_str):
                self.SYRIATEL_CASH_NUMBERS = numbers
                return True
            return False
        except Exception as e:
            print(f"Error updating Syriatel numbers: {e}")
            return False

    def update_usdt_wallets(self, wallets: Dict[str, str]) -> bool:
        """
        تحديث محافظ USDT بشكل فوري.
        """
        try:
            success = True
            updates = {
                'USDT_WALLET_COINEX': ('coinex', self.USDT_WALLET_COINEX),
                'USDT_WALLET_CWALLET': ('cwallet', self.USDT_WALLET_CWALLET),
                'USD_WALLET_PAYEER': ('payeer', self.USD_WALLET_PAYEER),
                'USDT_WALLET_PEB20': ('peb20', self.USDT_WALLET_PEB20)
            }
            
            for env_var, (key, attr) in updates.items():
                if key in wallets:
                    if self._update_env_variable(env_var, wallets[key]):
                        setattr(self, env_var, wallets[key])
                    else:
                        success = False
            
            return success
        except Exception as e:
            print(f"Error updating USDT wallets: {e}")
            return False

    def update_mtn_numbers(self, numbers: list[str]) -> bool:
        """
        تحديث أرقام MTN كاش.
        """
        try:
            numbers_str = ','.join(num.strip() for num in numbers if num.strip())
            if self._update_env_variable('MTN_CASH_NUMBERS', numbers_str):
                self.MTN_CASH_NUMBERS = numbers
                return True
            return False
        except Exception as e:
            print(f"Error updating MTN numbers: {e}")
            return False

    def update_shamcash_numbers(self, numbers: list[str]) -> bool:
        """
        تحديث أرقام شام كاش.
        """
        try:
            numbers_str = ','.join(num.strip() for num in numbers if num.strip())
            if self._update_env_variable('SHAMCASH_NUMBERS', numbers_str):
                self.SHAMCASH_NUMBERS = numbers
                return True
            return False
        except Exception as e:
            print(f"Error updating Sham Cash numbers: {e}")
            return False
    
    def _update_env_variable(self, variable_name: str, new_value: str) -> bool:
        """
        تحديث متغير بيئة مع معالجة الأخطاء المحسنة.
        """
        try:
            dotenv_path = '.env'
            
            # قراءة المحتويات الحالية
            if not os.path.exists(dotenv_path):
                with open(dotenv_path, 'w', encoding='utf-8') as f:
                    f.write(f"{variable_name}={new_value}\n")
                os.environ[variable_name] = new_value
                return True

            with open(dotenv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # تحديث أو إضافة المتغير
            updated = False
            new_lines = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    if line.startswith(f"{variable_name}="):
                        new_lines.append(f"{variable_name}={new_value}\n")
                        updated = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            if not updated:
                new_lines.append(f"{variable_name}={new_value}\n")

            # الكتابة مرة أخرى إلى الملف
            with open(dotenv_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

            # تحديث متغير البيئة في الذاكرة
            os.environ[variable_name] = new_value
            return True

        except Exception as e:
            print(f"Error updating {variable_name} in .env: {e}")
            return False


_config = Config()  # إنشاء نسخة واحدة

def get_config() -> Config:
    """
    الحصول على نسخة Config مع تلميح النوع المناسب.
    """
    return _config