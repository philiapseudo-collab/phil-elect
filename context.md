# context.md - Project Context (Phil-Elect Edition)

## 1. Project Overview
**Business Name:** Phil-Elect (Home & Electronics).
**Location:** Kenya (Serving Juja/Nairobi).
**Domain:** Consumer Electronics & Home Appliances (TVs, Fridges, Microwaves, Sound Systems).
**Goal:** Automate sales via WhatsApp. Users verify stock, get a price, and pay via M-Pesa STK Push.

## 2. Business Rules (Strict)
1.  **MVP Scope:** Order -> Pay -> Receipt.
2.  **Payment:** M-Pesa ONLY. No "Lipa Polepole" (Installments). No "Deni".
    * *System Prompt Rule:* If a user asks for installments/hire purchase, politely decline and say we currently only accept full payment via M-Pesa.
3.  **Warranty:** If users ask about warranty, the AI should state: "All items come with a 1-year manufacturer warranty (Ramtons/Sony/Von)."

## 3. Product Examples (For Context)
* **TVs:** "Sony 55 inch", "Vision Plus 32 inch".
* **Kitchen:** "Ramtons 2-door Fridge", "Mika Microwave", "Von Hotplate".
* **Audio:** "JBL Flip 6", "Sony Soundbar".

## 4. Tech Stack (Vercel Deployment)
* **Platform:** Vercel (Python/FastAPI).
* **DB:** Supabase.
* **AI:** OpenAI (gpt-4o-mini).
* **Integration:** WhatsApp Cloud API + Safaricom Daraja.

## 5. Development Modules
* `api/index.py`: Main entry.
* `services/openai_service.py`: Intent extraction. **MUST** handle brand names and model numbers (e.g., "RM-234").
* `services/mpesa_service.py`: STK Push.