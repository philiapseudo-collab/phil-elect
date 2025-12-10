"""
Catalog Service for Phil-Elect inventory lookup.
Wraps mock_data.py to provide a service layer.
This allows switching from mock data to Supabase later without breaking the app.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add api directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from db.mock_data import (
    get_product_by_sku,
    get_product_by_name,
    get_all_products,
    check_stock
)


def get_item_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Get a product by name (case-insensitive partial match).
    Returns the first matching product, or None if not found.
    
    Args:
        name: Product name or partial name (e.g., "Ramtons Fridge", "Vision Plus")
        
    Returns:
        Product dictionary with keys: sku, name, price, stock
        Returns None if no match found
    """
    matches = get_product_by_name(name)
    
    if matches:
        # Return the first match
        return matches[0]
    
    return None


def get_item_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    """
    Get a product by SKU.
    
    Args:
        sku: Product SKU code (e.g., "RMT-2DR-SLV")
        
    Returns:
        Product dictionary with keys: sku, name, price, stock
        Returns None if not found
    """
    return get_product_by_sku(sku)


def get_all_items() -> List[Dict[str, Any]]:
    """
    Get all products in inventory.
    
    Returns:
        List of all products
    """
    return get_all_products()


def verify_stock(sku: str, quantity: int = 1) -> bool:
    """
    Check if product has sufficient stock.
    
    Args:
        sku: Product SKU code
        quantity: Required quantity
        
    Returns:
        True if stock is available, False otherwise
    """
    return check_stock(sku, quantity)

