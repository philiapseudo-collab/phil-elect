"""
Catalog Service for Phil-Elect inventory lookup.
Connects to Supabase database for product information.
"""

import logging
from typing import Optional, Dict, Any, List

# Import Supabase client
from ..db.supabase import get_supabase_client

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database connection failures."""
    pass


def get_item_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Get a product by name using case-insensitive partial match (ilike).
    Queries Supabase products table.
    
    Args:
        name: Product name or partial name (e.g., "Ramtons Fridge", "Vision Plus")
        
    Returns:
        Product dictionary with keys: sku, name, price, stock, image_url
        Returns None if not found or database error
        
    Raises:
        DatabaseError: If Supabase connection fails
    """
    try:
        supabase = get_supabase_client()
        
        # Perform case-insensitive partial match search
        response = supabase.table("products").select("*").ilike("name", f"%{name}%").execute()
        
        if response.data and len(response.data) > 0:
            # Return the first matching result
            product = response.data[0]
            logger.info(f"Found product by name '{name}': {product.get('name')} (SKU: {product.get('sku')})")
            return product
        
        logger.info(f"No product found matching name: {name}")
        return None
        
    except ValueError as e:
        # Supabase credentials not configured
        logger.error(f"Database connection failed: {str(e)}")
        raise DatabaseError("System maintenance: Database not configured")
    except Exception as e:
        # Any other database error
        logger.error(f"Database query failed for name '{name}': {str(e)}")
        raise DatabaseError("System maintenance: Database unavailable")


def get_item_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    """
    Get a product by SKU.
    Queries Supabase products table.
    
    Args:
        sku: Product SKU code (e.g., "RMT-2DR-SLV")
        
    Returns:
        Product dictionary with keys: sku, name, price, stock, image_url
        Returns None if not found or database error
        
    Raises:
        DatabaseError: If Supabase connection fails
    """
    try:
        supabase = get_supabase_client()
        
        # Query by SKU (primary key)
        response = supabase.table("products").select("*").eq("sku", sku).execute()
        
        if response.data and len(response.data) > 0:
            product = response.data[0]
            logger.info(f"Found product by SKU '{sku}': {product.get('name')}")
            return product
        
        logger.info(f"No product found with SKU: {sku}")
        return None
        
    except ValueError as e:
        # Supabase credentials not configured
        logger.error(f"Database connection failed: {str(e)}")
        raise DatabaseError("System maintenance: Database not configured")
    except Exception as e:
        # Any other database error
        logger.error(f"Database query failed for SKU '{sku}': {str(e)}")
        raise DatabaseError("System maintenance: Database unavailable")


def get_all_items() -> List[Dict[str, Any]]:
    """
    Get all products in inventory.
    Queries Supabase products table.
    
    Returns:
        List of all products
        
    Raises:
        DatabaseError: If Supabase connection fails
    """
    try:
        supabase = get_supabase_client()
        
        response = supabase.table("products").select("*").execute()
        
        if response.data:
            logger.info(f"Retrieved {len(response.data)} products from database")
            return response.data
        
        return []
        
    except ValueError as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise DatabaseError("System maintenance: Database not configured")
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        raise DatabaseError("System maintenance: Database unavailable")


def verify_stock(sku: str, quantity: int = 1) -> bool:
    """
    Check if product has sufficient stock.
    Queries Supabase products table.
    
    Args:
        sku: Product SKU code
        quantity: Required quantity
        
    Returns:
        True if stock is available, False otherwise
        
    Raises:
        DatabaseError: If Supabase connection fails
    """
    try:
        product = get_item_by_sku(sku)
        if not product:
            return False
        
        stock = product.get("stock", 0)
        return stock >= quantity
        
    except DatabaseError:
        # Re-raise database errors
        raise
    except Exception as e:
        logger.error(f"Stock verification failed for SKU '{sku}': {str(e)}")
        raise DatabaseError("System maintenance: Database unavailable")
