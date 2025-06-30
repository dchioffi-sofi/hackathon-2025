import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Configuration class to store all the application settings.
    """
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
    GOOGLE_SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]

    GLEAN_API_KEY = os.environ.get("GLEAN_API_KEY")
    GLEAN_BASE_URL = "https://api.sofi.com/glean/v1"

    DB_HOST = os.environ.get("DB_HOST")
    DB_NAME = os.environ.get("DB_NAME")
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")

    REMINDER_WINDOW_HOURS = 3
    CALENDAR_CHECK_INTERVAL_MINUTES = 15