import os
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPERVISORA_PHONE = os.getenv("SUPERVISORA_PHONE")
SECRET_KEY = os.getenv("SECRET_KEY", "changeme")
