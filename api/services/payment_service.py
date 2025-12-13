"""
Paystack payment service for hybrid payments (M-Pesa STK Push + Card Checkout Links).
"""

import requests
import os
import logging
import json

# Configure Logging
logger = logging.getLogger(__name__)

# Load Environment Variables
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
IS_PROD = os.getenv("MPESA_ENVIRONMENT", "sandbox") == "production"

# Paystack Base URL
BASE_URL = "https://api.paystack.co"

# Detect Test Mode
IS_TEST_MODE = PAYSTACK_SECRET_KEY and PAYSTACK_SECRET_KEY.startswith("sk_test_")

# Paystack Test Phone Numbers (for test mode)
# Paystack's official test number for Kenya M-Pesa: +254710000000
# Format: No spaces, international format with + prefix
PAYSTACK_TEST_PHONES = [
    "+254710000000",  # Official Paystack test number for M-Pesa
    "+254700000000",
    "+254711111111",
    "+254722222222"
]

# Safety Log: Check for Test Mode
if IS_TEST_MODE:
    logger.warning("🧪 RUNNING IN PAYSTACK TEST MODE - No real money will be deducted.")
    print("🧪 RUNNING IN PAYSTACK TEST MODE - No real money will be deducted.")


def trigger_mpesa_payment(phone_number: str, amount: int, order_id: str) -> str:
    """
    Triggers a 'Headless' STK Push via Paystack (Direct Charge).
    User gets the PIN prompt immediately.
    
    Args:
        phone_number: Customer phone number (format: 254712345678)
        amount: Payment amount in KES (e.g., 14500 for 145.00 KES)
        order_id: Order ID to track the payment
        
    Returns:
        The Paystack reference string from the response
        
    Raises:
        Exception: If payment request fails
    """
    if not PAYSTACK_SECRET_KEY:
        error_msg = "PAYSTACK_SECRET_KEY environment variable is required"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    endpoint = f"{BASE_URL}/charge"
    
    # Paystack requires amount in kobo/cents (Multiply by 100)
    amount_in_cents = int(amount * 100)
    
    # Format phone number for Paystack (international format with + prefix)
    # Paystack requires: +254XXXXXXXXX format for M-Pesa
    if phone_number.startswith("+"):
        phone_number_clean = phone_number[1:]  # Remove + for processing
    else:
        phone_number_clean = phone_number
    
    # Ensure it starts with 254
    if not phone_number_clean.startswith("254"):
        # Assume local format, add 254
        if phone_number_clean.startswith("0"):
            phone_number_clean = "254" + phone_number_clean[1:]
        else:
            phone_number_clean = "254" + phone_number_clean
    
    # Format for Paystack API (international format WITH + prefix for logging)
    phone_for_logging = f"+{phone_number_clean}"
    
    # In test mode, automatically use test phone number if user provided real number
    if IS_TEST_MODE and phone_for_logging not in PAYSTACK_TEST_PHONES:
        # Use first test phone number for consistency
        original_phone = phone_for_logging
        test_phone_with_plus = PAYSTACK_TEST_PHONES[0]  # "+254710000000"
        # Use the test phone directly (it already has + prefix)
        phone_for_logging = test_phone_with_plus
        phone_number_clean = test_phone_with_plus[1:]  # "254710000000" for email
        logger.info(f"🧪 Test Mode: Using test phone {phone_for_logging} instead of {original_phone}")
    
    # Paystack mobile_money API requires phone WITH + prefix in international format
    phone_for_paystack = phone_for_logging  # Already formatted with + prefix: +254XXXXXXXXX
    
    # 1. Prepare Payload
    payload = {
        "amount": amount_in_cents, 
        "email": f"{phone_number_clean}@philelect.bot",
        "currency": "KES",
        "mobile_money": {
            "phone": phone_for_paystack,  # Format: +254XXXXXXXXX (with + prefix)
            "provider": "mpesa"
        },
        "reference": f"ORD-{str(order_id)[:8]}"
    }
    
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"⚠️ Initiating Paystack STK Push to {phone_for_logging} (original: {phone_number}) for KES {amount}")
        # Log payload for debugging
        payload_log = payload.copy()
        logger.info(f"Paystack payload phone: {payload_log.get('mobile_money', {}).get('phone')}")
        logger.debug(f"Full Paystack payload: {json.dumps(payload_log)}")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=20)
        
        # 2. Deep Logging
        logger.info(f"Paystack Response: {response.status_code} - {response.text}")
        
        # Parse JSON response (don't raise_for_status yet - we need to extract detailed error)
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"Paystack response is not valid JSON: {response.text}")
            response.raise_for_status()  # Will raise appropriate HTTP error
            raise Exception(f"Invalid JSON response from Paystack: {str(e)}")
        
        # 3. Check HTTP Status Code
        if response.status_code not in [200, 201]:
            # Extract detailed error message from Paystack response
            error_msg = data.get("message", "Unknown error")
            # Check for nested error message in data object
            error_data = data.get("data", {})
            if isinstance(error_data, dict) and error_data.get("message"):
                error_msg = error_data.get("message")
            
            logger.error(f"Paystack STK Push failed (HTTP {response.status_code}): {error_msg}")
            raise Exception(f"Paystack API error: {error_msg}")
        
        # 4. Check Paystack API Status
        # Paystack returns "status": true if the request was accepted.
        # The actual payment status might be "pending" (waiting for user PIN) or "failed".
        if not data.get("status"):
            # Extract error message from nested data if available
            error_data = data.get("data", {})
            error_msg = data.get("message", "Paystack request failed")
            if isinstance(error_data, dict) and error_data.get("message"):
                error_msg = error_data.get("message")
            
            logger.error(f"Paystack STK Push failed: {error_msg}")
            raise Exception(f"Paystack API error: {error_msg}")
        
        # 5. Check Transaction Status in Data
        transaction_data = data.get("data", {})
        if isinstance(transaction_data, dict) and transaction_data.get("status") == "failed":
            error_msg = transaction_data.get("message", "Transaction failed")
            logger.error(f"Paystack transaction failed: {error_msg}")
            # Provide helpful message for test mode
            if IS_TEST_MODE and ("test" in error_msg.lower() or "test mobile" in error_msg.lower()):
                test_phones_str = ", ".join(PAYSTACK_TEST_PHONES)
                error_msg += f" Test mode requires test phone numbers: {test_phones_str}"
            raise Exception(f"Payment failed: {error_msg}")
        
        # Extract reference from response
        reference = transaction_data.get("reference") if isinstance(transaction_data, dict) else data.get("data", {}).get("reference")
        if not reference:
            logger.error(f"Paystack response missing reference: {data}")
            raise Exception("Paystack response missing reference")
        
        logger.info(f"Paystack STK Push initiated successfully. Reference: {reference}")
        return reference

    except requests.exceptions.RequestException as e:
        logger.error(f"Paystack STK Failed: {str(e)}")
        # Try to extract detailed error from response
        if hasattr(e, 'response') and e.response:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("message", "Unknown error")
                error_details = error_data.get("data", {})
                if isinstance(error_details, dict) and error_details.get("message"):
                    error_msg = error_details.get("message")
                logger.error(f"Error Details: {error_msg}")
                raise Exception(f"Paystack error: {error_msg}")
            except (ValueError, AttributeError):
                logger.error(f"Error Details: {e.response.text}")
        raise Exception(f"Network error: {str(e)}")


