"""
Mock inventory data for Phil-Elect (Home & Electronics).
Used before Supabase connection is established.

Schema: sku, name, price (KES), stock (quantity)
"""

# Phil-Elect Inventory Mock Data
INVENTORY = [
    {
        "sku": "RMT-2DR-SLV",
        "name": "Ramtons 2-Door Fridge (Silver)",
        "price": 35000,
        "stock": 5
    },
    {
        "sku": "VP-32-SMART",
        "name": "Vision Plus 32\" Smart TV",
        "price": 14000,
        "stock": 8
    },
    {
        "sku": "VON-HP-DBL",
        "name": "Von Hotplate (Double)",
        "price": 3500,
        "stock": 12
    },
    {
        "sku": "MIKA-MW-20L",
        "name": "Mika Microwave (20L)",
        "price": 8000,
        "stock": 10
    },
    {
        "sku": "SONY-SB-S20R",
        "name": "Sony Soundbar (S20R)",
        "price": 28000,
        "stock": 4
    }
]


def get_product_by_sku(sku: str) -> dict:
    """
    Get a product by SKU.
    
    Args:
        sku: Product SKU code
        
    Returns:
        Product dictionary or None if not found
    """
    for product in INVENTORY:
        if product["sku"].upper() == sku.upper():
            return product
    return None


def get_product_by_name(name: str) -> list:
    """
    Search products by name (case-insensitive partial match).
    
    Args:
        name: Product name or partial name
        
    Returns:
        List of matching products
    """
    name_lower = name.lower()
    matches = []
    for product in INVENTORY:
        if name_lower in product["name"].lower():
            matches.append(product)
    return matches


def get_all_products() -> list:
    """
    Get all products in inventory.
    
    Returns:
        List of all products
    """
    return INVENTORY.copy()


def check_stock(sku: str, quantity: int = 1) -> bool:
    """
    Check if product has sufficient stock.
    
    Args:
        sku: Product SKU code
        quantity: Required quantity
        
    Returns:
        True if stock is available, False otherwise
    """
    product = get_product_by_sku(sku)
    if not product:
        return False
    return product["stock"] >= quantity

