import logging
import os
from datetime import datetime
from typing import Optional, Union
from decimal import Decimal

from telegram import Bot
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from dotenv import load_dotenv

from config import get_config

# Load environment variables
load_dotenv()

class LogManager:
    """Manages logging and admin notifications with enhanced functionality."""

    def __init__(self):
        self.config = get_config()
        self.admin_chat_id = self.config.OWNER_ID
        
        # Setup logger
        self.logger = logging.getLogger('DiamondStore')
        if not self.logger.handlers:
            handler = logging.FileHandler('diamond_store.log', encoding='utf-8')
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                '%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def log_action(self, 
                        context: ContextTypes.DEFAULT_TYPE, 
                        action: str,
                        details: str,
                        user_id: Optional[int] = None,
                        amount: Optional[Union[int, float, Decimal]] = None,
                        level: str = "info",
                        notify_admin: bool = False) -> None:
        """
        Enhanced log actions with user tracking and amount handling.
        
        Args:
            context: The context object from telegram
            action: The action being performed
            details: Details about the action
            user_id: Optional user ID involved in the action
            amount: Optional amount involved in the action
            level: Log level (info, warning, error, success)
            notify_admin: Whether to send notification to admin
        """
        try:
            # Format the log message
            log_parts = [f"[{level.upper()}]", action]
            if user_id:
                log_parts.append(f"User: {user_id}")
            if amount is not None:
                log_parts.append(f"Amount: {amount}")
            log_parts.append(f"Details: {details}")
            
            log_msg = " | ".join(log_parts)
            
            # Log based on level
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(log_msg)

            if notify_admin:
                await self.notify_admin(context, action, details, user_id, amount, level)
                
        except Exception as e:
            self.logger.error(f"Error in log_action: {e}")

    async def notify_admin(self,
                         context: ContextTypes.DEFAULT_TYPE,
                         action: str,
                         details: str,
                         user_id: Optional[int] = None,
                         amount: Optional[Union[int, float, Decimal]] = None,
                         level: str = "info") -> None:
        """
        Enhanced admin notification with rich formatting.
        """
        try:
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "success": "✅",
                "transaction": "💰",
                "user": "👤",
                "system": "🔧"
            }

            # Build the message with proper escape
            message_parts = [
                f"{emoji_map.get(level, 'ℹ️')} *{escape_markdown(action, version=2)}*\n"
            ]

            if user_id:
                message_parts.append(f"👤 *المستخدم:* `{user_id}`")
            
            if amount is not None:
                message_parts.append(f"💰 *المبلغ:* `{amount}`")
            
            message_parts.extend([
                f"\n📝 *التفاصيل:*\n`{escape_markdown(details, version=2)}`",
                f"\n⏰ {self.format_timestamp(datetime.now())}"
            ])

            message = "\n".join(message_parts)

            # Send with markdown v2 formatting
            await context.bot.send_message(
                chat_id=self.admin_chat_id,
                text=message,
                parse_mode='MarkdownV2'
            )
            
        except Exception as e:
            self.logger.error(f"Error sending admin notification: {e}")

    async def log_transaction(self,
                            context: ContextTypes.DEFAULT_TYPE,
                            user_id: int,
                            amount: Union[int, float, Decimal],
                            transaction_type: str,
                            status: str,
                            details: str = "") -> None:
        """
        Specialized method for logging transactions.
        """
        action = f"Transaction {transaction_type}"
        detailed_msg = (
            f"Type: {transaction_type}\n"
            f"Status: {status}\n"
            f"Amount: {amount}\n"
            f"{details if details else ''}"
        )
        
        await self.log_action(
            context=context,
            action=action,
            details=detailed_msg,
            user_id=user_id,
            amount=amount,
            level="info",
            notify_admin=True
        )

    async def log_error(self,
                       context: ContextTypes.DEFAULT_TYPE,
                       error: Exception,
                       user_id: Optional[int] = None,
                       custom_msg: Optional[str] = None) -> None:
        """
        Specialized method for logging errors.
        """
        error_msg = (
            f"Error Type: {type(error).__name__}\n"
            f"Error Message: {str(error)}\n"
            f"{custom_msg if custom_msg else ''}"
        )
        
        await self.log_action(
            context=context,
            action="Error Occurred",
            details=error_msg,
            user_id=user_id,
            level="error",
            notify_admin=True
        )

    def format_timestamp(self, dt: datetime) -> str:
        """Format datetime with timezone awareness."""
        try:
            return dt.strftime('%Y\\-%m\\-%d %H\\:%M\\:%S')
        except Exception as e:
            self.logger.error(f"Error formatting timestamp: {e}")
            return "Timestamp Error"

# Create singleton instance
_log_manager = LogManager()

def get_log_manager() -> LogManager:
    """Get the LogManager instance."""
    return _log_manager