def generate_card_link(phone_number: str, amount: int, order_id: str) -> str:
    """
    Generates a Standard Checkout Link for Card Users.
    
    Args:
        phone_number: Customer phone number (format: 254712345678)
        amount: Payment amount in KES (e.g., 14500 for 145.00 KES)
        order_id: Order ID to track the payment
        
    Returns:
        The checkout authorization URL from Paystack
        
    Raises:
        Exception: If link generation fails
    """
    if not PAYSTACK_SECRET_KEY:
        error_msg = "PAYSTACK_SECRET_KEY environment variable is required"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    endpoint = f"{BASE_URL}/transaction/initialize"
    amount_in_cents = int(amount * 100)
    
    # Format phone number (ensure it starts with 254)
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]
    if not phone_number.startswith("254"):
        # Assume local format, add 254
        if phone_number.startswith("0"):
            phone_number = "254" + phone_number[1:]
        else:
            phone_number = "254" + phone_number
    
    payload = {
        "amount": amount_in_cents,
        "email": f"{phone_number}@philelect.bot",
        "currency": "KES",
        "reference": f"ORD-{str(order_id)[:8]}-CARD",
        "channels": ["card", "mobile_money"]
    }
    
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Generating Paystack Link for {phone_number}, Amount: {amount} KES, Order: {order_id}")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        
        # Deep logging
        logger.info(f"Paystack Response: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        data = response.json()
        
        # Check status
        if not data.get("status"):
            error_msg = data.get("message", "Paystack request failed")
            logger.error(f"Paystack link generation failed: {error_msg}")
            raise Exception(f"Paystack API error: {error_msg}")
        
        # Return the authorization URL
        authorization_url = data.get("data", {}).get("authorization_url")
        if not authorization_url:
            logger.error(f"Paystack response missing authorization_url: {data}")
            raise Exception("Paystack response missing authorization_url")
        
        logger.info(f"Paystack card checkout link generated successfully. URL: {authorization_url}")
        return authorization_url

    except requests.exceptions.RequestException as e:
        logger.error(f"Link Generation Failed: {str(e)}")
        if hasattr(e, 'response') and e.response:
             logger.error(f"Error Details: {e.response.text}")
        raise Exception(f"Network error: {str(e)}")

