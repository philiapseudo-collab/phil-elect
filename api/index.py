"""
FastAPI entry point for Vercel Serverless deployment.
Handles WhatsApp webhook verification and message processing for Phil-Elect.
"""

import os
import logging
import uuid
import re
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import services (relative imports for Vercel)
from .services.openai_service import analyze_message
from .services.catalog_service import get_item_by_name, get_item_by_sku, DatabaseError
from .db.supabase import get_supabase_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                        
                        # Analyze message using OpenAI service
                        analysis = analyze_message(text_body)
                        
                        # Log parsed JSON from OpenAI
                        logger.info(f"OpenAI analysis result: {analysis}")
                        
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
                                        # Try to match using the message context or item name
                                        search_term = item.get("name", analysis.get("message", ""))
                                        if search_term:
                                            try:
                                                catalog_item = get_item_by_name(search_term)
                                            except DatabaseError as e:
                                                db_error_occurred = True
                                                logger.error(f"Database error while searching for '{search_term}': {str(e)}")
                                    
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
                        
                        # Check if user wants to pay (detect "Pay [Amount]" in message)
                        pay_pattern = re.search(r'pay\s+(\d+)', text_body.lower())
                        is_payment_request = pay_pattern is not None or "pay" in text_body.lower()
                        
                        # If payment request and we have matched items, create order
                        if is_payment_request and matched_items and not db_error_occurred:
                            try:
                                # Build order items JSONB array
                                order_items = []
                                total_amount = 0
                                
                                for matched_item in matched_items:
                                    catalog_match = matched_item["catalog_match"]
                                    qty = matched_item["qty"]
                                    price = catalog_match.get("price", 0)
                                    item_total = price * qty
                                    
                                    order_items.append({
                                        "sku": catalog_match.get("sku"),
                                        "qty": qty,
                                        "price": price
                                    })
                                    total_amount += item_total
                                
                                # Generate order ID (UUID)
                                order_id = str(uuid.uuid4())
                                
                                # Insert order into Supabase
                                supabase = get_supabase_client()
                                order_data = {
                                    "order_id": order_id,
                                    "user_phone": sender_id,
                                    "items": order_items,  # JSONB column
                                    "total_amount": total_amount,
                                    "status": "PENDING",
                                    "mpesa_receipt": None
                                }
                                
                                response = supabase.table("orders").insert(order_data).execute()
                                
                                logger.info(f"Order created: {order_id} for user {sender_id}, Total: {total_amount} KES")
                                logger.info(f"Order items: {order_items}")
                                
                            except DatabaseError as e:
                                logger.error(f"Failed to create order: {str(e)}")
                                return {
                                    "status": "error",
                                    "message": "System maintenance: Unable to process order. Please try again later."
                                }
                            except Exception as e:
                                logger.error(f"Unexpected error creating order: {str(e)}")
                                return {
                                    "status": "error",
                                    "message": "System error: Unable to process order."
                                }
                        
                        # Log final order summary
                        order_summary = {
                            "sender": sender_id,
                            "intent": analysis.get("intent"),
                            "matched_items": len(matched_items),
                            "partial_matches": len(partial_matches),
                            "is_payment_request": is_payment_request,
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

