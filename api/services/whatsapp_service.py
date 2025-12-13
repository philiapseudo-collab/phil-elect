"""
WhatsApp service for sending messages via Meta Cloud API.
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def send_whatsapp_message(phone_number: str, message_text: str) -> bool:
    """
    Send a WhatsApp message to a user via Meta Cloud API.
    
    Args:
        phone_number: Recipient phone number (with country code, e.g., "254712345678")
        message_text: Text message to send
        
    Returns:
        True if message sent successfully, False otherwise
    """
    api_token = os.environ.get("WHATSAPP_API_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    
    if not api_token or not phone_number_id:
        logger.error("WhatsApp API credentials not configured (WHATSAPP_API_TOKEN or WHATSAPP_PHONE_NUMBER_ID)")
        return False
    
    # Meta Cloud API endpoint
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # Format phone number (ensure it's in international format without +)
    formatted_phone = phone_number.strip()
    if formatted_phone.startswith("+"):
        formatted_phone = formatted_phone[1:]
    # Ensure it starts with country code (254 for Kenya)
    if not formatted_phone.startswith("254"):
        if formatted_phone.startswith("0"):
            # Remove leading 0 and add 254
            formatted_phone = "254" + formatted_phone[1:]
        else:
            # Assume it's missing country code, add 254
            formatted_phone = "254" + formatted_phone
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": formatted_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text
        }
    }
    
    try:
        # Log the request for debugging
        logger.debug(f"WhatsApp API request: {url}")
        logger.debug(f"WhatsApp API payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        # Check status code
        if response.status_code != 200:
            # Try to get error details
            try:
                error_result = response.json()
                error_message = error_result.get("error", {}).get("message", "Unknown error")
                error_code = error_result.get("error", {}).get("code", "Unknown")
                error_type = error_result.get("error", {}).get("type", "Unknown")
                logger.error(f"WhatsApp API error {response.status_code}: {error_type} ({error_code}) - {error_message}")
                logger.error(f"Full error response: {error_result}")
            except Exception as parse_error:
                logger.error(f"WhatsApp API error {response.status_code}: {response.text}")
                logger.error(f"Failed to parse error response: {str(parse_error)}")
            
            return False
        
        result = response.json()
        if "messages" in result:
            message_id = result["messages"][0].get("id", "unknown")
            logger.info(f"WhatsApp message sent successfully to {formatted_phone} (Message ID: {message_id})")
            return True
        else:
            logger.error(f"WhatsApp API unexpected response: {result}")
            return False
            
    except requests.exceptions.HTTPError as e:
        # HTTP error (4xx, 5xx) - response should be available
        try:
            if hasattr(e, 'response') and e.response is not None:
                error_result = e.response.json()
                error_message = error_result.get("error", {}).get("message", str(e))
                logger.error(f"WhatsApp API HTTP error: {error_message}")
                logger.error(f"Full error response: {error_result}")
            else:
                logger.error(f"WhatsApp API HTTP error: {str(e)}")
        except Exception as parse_error:
            logger.error(f"WhatsApp API HTTP error: {str(e)}")
            logger.error(f"Failed to parse error response: {str(parse_error)}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send WhatsApp message (network error): {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp message: {str(e)}")
        return False

