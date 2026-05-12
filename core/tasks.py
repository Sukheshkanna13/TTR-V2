import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def send_whatsapp_message(phone, template_name, template_data=None):
    """
    Background task to send a WhatsApp message using Interakt API.
    """
    api_key = getattr(settings, 'INTERAKT_API_KEY', None)
    if not api_key:
        logger.warning("Interakt API key not set. Skipping WhatsApp message to %s", phone)
        return False
        
    url = "https://api.interakt.ai/v1/public/message/"
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }
    
    # Format the phone number (assuming India if no country code provided)
    if not phone.startswith('+'):
        phone = f"+91{phone}"
        
    country_code = phone[:3] if phone.startswith('+91') else phone[:2]
    phone_number = phone[3:] if phone.startswith('+91') else phone[2:]
    
    # Strip any spaces or dashes
    phone_number = phone_number.replace(' ', '').replace('-', '')
    country_code = country_code.replace('+', '')
    
    # Prepare traits if any
    traits = {}
    if template_data:
        traits = template_data
        
    payload = {
        "countryCode": country_code,
        "phoneNumber": phone_number,
        "callbackData": f"template_{template_name}",
        "type": "Template",
        "template": {
            "name": template_name,
            "languageCode": "en",
            "bodyValues": [str(v) for v in traits.values()] if traits else []
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("WhatsApp template '%s' sent to %s", template_name, phone)
        return True
    except requests.exceptions.RequestException as e:
        logger.error("Failed to send WhatsApp message: %s", str(e))
        return False
