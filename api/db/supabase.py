"""
Supabase database client initialization for Phil-Elect.
Handles connection to Supabase PostgreSQL database.
"""

import os
import logging
from supabase import create_client, Client
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize Supabase client
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or create the Supabase client instance.
    Uses environment variables: SUPABASE_URL and SUPABASE_KEY.
    
    Returns:
        Supabase Client instance
        
    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY is not configured
    """
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        error_msg = "Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_KEY environment variables."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        _supabase_client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized successfully")
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {str(e)}")
        raise


# Export the client instance (for convenience)
def supabase() -> Client:
    """
    Convenience function to get the Supabase client.
    
    Returns:
        Supabase Client instance
    """
    return get_supabase_client()

