import os
import time
import sqlite3
import logging
import shutil
import json
from typing import Optional, Dict, List
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# استيراد Config للتحقق من المسؤول
from config import get_config

# تحميل متغيرات البيئة
load_dotenv()

# الثوابت
DB_PATH = "diamond_store.db"
DAMASCUS_TZ = timezone(timedelta(hours=3))

# إعداد المسجل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# محولات التاريخ والوقت لـ SQLite
def adapt_datetime(dt):
    """تحويل datetime إلى تنسيق متوافق مع SQLite."""
    return dt.isoformat()

def convert_datetime(text):
    """تحويل النص من SQLite إلى datetime."""
    return datetime.fromisoformat(text)

# تسجيل المحولات
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

class Database:
    """
    كلاس إدارة قاعدة البيانات مع معالجة محسنة للأخطاء وإدارة الاتصال.

    هذا الكلاس يستخدم نمط Singleton لضمان وجود نسخة واحدة فقط من قاعدة البيانات.
    """
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        """تهيئة قاعدة البيانات إذا لم تكن مهيأة بالفعل."""
        if not self.initialized:
            self.initialized = True
            self.init_db()

    def get_connection(self):
        """إنشاء اتصال بقاعدة البيانات مع إعدادات محسنة."""
        for i in range(5):  # إعادة محاولة الاتصال 5 مرات
            try:
                conn = sqlite3.connect(
                    DB_PATH,
                    timeout=30.0,
                    isolation_level=None,  # تمكين التحكم اليدوي في المعاملات
                    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
                )
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA busy_timeout=30000')
                conn.row_factory = sqlite3.Row  # تمكين row factory للأعمدة المسماة
                return conn
            except sqlite3.OperationalError as e:
                if i == 4:  # إذا فشلت جميع المحاولات
                    logger.error(f"Failed to connect to database after 5 attempts: {e}")
                    raise
                time.sleep(1)  # الانتظار قبل إعادة المحاولة

    def init_db(self):
        """تهيئة قاعدة البيانات بجميع الجداول المطلوبة."""
        try:
            # إنشاء دليل النسخ الاحتياطي إذا لم يكن موجودًا
            os.makedirs('backup', exist_ok=True)

            # نسخ قاعدة البيانات الموجودة إذا كانت موجودة
            if os.path.exists(DB_PATH):
                backup_path = f'backup/diamond_store_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
                shutil.copy2(DB_PATH, backup_path)
                logger.info(f"Database backed up to {backup_path}")

            conn = self.get_connection()
            c = conn.cursor()

            # إنشاء الجداول مع إعدادات متقدمة
            c.executescript('''
                -- تمكين قيود المفتاح الخارجي
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;
                PRAGMA cache_size = -2000;

                -- جدول المستخدمين مع تتبع محسن
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance REAL DEFAULT 0.0 CHECK (balance >= 0),
                    joined_date TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'banned', 'suspended')),
                    account_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- سجل الرصيد مع تتبع محسن
                CREATE TABLE IF NOT EXISTS balance_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    old_balance REAL NOT NULL,
                    new_balance REAL NOT NULL,
                    change_amount REAL NOT NULL,
                    transaction_type TEXT NOT NULL,
                    admin_id INTEGER,  -- تمت إضافة admin_id لتتبع من قام بالتغيير
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                -- جدول الطلبات مع تتبع محسن
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_type TEXT NOT NULL CHECK (product_type IN ('game', 'app')),
                    product_id TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'rejected', 'expired')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                -- جدول المعاملات مع تتبع محسن
                CREATE TABLE IF NOT EXISTS transactions (
                    tx_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('deposit', 'withdrawal')),
                    payment_method TEXT NOT NULL,
                    payment_details TEXT,
                    payment_subtype TEXT,  -- لـ شام كاش: 'syp' أو 'usd'
                    payment_number TEXT,   -- رقم الدفع بالدولار
                    original_amount REAL,
                    original_currency TEXT,
                    exchange_rate REAL,  -- تمت إضافة تتبع سعر الصرف
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'rejected', 'expired')),
                    reject_reason TEXT,
                    admin_id INTEGER,  -- تمت إضافة admin_id لتتبع من قام بمعالجة المعاملة
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                -- سجلات المسؤول مع تتبع مفصل
                CREATE TABLE IF NOT EXISTS admin_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    target_user_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (target_user_id) REFERENCES users(user_id) ON DELETE SET NULL
                );

                -- إنشاء فهارس للأداء
                CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
                CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
                CREATE INDEX IF NOT EXISTS idx_transactions_user_status ON transactions (user_id, status);
                CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders (user_id, status);
                CREATE INDEX IF NOT EXISTS idx_balance_history_user ON balance_history (user_id);
                CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs (admin_id);
            ''')

            conn.commit()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def is_admin(self, user_id: int) -> bool:
        """التحقق مما إذا كان المستخدم مسؤولاً."""
        config = get_config()
        return user_id in config.ADMINS

    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """الحصول على إحصائيات شاملة للمستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            # الحصول على معلومات المستخدم الأساسية
            c.execute("""
                SELECT balance, joined_date, last_activity, status,
                       created_at, username, first_name
                FROM users 
                WHERE user_id = ?
            """, (user_id,))
            user = c.fetchone()
            
            if not user:
                return None

            # الحصول على إحصائيات المعاملات
            c.execute("""
                SELECT 
                    COUNT(*) as total_tx,
                    COALESCE(SUM(CASE WHEN type = 'deposit' AND status = 'completed' THEN amount ELSE 0 END), 0) as deposits,
                    COALESCE(SUM(CASE WHEN type = 'withdrawal' AND status = 'completed' THEN amount ELSE 0 END), 0) as withdrawals
                FROM transactions 
                WHERE user_id = ?
            """, (user_id,))
            tx_stats = c.fetchone()

            # الحصول على إحصائيات الطلبات
            c.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END), 0) as total_spent
                FROM orders 
                WHERE user_id = ?
            """, (user_id,))
            order_stats = c.fetchone()

            return {
                'user_id': user_id,
                'username': user['username'],
                'first_name': user['first_name'],
                'current_balance': Decimal(str(user['balance'])),
                'join_date': datetime.fromisoformat(user['joined_date']),
                'last_active': datetime.fromisoformat(user['last_activity']),
                'is_banned': user['status'] == 'banned',
                'created_at': datetime.fromisoformat(user['created_at']),
                'total_transactions': tx_stats['total_tx'],
                'total_deposits': Decimal(str(tx_stats['deposits'])),
                'total_withdrawals': Decimal(str(tx_stats['withdrawals'])),
                'total_orders': order_stats['total_orders'],
                'total_spent': Decimal(str(order_stats['total_spent']))
            }

        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def ban_user(self, user_id: int, admin_id: int) -> bool:
        """حظر المستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # تحديث حالة المستخدم
            c.execute("""
                UPDATE users 
                SET status = 'banned', updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            
            if c.rowcount > 0:
                # تسجيل الإجراء
                c.execute("""
                    INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                    VALUES (?, 'ban_user', ?, ?)
                """, (admin_id, f"User {user_id} was banned", user_id))
                
                c.execute("COMMIT")
                return True
                
            c.execute("ROLLBACK")
            return False

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error banning user: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def unban_user(self, user_id: int, admin_id: int) -> bool:
        """إلغاء حظر المستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # تحديث حالة المستخدم
            c.execute("""
                UPDATE users 
                SET status = 'active', updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            
            if c.rowcount > 0:
                # تسجيل الإجراء
                c.execute("""
                    INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                    VALUES (?, 'unban_user', ?, ?)
                """, (admin_id, f"User {user_id} was unbanned", user_id))
                
                c.execute("COMMIT")
                return True
                
            c.execute("ROLLBACK")
            return False

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error unbanning user: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def modify_user_balance(self, user_id: int, amount: Decimal, admin_id: int) -> bool:
        """تعديل رصيد المستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # الحصول على الرصيد الحالي
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if not result:
                c.execute("ROLLBACK")
                return False
                
            current_balance = Decimal(str(result['balance']))
            new_balance = current_balance + amount
            
            # منع الرصيد السالب
            if new_balance < 0:
                c.execute("ROLLBACK")
                return False
            
            # تحديث الرصيد
            c.execute("""
                UPDATE users 
                SET balance = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (str(new_balance), user_id))
            
            # تسجيل التغيير
            c.execute("""
                INSERT INTO balance_history 
                (user_id, old_balance, new_balance, change_amount, transaction_type, admin_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, str(current_balance), str(new_balance), str(amount),
                  'credit' if amount > 0 else 'debit', admin_id))
            
            # تسجيل إجراء المسؤول
            c.execute("""
                INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                VALUES (?, 'modify_balance', ?, ?)
            """, (admin_id, f"Modified balance by {amount}", user_id))
            
            c.execute("COMMIT")
            return True

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error modifying balance: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def get_user_id_by_username(self, username: str) -> Optional[int]:
        """الحصول على معرف المستخدم من اسم المستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            username = username.lstrip('@')
            c.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = c.fetchone()
            return result['user_id'] if result else None

        except Exception as e:
            logger.error(f"Error getting user ID: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def get_total_users(self) -> int:
        """الحصول على العدد الإجمالي للمستخدمين."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as count FROM users")
            return c.fetchone()['count']
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    async def get_active_users_last_24h(self) -> int:
        """الحصول على عدد المستخدمين النشطين في آخر 24 ساعة."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE datetime(last_activity) > datetime('now', '-1 day')
                AND status = 'active'
            """)
            return c.fetchone()['count']
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    async def get_total_transaction_volume(self) -> Decimal:
        """الحصول على إجمالي حجم المعاملات."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT COALESCE(SUM(amount), 0) as total 
                FROM transactions 
                WHERE status = 'completed'
            """)
            return Decimal(str(c.fetchone()['total']))
        except Exception as e:
            logger.error(f"Error getting transaction volume: {e}")
            return Decimal('0')
     
    async def get_user_balance(self, user_id: int) -> Decimal:
        """الحصول على رصيد المستخدم الحالي."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            return Decimal(str(result['balance'])) if result else Decimal('0')
        except Exception as e:
            self.logger.error(f"Error getting user balance: {e}")
            return Decimal('0')
        finally:
            if conn:
                conn.close()

    async def get_order(self, order_id: str) -> Optional[Dict]:
        """الحصول على تفاصيل الطلب."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT * FROM orders 
                WHERE order_id = ?
            """, (order_id,))
            result = c.fetchone()
            return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error getting order: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def update_user_balance(self, user_id: int, amount: Decimal) -> bool:
        """تحديث رصيد المستخدم."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
        
            c.execute("BEGIN TRANSACTION")
        
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ? AND balance + ? >= 0
            """, (str(amount), user_id, str(amount)))
            
            if c.rowcount > 0:
                c.execute("COMMIT")
                return True
            
            c.execute("ROLLBACK")
            return False
        
        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            self.logger.error(f"Error updating balance: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def create_order(
        self,
        user_id: int,
        product_type: str,
        product_id: str,
        game_id: str,
        price: Decimal,
        quantity: int = 1
    ) -> Optional[int]:
        """إنشاء طلب جديد."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
        
            c.execute("BEGIN TRANSACTION")
        
            c.execute("""
                INSERT INTO orders (
                    user_id, product_type, product_id, amount,
                    price, created_at, status
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
                RETURNING order_id
            """, (user_id, product_type, product_id, game_id, str(price)))
         
            result = c.fetchone()
            if result:
                order_id = result['order_id']
                c.execute("COMMIT")
                return order_id
            
            c.execute("ROLLBACK")
            return None
        
        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            self.logger.error(f"Error creating order: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    async def create_transaction(
        self,
        tx_id: str,
        user_id: int,
        amount: Decimal,
        payment_method: str,
        payment_subtype: Optional[str] = None,
        payment_number: Optional[str] = None,
        **kwargs
    ) -> bool:
        """إنشاء معاملة جديدة مع تفاصيل محسنة."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
        
            c.execute("BEGIN TRANSACTION")
        
            c.execute("""
                INSERT INTO transactions (
                    tx_id, user_id, amount, type, payment_method,
                    payment_subtype, payment_number, payment_details,
                    original_amount, original_currency, exchange_rate,
                    created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
            """, (
                tx_id, user_id, str(amount), 'deposit', payment_method,
                payment_subtype, payment_number,
                json.dumps(kwargs.get('payment_details', {})),
                str(kwargs.get('original_amount', amount)),
                kwargs.get('original_currency', 'SYP'),
                str(kwargs.get('exchange_rate', 1))
            ))
        
            c.execute("COMMIT")
            return True
        
        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error creating transaction: {e}")
            return False
     
        finally:
            if conn:
                conn.close()

    async def get_transaction(self, tx_id: str) -> Optional[Dict]:
        """Get transaction details by transaction ID."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM transactions WHERE tx_id = ?", (tx_id,))
            result = c.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting transaction details: {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def confirm_transaction(self, tx_id: str, admin_id: int) -> bool:
        """Confirm a transaction."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # Get transaction details
            c.execute("SELECT user_id, amount FROM transactions WHERE tx_id = ?", (tx_id,))
            result = c.fetchone()
            if not result:
                c.execute("ROLLBACK")
                return False
                
            user_id = result['user_id']
            amount = Decimal(str(result['amount']))
            
            # Update transaction status
            c.execute("""
                UPDATE transactions 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    admin_id = ?
                WHERE tx_id = ?
            """, (admin_id, tx_id))
            
            # Update user balance
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (str(amount), user_id))
            
            # Log admin action
            c.execute("""
                INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                VALUES (?, 'confirm_transaction', ?, ?)
            """, (admin_id, f"Confirmed transaction {tx_id}", user_id))
            
            c.execute("COMMIT")
            return True

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error confirming transaction: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def reject_transaction(self, tx_id: str, admin_id: int, reason: str) -> bool:
        """Reject a transaction."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # Get transaction details
            c.execute("SELECT user_id, amount FROM transactions WHERE tx_id = ?", (tx_id,))
            result = c.fetchone()
            if not result:
                c.execute("ROLLBACK")
                return False
                
            user_id = result['user_id']
            amount = Decimal(str(result['amount']))
            
            # Update transaction status and add reject reason
            c.execute("""
                UPDATE transactions 
                SET status = 'rejected', reject_reason = ?, completed_at = CURRENT_TIMESTAMP,
                    admin_id = ?
                WHERE tx_id = ?
            """, (reason, admin_id, tx_id))
            
            # Refund user balance
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (str(amount), user_id))
            
            # Log admin action
            c.execute("""
                INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                VALUES (?, 'reject_transaction', ?, ?)
            """, (admin_id, f"Rejected transaction {tx_id} with reason: {reason}", user_id))
            
            c.execute("COMMIT")
            return True

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error rejecting transaction: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def get_user_orders(self, user_id: int) -> List[Dict]:
        """Get user's order history."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT * FROM orders 
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            
            orders = []
            for row in c.fetchall():
                orders.append(dict(row))
            return orders
            
        except Exception as e:
            logger.error(f"Error getting user orders: {e}")
            return []
        finally:
            if conn:
                conn.close()

    async def update_order_status(self, order_id: str, status: str, admin_id: int) -> bool:
        """Update order status."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # Update order status
            c.execute("""
                UPDATE orders 
                SET status = ?, completed_at = CURRENT_TIMESTAMP 
                WHERE order_id = ?
            """, (status, order_id))
            
            # Log admin action
            c.execute("""
                INSERT INTO admin_logs (admin_id, action, details)
                VALUES (?, 'update_order_status', ?)
            """, (admin_id, f"Updated order {order_id} to status {status}"))
            
            c.execute("COMMIT")
            return True

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error updating order status: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def reject_order(self, order_id: str, admin_id: int) -> bool:
        """Reject an order and refund the user."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # Get order details
            c.execute("SELECT user_id, price FROM orders WHERE order_id = ?", (order_id,))
            result = c.fetchone()
            if not result:
                c.execute("ROLLBACK")
                return False
                
            user_id = result['user_id']
            price = Decimal(str(result['price']))
            
            # Update order status
            c.execute("""
                UPDATE orders 
                SET status = 'rejected', completed_at = CURRENT_TIMESTAMP 
                WHERE order_id = ?
            """, (order_id,))
            
            # Refund user balance
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (str(price), user_id))
            
            # Log admin action
            c.execute("""
                INSERT INTO admin_logs (admin_id, action, details, target_user_id)
                VALUES (?, 'reject_order', ?, ?)
            """, (admin_id, f"Rejected order {order_id}", user_id))
            
            c.execute("COMMIT")
            return True

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error rejecting order: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    async def cleanup_expired_transactions(self, expiry_time: datetime) -> int:
        """Clean up expired pending transactions."""
        conn = None
        try:
            conn = self.get_connection()
            c = conn.cursor()
            
            c.execute("BEGIN TRANSACTION")
            
            # Delete expired pending transactions
            c.execute("""
                DELETE FROM transactions 
                WHERE status = 'pending' AND created_at < ?
            """, (adapt_datetime(expiry_time),))
            
            deleted_count = c.rowcount
            c.execute("COMMIT")
            
            logger.info(f"Cleaned up {deleted_count} expired transactions")
            return deleted_count

        except Exception as e:
            if conn:
                c.execute("ROLLBACK")
            logger.error(f"Error cleaning up expired transactions: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    async def ping(self):
        """Check if the database connection is still active."""
        try:
            # Example: Execute a simple query
            await self.db.execute("SELECT 1")
            return True
        except Exception:
            # Log the error
            logging.exception("Database connection failed")
            return False

# Create a single instance
_db = Database()

def get_database() -> Database:
    """Get the Database instance."""
    return _db


