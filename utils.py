import logging
from datetime import timezone, timedelta, datetime
from typing import Union, Optional
from decimal import Decimal

# Logger setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
DAMASCUS_TZ = timezone(timedelta(hours=3))

def format_currency(amount: Union[float, Decimal, int], currency: str = "SYP") -> str:
    """
    Format currency amounts with improved precision and formatting.
    
    Args:
        amount: The amount to format
        currency: The currency code (SYP, USD, or USDT)
    
    Returns:
        Formatted currency string
    """
    try:
        # Convert to Decimal for precise calculations
        amount = Decimal(str(amount))
        
        if currency == "SYP":
            return f"{amount:,.0f} ل.س"
        elif currency == "USD":
            return f"${amount:,.2f}"
        elif currency == "USDT":
            return f"{amount:,.2f} USDT"
        return f"{amount:,}"
    except Exception as e:
        logger.error(f"Error formatting currency: {e}")
        return str(amount)

def get_damascus_time(format_str: Optional[str] = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Get current Damascus time with flexible formatting.
    
    Args:
        format_str: Optional datetime format string
    
    Returns:
        Formatted datetime string
    """
    try:
        return datetime.now(DAMASCUS_TZ).strftime(format_str)
    except Exception as e:
        logger.error(f"Error getting Damascus time: {e}")
        return datetime.now(DAMASCUS_TZ).isoformat()

def format_datetime(dt: datetime, format_str: Optional[str] = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Format datetime with flexible formatting.
    
    Args:
        dt: Datetime object to format
        format_str: Optional datetime format string
    
    Returns:
        Formatted datetime string
    """
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DAMASCUS_TZ)
        return dt.strftime(format_str)
    except Exception as e:
        logger.error(f"Error formatting datetime: {e}")
        return dt.isoformat()

def parse_amount(amount_str: str) -> Optional[Decimal]:
    """
    Parse amount string to Decimal with error handling.
    
    Args:
        amount_str: String representation of amount
    
    Returns:
        Decimal amount or None if invalid
    """
    try:
        # Remove currency symbols and whitespace
        amount_str = amount_str.replace('ل.س', '').replace('$', '').strip()
        # Replace Arabic numbers if present
        arabic_numbers = {'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
                         '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'}
        for ar, en in arabic_numbers.items():
            amount_str = amount_str.replace(ar, en)
        return Decimal(amount_str)
    except Exception as e:
        logger.error(f"Error parsing amount: {e}")
        return None

def calculate_exchange_rate(amount: Decimal, from_currency: str, to_currency: str,
                          usd_rate: Decimal, usdt_rate: Decimal) -> Optional[Decimal]:
    """
    Calculate exchange rate between currencies.
    
    Args:
        amount: Amount to convert
        from_currency: Source currency
        to_currency: Target currency
        usd_rate: USD to SYP rate
        usdt_rate: USDT to SYP rate
    
    Returns:
        Converted amount or None if error
    """
    try:
        if from_currency == to_currency:
            return amount
            
        rates = {
            'USD': usd_rate,
            'USDT': usdt_rate,
            'SYP': Decimal('1')
        }
        
        if from_currency not in rates or to_currency not in rates:
            raise ValueError(f"Unsupported currency: {from_currency} or {to_currency}")
            
        # Convert to SYP first if needed
        amount_syp = amount * rates[from_currency]
        
        # Then convert to target currency
        return amount_syp / rates[to_currency]
        
    except Exception as e:
        logger.error(f"Error calculating exchange rate: {e}")
        return None