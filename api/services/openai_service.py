"""
OpenAI Service for analyzing WhatsApp messages for Phil-Elect.
Uses gpt-4o-mini for fast response times (Vercel 10s timeout constraint).
"""

import os
import json
from typing import Dict, Any
from openai import OpenAI


def analyze_message(text: str) -> Dict[str, Any]:
    """
    Analyze user message and extract order intent for Phil-Elect.
    Matches user requests to inventory items and handles business rules.
    
    Args:
        text: The WhatsApp message text from the user
        
    Returns:
        Dictionary with analyzed order information.
        Format: {
            "intent": "order" | "reject" | "unclear" | "error",
            "items": [{"sku": "...", "qty": 1}],
            "message": "..."
        }
        
    Error Handling:
        Returns fallback dict if OpenAI times out (>10s) or fails.
        This prevents bot crashes on API failures.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        return {
            "intent": "error",
            "items": [],
            "message": "OpenAI API key not configured"
        }
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Phil-Elect specific system prompt
        system_prompt = """You are a sales assistant for Phil-Elect (Home & Electronics), serving Juja/Nairobi, Kenya.

Your inventory includes:
- TVs: Vision Plus 32" Smart TV
- Kitchen: Ramtons 2-Door Fridge (Silver), Mika Microwave (20L), Von Hotplate (Double)
- Audio: Sony Soundbar (S20R)

Business Rules:
1. Match user requests to our inventory items. Extract the SKU if you can identify the product.
2. If they ask for credit/installments/hire purchase/"Lipa Polepole"/"Deni", politely decline and set intent to "reject".
3. If they ask about warranty, mention: "All items come with a 1-year manufacturer warranty (Ramtons/Sony/Von)."
4. Return ONLY valid JSON. No explanations outside JSON.

Output JSON format:
{
    "intent": "order" | "reject" | "unclear",
    "items": [{"sku": "RMT-2DR-SLV", "qty": 1}],
    "message": "brief context"
}

If you cannot match to a specific SKU, use the product name in the "message" field but leave items empty or use best guess SKU."""
        
        user_prompt = f"User message: {text}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"}  # Force JSON output
        )
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present (fallback)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        # Parse JSON response
        result = json.loads(content)
        
        # Normalize the response format
        if "intent" not in result:
            result["intent"] = "unclear"
        if "items" not in result:
            result["items"] = []
        if "message" not in result:
            result["message"] = ""
            
        return result
        
    except json.JSONDecodeError as e:
        # OpenAI returned invalid JSON
        return {
            "intent": "error",
            "items": [],
            "message": "Failed to parse AI response"
        }
    except Exception as e:
        # Timeout, API error, or any other exception
        return {
            "intent": "error",
            "items": [],
            "message": "System busy. Please try again."
        }

