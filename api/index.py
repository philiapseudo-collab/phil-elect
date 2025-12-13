"""
FastAPI entry point for Vercel Serverless deployment.
Handles WhatsApp webhook verification and message processing for Phil-Elect.
"""

import os
import logging
import uuid
import re
import hmac
import hashlib
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import services (relative imports for Vercel)
from .services.openai_service import analyze_message
from .services.catalog_service import get_item_by_name, get_item_by_sku, find_products, DatabaseError
from .services.whatsapp_service import send_whatsapp_message
from .services.payment_service import trigger_mpesa_payment, generate_card_link
from .db.supabase import get_supabase_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def upsert_user_search_results(phone_number: str, search_results: List[Dict[str, Any]]) -> bool:
    """
    UPSERT user record with last_search_results.
    Creates user if doesn't exist, updates if exists.
    
    Args:
        phone_number: User's WhatsApp phone number
        search_results: List of products to save (minimal format: [{"sku": "...", "name": "...", "price": 14500}])
        
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_client()
        
        # Prepare minimal search results data
        minimal_results = []
        for product in search_results:
            minimal_results.append({
                "sku": product.get("sku"),
                "name": product.get("name"),
                "price": product.get("price")
            })
        
        # UPSERT: Update if exists, insert if new
        user_data = {
            "phone": phone_number,
            "last_search_results": minimal_results  # JSONB column
        }
        
        # Use upsert (insert if not exists, update if exists)
        # Note: phone is the primary key, so upsert will match on that
        response = supabase.table("users").upsert(user_data, on_conflict="phone").execute()
        
        if response.data:
            logger.info(f"UPSERT successful for user {phone_number}: {len(minimal_results)} search results saved")
        else:
            logger.warning(f"UPSERT returned no data for user {phone_number}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to upsert user search results for {phone_number}: {str(e)}")
        return False


def get_user_search_results(phone_number: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get user's last_search_results from database.
    
    Args:
        phone_number: User's WhatsApp phone number
        
    Returns:
        List of products from last search, or None if not found/error
    """
    try:
        supabase = get_supabase_client()
        
        response = supabase.table("users").select("last_search_results").eq("phone", phone_number).execute()
        
        if response.data and len(response.data) > 0:
            last_search = response.data[0].get("last_search_results")
            if last_search:
                logger.info(f"Retrieved search results for user {phone_number}: {len(last_search)} items")
                return last_search
        
        logger.info(f"No search results found for user {phone_number}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get user search results for {phone_number}: {str(e)}")
        return None


