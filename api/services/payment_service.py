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

# Safety Log: Check for Test Mode
if PAYSTACK_SECRET_KEY and PAYSTACK_SECRET_KEY.startswith("sk_test_"):
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
    
    # Format phone number (ensure it starts with 254)
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]
    if not phone_number.startswith("254"):
        # Assume local format, add 254
        if phone_number.startswith("0"):
            phone_number = "254" + phone_number[1:]
        else:
            phone_number = "254" + phone_number
    
    # 1. Prepare Payload
    payload = {
        "amount": amount_in_cents, 
        "email": f"{phone_number}@philelect.bot",
        "currency": "KES",
        "mobile_money": {
            "phone": phone_number,
            "provider": "mpesa"
        },
        "reference": f"ORD-{str(order_id)[:8]}"
    }
    
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"⚠️ Initiating Paystack STK Push to {phone_number} for KES {amount}")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=20)
        
        # 2. Deep Logging
        logger.info(f"Paystack Response: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        data = response.json()
        
        # 3. Check Status
        # Paystack returns "status": true if the request was accepted.
        # The actual payment status might be "pending" (waiting for user PIN).
        if not data.get("status"):
            error_msg = data.get("message", "Paystack request failed")
            logger.error(f"Paystack STK Push failed: {error_msg}")
            raise Exception(f"Paystack API error: {error_msg}")
        
        # Extract reference from response
        reference = data.get("data", {}).get("reference")
        if not reference:
            logger.error(f"Paystack response missing reference: {data}")
            raise Exception("Paystack response missing reference")
        
        logger.info(f"Paystack STK Push initiated successfully. Reference: {reference}")
        return reference

    except requests.exceptions.RequestException as e:
        logger.error(f"Paystack STK Failed: {str(e)}")
        if hasattr(e, 'response') and e.response:
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

