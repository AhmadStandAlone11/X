import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime

from config import get_config
from log_manager import get_log_manager

config = get_config()
log_manager = get_log_manager()

class ProductManager:
    """Enhanced product management system with CRUD operations."""
    
    def __init__(self, products_file: str = 'products.json'):
        """Initialize the product manager."""
        self.logger = logging.getLogger(__name__)
        self.products_file = products_file
        self.backup_dir = 'backups/products'
        os.makedirs(self.backup_dir, exist_ok=True)

    def _backup_products(self) -> bool:
        """Create a backup of the products file."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.backup_dir}/products_{timestamp}.json"
            with open(self.products_file, 'r', encoding='utf-8') as src:
                with open(backup_file, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            return True
        except Exception as e:
            self.logger.error(f"Backup error: {e}")
            return False

    def _load_products(self) -> Dict[str, Any]:
        """Load products from JSON file."""
        try:
            with open(self.products_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading products: {e}")
            return {"games": {}, "apps": {}}

    def _save_products(self, products: Dict[str, Any]) -> bool:
        """Save products to JSON file with backup."""
        try:
            if self._backup_products():
                with open(self.products_file, 'w', encoding='utf-8') as f:
                    json.dump(products, f, ensure_ascii=False, indent=4)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error saving products: {e}")
            return False

    def get_product(self, category: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific product."""
        products = self._load_products()
        return products.get(category, {}).get(product_id)

    def get_all_products(self, category: Optional[str] = None) -> Dict[str, Any]:
        """Get all products or products in a specific category."""
        products = self._load_products()
        if category:
            return {category: products.get(category, {})}
        return products

    # داخل الكلاس ProductManager:
    async def should_reload_products(self) -> bool:
        """Check if products should be reloaded from the database."""
    # Implement your logic here to determine if products need to be reloaded.
    # For example, you could check if the product data has been modified in the database.
    # This is just a placeholder, replace with your actual logic.
        return False  # Replace with your actual logic
    
    def add_product(self, category: str, product_id: str, 
                   product_data: Dict[str, Any]) -> bool:
        """Add a new product."""
        try:
            products = self._load_products()
            
            if category not in products:
                products[category] = {}
            
            if product_id in products[category]:
                raise ValueError(f"Product {product_id} already exists")
            
            # Validate product data based on category
            if category == "games":
                required_fields = ['name', 'icon', 'packages']
                if not all(field in product_data for field in required_fields):
                    raise ValueError("Missing required fields for game")
                if not isinstance(product_data['packages'], list):
                    raise ValueError("Packages must be a list")
                
            elif category == "apps":
                required_fields = ['name', 'icon', 'package_size', 'price']
                if not all(field in product_data for field in required_fields):
                    raise ValueError("Missing required fields for app")
                
            else:
                raise ValueError("Invalid category")
            
            products[category][product_id] = product_data
            return self._save_products(products)
            
        except Exception as e:
            self.logger.error(f"Error adding product: {e}")
            return False

    def update_product(self, category: str, product_id: str, 
                      updates: Dict[str, Any]) -> bool:
        """Update an existing product."""
        try:
            products = self._load_products()
            
            if category not in products or product_id not in products[category]:
                raise ValueError(f"Product {product_id} not found")
            
            current_product = products[category][product_id]
            
            # Update based on category
            if category == "games":
                if 'packages' in updates:
                    if not isinstance(updates['packages'], list):
                        raise ValueError("Packages must be a list")
                    current_product['packages'] = updates['packages']
                    
            elif category == "apps":
                if 'price' in updates:
                    current_product['price'] = float(updates['price'])
                if 'package_size' in updates:
                    current_product['package_size'] = int(updates['package_size'])
            
            # Update common fields
            for field in ['name', 'icon', 'note']:
                if field in updates:
                    current_product[field] = updates[field]
            
            return self._save_products(products)
            
        except Exception as e:
            self.logger.error(f"Error updating product: {e}")
            return False

    def delete_product(self, category: str, product_id: str) -> bool:
        """Delete a product."""
        try:
            products = self._load_products()
            
            if category not in products or product_id not in products[category]:
                raise ValueError(f"Product {product_id} not found")
            
            del products[category][product_id]
            return self._save_products(products)
            
        except Exception as e:
            self.logger.error(f"Error deleting product: {e}")
            return False

    def update_game_package_price(self, game_id: str, package_index: int, 
                                new_price: float) -> bool:
        """Update price for a specific game package."""
        try:
            products = self._load_products()
            
            if 'games' not in products or game_id not in products['games']:
                raise ValueError(f"Game {game_id} not found")
            
            game = products['games'][game_id]
            if not 0 <= package_index < len(game['packages']):
                raise ValueError("Invalid package index")
            
            game['packages'][package_index][1] = float(new_price)
            return self._save_products(products)
            
        except Exception as e:
            self.logger.error(f"Error updating game package price: {e}")
            return False

    def update_app_price(self, app_id: str, new_price: float) -> bool:
        """Update price for an app."""
        try:
            products = self._load_products()
            
            if 'apps' not in products or app_id not in products['apps']:
                raise ValueError(f"App {app_id} not found")
            
            products['apps'][app_id]['price'] = float(new_price)
            return self._save_products(products)
            
        except Exception as e:
            self.logger.error(f"Error updating app price: {e}")
            return False