def get_last_selected_product(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Get user's last selected product from database.
    Checks last_selected_product first, then falls back to last_search_results[0].
    
    Args:
        phone_number: User's WhatsApp phone number
        
    Returns:
        Product dictionary with sku, name, price, or None if not found
    """
    try:
        supabase = get_supabase_client()
        
        response = supabase.table("users").select("last_selected_product, last_search_results").eq("phone", phone_number).execute()
        
        if response.data and len(response.data) > 0:
            user_data = response.data[0]
            
            # Try last_selected_product first
            last_selected = user_data.get("last_selected_product")
            if last_selected:
                logger.info(f"Retrieved last selected product for user {phone_number}: {last_selected.get('name')}")
                return last_selected
            
            # Fallback to first item in last_search_results
            last_search = user_data.get("last_search_results")
            if last_search and len(last_search) > 0:
                logger.info(f"Using first item from search results for user {phone_number}")
                return last_search[0]
        
        logger.info(f"No selected product found for user {phone_number}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get last selected product for {phone_number}: {str(e)}")
        return None


# Initialize FastAPI app
app = FastAPI(title="WhatsApp Bot API")

# Enable CORS (wildcard for MVP)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Models for WhatsApp Webhook Payload
class TextMessage(BaseModel):
    """Text message content from WhatsApp."""
    body: str


class Message(BaseModel):
    """WhatsApp message object."""
    from_: Optional[str] = Field(None, alias="from")  # 'from' is a Python keyword, using from_
    id: str
    timestamp: str
    type: str
    text: Optional[TextMessage] = None


class Contact(BaseModel):
    """Contact information."""
    profile: Optional[Dict[str, Any]] = None
    wa_id: Optional[str] = None


class Value(BaseModel):
    """Value object containing messages and metadata."""
    messaging_product: str
    metadata: Optional[Dict[str, Any]] = None
    contacts: Optional[List[Contact]] = None
    messages: Optional[List[Message]] = None


class Change(BaseModel):
    """Change object in webhook entry."""
    value: Value
    field: str


class Entry(BaseModel):
    """Entry object in webhook payload."""
    id: str
    changes: List[Change]


class WhatsAppWebhook(BaseModel):
    """Root webhook payload from Meta WhatsApp."""
    object: str
    entry: List[Entry]


# Health Check Endpoint
@app.get("/")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "Bot is running", "service": "WhatsApp Bot API"}


# Meta WhatsApp Webhook Verification (GET)
@app.get("/api/webhook")
async def verify_webhook(request: Request):
    """
    Meta requires this GET endpoint for initial webhook verification.
    Returns hub.challenge if verify_token matches.
    """
    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    
    if not verify_token:
        raise HTTPException(status_code=500, detail="Verify token not configured")
    
    # Meta sends these query parameters
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    # Verify the token
    if mode == "subscribe" and token == verify_token:
        # Return the challenge to complete verification
        return Response(content=challenge, media_type="text/plain")
    else:
        # Token mismatch - return 403
        raise HTTPException(status_code=403, detail="Verification failed")


# WhatsApp Message Handler (POST)
@app.post("/api/webhook")
async def handle_webhook(webhook: WhatsAppWebhook):
    """
    Receives WhatsApp messages from Meta Cloud API.
    Analyzes messages, matches to catalog, and logs order details.
    """
    # Process each entry
    for entry in webhook.entry:
        for change in entry.changes:
            value = change.value
            
            # Check if this is a message
            if value.messaging_product == "whatsapp" and value.messages:
                for message in value.messages:
                    # Only process text messages
                    if message.type == "text" and message.text:
                        text_body = message.text.body
                        sender_id = message.from_
                        
                        # Log raw user text
                        logger.info(f"Raw user message from {sender_id}: {text_body}")
                        
                        # PRIORITY 1: Check for payment request BEFORE OpenAI (saves ~2s and prevents misclassification)
                        pay_pattern = re.search(r'pay\s+(\d+)', text_body.lower())
                        if pay_pattern:
                            amount = int(pay_pattern.group(1))
                            
                            # Detect payment method preference (Card/Visa vs default M-Pesa)
                            text_lower = text_body.lower()
                            is_card_payment = "card" in text_lower or "visa" in text_lower or "mastercard" in text_lower
                            
                            logger.info(f"Payment request detected: {amount} KES from {sender_id}, Method: {'Card' if is_card_payment else 'M-Pesa'}")
                            
                            # Get last selected product from database (state management)
                            selected_product = get_last_selected_product(sender_id)
                            
                            if not selected_product:
                                # Fail-safe: Proceed with manual payment
                                logger.warning(f"No selected product found for {sender_id}, proceeding with manual payment")
                                selected_product = {
                                    "sku": "MANUAL",
                                    "name": "Manual Payment",
                                    "price": amount
                                }
                            
                            # Validate amount (optional: compare with stored price)
                            stored_price = selected_product.get("price", 0)
                            if stored_price > 0 and abs(amount - stored_price) > 100:
                                # Amount differs significantly, but proceed anyway for MVP
                                logger.warning(f"Amount mismatch: User sent {amount}, stored price is {stored_price}")
                            
                            try:
                                # Create order FIRST (need order_id for payment)
                                order_id = str(uuid.uuid4())
                                supabase = get_supabase_client()
                                
                                order_items = [{
                                    "sku": selected_product.get("sku", "MANUAL"),
                                    "qty": 1,
                                    "price": amount
                                }]
                                
                                order_data = {
                                    "order_id": order_id,
                                    "user_phone": sender_id,
                                    "items": order_items,
                                    "total_amount": amount,
                                    "status": "PENDING",
                                    "mpesa_receipt": None
                                }
                                
                                supabase.table("orders").insert(order_data).execute()
                                logger.info(f"Order created: {order_id} for user {sender_id}, Amount: {amount} KES")
                                
                                # Route to appropriate payment method
                                try:
                                    if is_card_payment:
                                        # Card payment: Generate checkout link
                                        # Email is auto-generated inside the service from phone number
                                        checkout_url = generate_card_link(sender_id, amount, order_id)
                                        
                                        # Send checkout link via WhatsApp
                                        amount_formatted = f"{amount:,}"
                                        reply_message = f"✅ Card Payment Link Generated!\n\nClick here to pay securely: {checkout_url}\n\nAmount: KES {amount_formatted}\nOrder ID: {order_id}"
                                        send_whatsapp_message(sender_id, reply_message)
                                        logger.info(f"Card checkout link generated successfully for order {order_id}")
                                        
                                        return {
                                            "status": "received",
                                            "sender": sender_id,
                                            "intent": "payment",
                                            "order_id": order_id,
                                            "amount": amount,
                                            "payment_method": "card",
                                            "checkout_link_sent": True
                                        }
                                    else:
                                        # Default: M-Pesa STK Push
                                        invoice_id = trigger_mpesa_payment(sender_id, amount, order_id)
                                        
                                        # If we get here, STK Push was successful
                                        amount_formatted = f"{amount:,}"
                                        reply_message = f"✅ Payment Request Sent!\n\nPlease check your phone and enter your M-Pesa PIN to complete the payment of KES {amount_formatted}.\n\nWaiting for confirmation..."
                                        send_whatsapp_message(sender_id, reply_message)
                                        logger.info(f"M-Pesa STK Push initiated successfully for order {order_id}, Invoice ID: {invoice_id}")
                                        
                                        return {
                                            "status": "received",
                                            "sender": sender_id,
                                            "intent": "payment",
                                            "order_id": order_id,
                                            "amount": amount,
                                            "payment_method": "mpesa",
                                            "stk_push_sent": True,
                                            "invoice_id": invoice_id
                                        }
                                    
                                except Exception as payment_error:
                                    # Payment processing failed (exception raised from payment_service)
                                    error_msg = str(payment_error)
                                    reply_message = f"❌ Payment request failed. {error_msg}\n\nPlease try again or contact support."
                                    send_whatsapp_message(sender_id, reply_message)
                                    logger.error(f"Payment processing failed for order {order_id}: {error_msg}")
                                    
                                    return {
                                        "status": "error",
                                        "sender": sender_id,
                                        "intent": "payment",
                                        "order_id": order_id,
                                        "error": error_msg
                                    }
                            
                            except DatabaseError as e:
                                logger.error(f"Database error during payment: {str(e)}")
                                reply_message = "System maintenance: Unable to process payment. Please try again later."
                                send_whatsapp_message(sender_id, reply_message)
                                return {
                                    "status": "error",
                                    "message": "Database unavailable"
                                }
                            except Exception as e:
                                logger.error(f"Unexpected error during payment: {str(e)}")
                                reply_message = "System error: Unable to process payment. Please try again."
                                send_whatsapp_message(sender_id, reply_message)
                                return {
                                    "status": "error",
                                    "message": "Payment processing failed"
                                }
                        
                        # Check if user sent a number (for item selection)
                        text_stripped = text_body.strip()
                        if text_stripped.isdigit():
                            digit = int(text_stripped)
                            
                            # Get user's last search results
                            search_results = get_user_search_results(sender_id)
                            
                            if not search_results or len(search_results) == 0:
                                # No search history
                                reply_message = "Please search for an item first (e.g., type 'TVs')."
                                send_whatsapp_message(sender_id, reply_message)
                                return {
                                    "status": "received",
                                    "sender": sender_id,
                                    "intent": "number_selection",
                                    "error": "no_search_history"
                                }
                            
                            # Validate digit is within range
                            if digit < 1 or digit > len(search_results):
                                max_num = len(search_results)
                                reply_message = f"Please select a valid number from the list (1-{max_num})."
                                send_whatsapp_message(sender_id, reply_message)
                                return {
                                    "status": "received",
                                    "sender": sender_id,
                                    "intent": "number_selection",
                                    "error": "invalid_range",
                                    "max": max_num
                                }
                            
                            # Extract selected item (convert 1-based to 0-based index)
                            selected_item = search_results[digit - 1]
                            item_name = selected_item.get("name", "Unknown")
                            item_price = selected_item.get("price", 0)
                            item_sku = selected_item.get("sku", "")
                            
                            # Save selected item to last_selected_product (for payment flow)
                            try:
                                supabase = get_supabase_client()
                                supabase.table("users").update({
                                    "last_selected_product": selected_item
                                }).eq("phone", sender_id).execute()
                                logger.info(f"Saved selected product for user {sender_id}: {item_name}")
                            except Exception as e:
                                logger.warning(f"Failed to save selected product for user {sender_id}: {str(e)}")
                            
                            # Reply with confirmation (pre-payment)
                            price_formatted = f"{item_price:,}"
                            reply_message = f"You selected {item_name}. Price: KES {price_formatted}. Reply with 'Pay {item_price}' to confirm."
                            send_whatsapp_message(sender_id, reply_message)
                            
                            logger.info(f"User {sender_id} selected item #{digit}: {item_name} (SKU: {item_sku})")
                            
                            # Return early - treat as if they typed the item name
                            # The user will need to send "Pay [Amount]" next, which will be processed normally
                            return {
                                "status": "received",
                                "sender": sender_id,
                                "intent": "number_selection",
                                "selected_item": selected_item,
                                "message_sent": True
                            }
                        
                        # Analyze message using OpenAI service
                        analysis = analyze_message(text_body)
                        
                        # Log parsed JSON from OpenAI
                        logger.info(f"OpenAI analysis result: {analysis}")
                        
                        # Handle greeting and unclear intents - send WhatsApp reply immediately
                        intent = analysis.get("intent")
                        if intent in ["greeting", "unclear"]:
                            reply_message = analysis.get("message", "")
                            if reply_message:
                                # Send WhatsApp reply
                                message_sent = send_whatsapp_message(sender_id, reply_message)
                                if message_sent:
                                    logger.info(f"Sent greeting/unclear reply to {sender_id}: {reply_message}")
                                else:
                                    logger.error(f"Failed to send WhatsApp reply to {sender_id}")
                            else:
                                message_sent = False
                            
                            # Return early for greetings/unclear (no order processing needed)
                            return {
                                "status": "received",
                                "sender": sender_id,
                                "intent": intent,
                                "message_sent": message_sent
                            }
                        
                        # Handle search intent - find products by category
                        if intent == "search":
                            search_term = analysis.get("search_term", "")
                            if search_term:
                                try:
                                    products = find_products(search_term, limit=3)
                                    
                                    if products:
                                        # Save search results to user's last_search_results (UPSERT)
                                        upsert_success = upsert_user_search_results(sender_id, products)
                                        if upsert_success:
                                            logger.info(f"Saved search results for user {sender_id}: {len(products)} products")
                                        else:
                                            logger.warning(f"Failed to save search results for user {sender_id}, but continuing...")
                                        
                                        # Format product list
                                        product_lines = []
                                        for idx, product in enumerate(products, 1):
                                            name = product.get("name", "Unknown")
                                            price = product.get("price", 0)
                                            # Format price with comma separators
                                            price_formatted = f"{price:,}"
                                            product_lines.append(f"{idx}. {name} - KES {price_formatted}")
                                        
                                        # Build reply message with updated footer
                                        reply_message = "\n".join(product_lines)
                                        reply_message += "\n\nReply with the **Number** (e.g., '1') or the **Name** of the item to order."
                                        
                                        # Send WhatsApp reply
                                        message_sent = send_whatsapp_message(sender_id, reply_message)
                                        if message_sent:
                                            logger.info(f"Sent search results to {sender_id} for '{search_term}': {len(products)} products")
                                        else:
                                            logger.error(f"Failed to send search results to {sender_id}")
                                    else:
                                        # No products found
                                        reply_message = "Sorry, we don't have those in stock right now."
                                        message_sent = send_whatsapp_message(sender_id, reply_message)
                                        if message_sent:
                                            logger.info(f"Sent 'no stock' message to {sender_id} for '{search_term}'")
                                        else:
                                            logger.error(f"Failed to send 'no stock' message to {sender_id}")
                                    
                                    return {
                                        "status": "received",
                                        "sender": sender_id,
                                        "intent": "search",
                                        "search_term": search_term,
                                        "products_found": len(products) if products else 0,
                                        "message_sent": message_sent
                                    }
                                    
                                except DatabaseError as e:
                                    logger.error(f"Database error during search: {str(e)}")
                                    reply_message = "System maintenance: Database unavailable. Please try again later."
                                    send_whatsapp_message(sender_id, reply_message)
                                    return {
                                        "status": "error",
                                        "message": "Database unavailable"
                                    }
                            else:
                                # Search term missing
                                logger.warning(f"Search intent detected but no search_term provided")
                                return {
                                    "status": "received",
                                    "sender": sender_id,
                                    "intent": "search",
                                    "error": "search_term missing"
                                }
                        
                        # Process items and match to catalog
                        matched_items = []
                        partial_matches = []
                        db_error_occurred = False
                        
                        try:
                            if analysis.get("intent") == "order" and analysis.get("items"):
                                for item in analysis["items"]:
                                    sku = item.get("sku")
                                    qty = item.get("qty", 1)
                                    
                                    # Try to get item by SKU first
                                    catalog_item = None
                                    if sku:
                                        try:
                                            catalog_item = get_item_by_sku(sku)
                                        except DatabaseError as e:
                                            db_error_occurred = True
                                            logger.error(f"Database error while fetching SKU '{sku}': {str(e)}")
                                            # Continue processing other items
                                    
                                    # If SKU lookup failed, try name matching
                                    if not catalog_item:
                                        # CRITICAL: Only use item name or SKU, NEVER use message field
                                        search_term = item.get("name") or item.get("sku")
                                        if search_term:
                                            try:
                                                catalog_item = get_item_by_name(search_term)
                                            except DatabaseError as e:
                                                db_error_occurred = True
                                                logger.error(f"Database error while searching for '{search_term}': {str(e)}")
                                        else:
                                            # No name or SKU available - skip this item
                                            logger.warning(f"Item has no name or SKU, skipping: {item}")
                                            partial_matches.append(item)
                                    
                                    if catalog_item:
                                        matched_items.append({
                                            "requested": item,
                                            "catalog_match": catalog_item,
                                            "qty": qty
                                        })
                                        logger.info(f"Matched item: {catalog_item['name']} (SKU: {catalog_item['sku']}) - Price: {catalog_item['price']} KES, Stock: {catalog_item['stock']}")
                                    else:
                                        # Product mismatch - log warning but don't crash
                                        partial_matches.append(item)
                                        logger.warning(f"Product mismatch: Could not find catalog item for '{item.get('name', sku)}'")
                        except DatabaseError as e:
                            # Database connection failed - fail fast
                            db_error_occurred = True
                            logger.error(f"Database connection failed: {str(e)}")
                            return {
                                "status": "error",
                                "message": "System maintenance: Database unavailable. Please try again later."
                            }
                        
                        # Handle reject intent with fallback (prevent silent bot)
                        if intent == "reject":
                            reply_message = analysis.get("message", "")
                            if not reply_message or reply_message.strip() == "":
                                # Fallback for empty reject message
                                reply_message = "I didn't quite catch that. Please select an item number (e.g., '1') or type 'Menu' to start over."
                                logger.warning(f"Empty reject message for user {sender_id}, using fallback")
                            
                            send_whatsapp_message(sender_id, reply_message)
                            return {
                                "status": "received",
                                "sender": sender_id,
                                "intent": "reject",
                                "message_sent": True
                            }
                        
                        # Log final order summary
                        order_summary = {
                            "sender": sender_id,
                            "intent": analysis.get("intent"),
                            "matched_items": len(matched_items),
                            "partial_matches": len(partial_matches),
                            "items": matched_items
                        }
                        logger.info(f"Order summary: {order_summary}")
                        
                        # Return success (no WhatsApp reply yet)
                        return {
                            "status": "received",
                            "sender": sender_id,
                            "analysis": analysis,
                            "matched_items_count": len(matched_items),
                            "partial_matches_count": len(partial_matches),
                            "db_error": db_error_occurred
                        }
    
    # If no messages processed, return success anyway (webhook received)
    logger.info("Webhook received but no text messages found")
    return {"status": "received", "message": "No text messages found"}


# Paystack Webhook Handler (POST)
@app.post("/api/paystack-webhook")
async def handle_paystack_webhook(request: Request):
    """
    Receives payment webhooks from Paystack.
    Verifies signature, updates order status, and sends WhatsApp confirmation.
    """
    # Get Paystack secret key
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    if not paystack_secret:
        logger.error("PAYSTACK_SECRET_KEY not configured")
        raise HTTPException(status_code=500, detail="Webhook configuration error")
    
    # Get raw request body (needed for signature verification)
    body = await request.body()
    
    # Get signature from header
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.warning("Paystack webhook missing x-paystack-signature header")
        raise HTTPException(status_code=401, detail="Missing signature")
    
    # Verify signature using HMAC-SHA512
    computed_signature = hmac.new(
        paystack_secret.encode('utf-8'),
        body,
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, signature):
        logger.error("Paystack webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse webhook event
    try:
        event_data = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Paystack webhook JSON: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Log webhook event for debugging
    event_type = event_data.get("event")
    logger.info(f"Paystack webhook received: {event_type}")
    
    # Handle successful payment events
    if event_type in ["charge.success", "transfer.success"]:
        try:
            # Extract payment data
            payment_data = event_data.get("data", {})
            reference = payment_data.get("reference", "")
            amount = payment_data.get("amount", 0)  # Amount in kobo/cents
            customer_email = payment_data.get("customer", {}).get("email", "")
            
            # Extract order_id from reference
            # Format: "ORD-{first 8 chars of order_id}" or "ORD-{first 8 chars}-CARD"
            if reference.startswith("ORD-"):
                ref_parts = reference.replace("ORD-", "").split("-")
                order_id_prefix = ref_parts[0]
                
                # Find order in database by matching first 8 characters of order_id
                # Only fetch PENDING orders to reduce load
                supabase = get_supabase_client()
                orders_response = supabase.table("orders").select("*").eq("status", "PENDING").execute()
                
                # Search for order where order_id starts with the prefix
                matching_order = None
                for order in orders_response.data:
                    order_id = order.get("order_id", "")
                    # Compare first 8 characters (order_id_prefix is 8 chars)
                    if len(order_id) >= 8 and order_id[:8] == order_id_prefix:
                        matching_order = order
                        break
                
                if not matching_order:
                    logger.warning(f"No PENDING order found matching reference: {reference} (prefix: {order_id_prefix})")
                    return {"status": "ok", "message": "Order not found or already processed"}
                
                order_id = matching_order.get("order_id")
                user_phone = matching_order.get("user_phone")
                current_status = matching_order.get("status", "PENDING")
                
                # Only update if order is still PENDING (prevent duplicate updates)
                if current_status == "PENDING":
                    # Update order status to PAID
                    update_data = {
                        "status": "PAID",
                        "mpesa_receipt": reference  # Store Paystack reference
                    }
                    
                    supabase.table("orders").update(update_data).eq("order_id", order_id).execute()
                    logger.info(f"Order {order_id} updated to PAID. Reference: {reference}")
                    
                    # Convert amount from cents to KES and format with commas
                    amount_kes = int(amount / 100)
                    amount_formatted = f"{amount_kes:,}"
                    
                    # Generate short ID (last 5 characters, uppercase)
                    short_id = order_id[-5:].upper()
                    
                    # Send premium WhatsApp confirmation message to customer
                    if user_phone:
                        customer_message = f"""✅ **PAYMENT RECEIVED!**

Thank you! Your payment of **KES {amount_formatted}** has been confirmed.

🧾 **Order Ref:** #{short_id}
📦 **Status:** Packing in Progress

**What happens next?**
Our dispatch team has been notified. We will call you shortly to arrange delivery/pickup.

_Need help? Call us at 0708-116-809_"""
                        
                        send_whatsapp_message(user_phone, customer_message)
                        logger.info(f"Confirmation message sent to {user_phone} for order {order_id}")
                    
                    # Send admin notification (optional - soft fail)
                    admin_phone = os.environ.get("ADMIN_PHONE")
                    if admin_phone:
                        try:
                            admin_message = f"""💰 **NEW SALE ALERT!**

User: {user_phone}
Amount: KES {amount_formatted}
Ref: #{short_id}

*Please check the dashboard and arrange delivery!*"""
                            
                            send_whatsapp_message(admin_phone, admin_message)
                            logger.info(f"Admin notification sent to {admin_phone} for order {order_id}")
                        except Exception as admin_error:
                            logger.error(f"❌ Failed to notify admin: {str(admin_error)}")
                    else:
                        logger.warning("⚠️ Admin phone not set. Skipping owner alert.")
                else:
                    logger.info(f"Order {order_id} already processed (status: {current_status}), skipping update")
                
                return {"status": "ok", "order_id": order_id}
            else:
                logger.warning(f"Unexpected reference format: {reference}")
                return {"status": "ok", "message": "Reference format not recognized"}
                
        except Exception as e:
            logger.error(f"Error processing Paystack webhook: {str(e)}")
            # Return 200 to prevent Paystack from retrying
            return {"status": "error", "message": str(e)}
    
    # Handle failed payment events
    elif event_type in ["charge.failed", "transfer.failed"]:
        payment_data = event_data.get("data", {})
        reference = payment_data.get("reference", "")
        logger.warning(f"Payment failed for reference: {reference}")
        
        # Optionally update order status to FAILED
        # For now, we'll leave it as PENDING and let user retry
        return {"status": "ok", "message": "Payment failed event received"}
    
    # For other event types, just acknowledge
    else:
        logger.info(f"Unhandled Paystack event type: {event_type}")
        return {"status": "ok", "message": f"Event {event_type} received"}

