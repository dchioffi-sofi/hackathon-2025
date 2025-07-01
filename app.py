import os
from flask import Flask, request, redirect
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import jwt

from config import Config
from database import Database
from google_calendar import GoogleCalendar
from scheduler import MeetingScheduler

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

slack_app = App(
    token=Config.SLACK_BOT_TOKEN,
    signing_secret=Config.SLACK_SIGNING_SECRET,
)
slack_handler = SlackRequestHandler(slack_app)

db = Database(Config.DB_HOST, Config.DB_NAME, Config.DB_USER, Config.DB_PASSWORD)
db.connect()

google_calendar_client = GoogleCalendar(
    Config.GOOGLE_CLIENT_ID,
    Config.GOOGLE_CLIENT_SECRET,
    Config.GOOGLE_REDIRECT_URI,
    Config.GOOGLE_SCOPES
)

scheduler = MeetingScheduler(db, google_calendar_client, slack_app.client, Config)

@slack_app.event("app_home_opened")
def handle_app_home_opened(event, client):
    """
    This function now uses client.views_publish to update the App Home.
    """
    user_id = event["user"]
    user_data = db.get_user(slack_user_id=user_id)
    
    blocks = []
    if user_data and user_data.get('google_refresh_token'):
        blocks.append({
            "type": "section",
            "text": { "type": "mrkdwn", "text": "Welcome back! Your Google Calendar is connected."}
        })
    else:
        auth_url, state = google_calendar_client.get_auth_url(user_id)
        blocks.extend([
            {
                "type": "section",
                "text": { "type": "mrkdwn", "text": "👋 Hey there! To get started, I need access to your Google Calendar."}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": { "type": "plain_text", "text": "Connect Google Calendar"},
                        "style": "primary",
                        "url": auth_url,
                        "action_id": "connect_google_calendar"
                    }
                ]
            },
        ])
    
    client.views_publish(
        user_id=user_id,
        view={
            "type": "home",
            "blocks": blocks
        }
    )


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return slack_handler.handle(request)

@flask_app.route("/google_oauth_callback", methods=["GET"])
def google_oauth_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    
    if not code or not state:
        return "Invalid Google OAuth callback.", 400

    slack_user_id = state
    
    try:
        authorization_response = request.url
        refresh_token, _, _, _, _, expiry_dt, id_token = google_calendar_client.exchange_code_for_tokens(authorization_response)
        
        google_email = None
        if id_token:
            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
            google_email = decoded_token.get('email')
        
        user_info = slack_app.client.users_info(user=slack_user_id)
        slack_email = user_info['user']['profile']['email']

        if refresh_token:
            db.save_user_tokens(slack_user_id, slack_email, google_email, refresh_token, expiry_dt)
            slack_app.client.chat_postMessage(channel=slack_user_id, text="✅ Google Calendar connected successfully!")
            return "Google Calendar connected successfully! You can close this tab."
        else:
            slack_app.client.chat_postMessage(channel=slack_user_id, text="❌ Failed to get a refresh token from Google.")
            return "Failed to connect Google Calendar.", 500

    except Exception as e:
        logger.error(f"Error during Google OAuth callback: {e}", exc_info=True)
        slack_app.client.chat_postMessage(channel=slack_user_id, text="❌ An unexpected error occurred.")
        return "An error occurred.", 500

if __name__ == "__main__":
    flask_app.run(host='0.0.0.0', port=8080, debug=True)