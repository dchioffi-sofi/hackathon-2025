import os
from flask import Flask, request, redirect
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import jwt

from config import Config
from database import Database
from google_calendar import GoogleCalendar
from glean_api import GleanAPI
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

glean_api_client = GleanAPI(Config.GLEAN_BASE_URL, Config.GLEAN_API_KEY)

scheduler = MeetingScheduler(db, google_calendar_client, glean_api_client, slack_app.client, Config)

@slack_app.event("app_home_opened")
def handle_app_home_opened(event, say, client):
    user_id = event["user"]
    user_data = db.get_user(slack_user_id=user_id)
    
    if user_data and user_data.get('google_refresh_token'):
        say(f"Welcome back! Your Google Calendar is connected.")
    else:
        auth_url, state = google_calendar_client.get_auth_url(user_id)
        say(
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"👋 Hey there! To get started, I need access to your Google Calendar."
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Connect Google Calendar"
                            },
                            "style": "primary",
                            "url": auth_url,
                            "action_id": "connect_google_calendar"
                        }
                    ]
                },
            ],
            text="Welcome! Please connect your Google Calendar."
        )

@slack_app.command("/glean-prep")
def handle_glean_prep_command(ack, body, say, client):
    ack()
    user_id = body["user_id"]
    meeting_query = body["text"].strip()

    if not meeting_query:
        say("Please provide a meeting title, e.g., `/glean-prep Q3 Review`")
        return

    user_data = db.get_user(slack_user_id=user_id)
    if not user_data or not user_data.get('google_refresh_token'):
        say("Please connect your Google Calendar first via my App Home.")
        return
    
    say(f"Searching Glean for prep info on '{meeting_query}'...")

    mock_attendees = [{"email": user_data['google_email'], "display_name": "Self"}]

    glean_prep = glean_api_client.summarize_meeting_prep(meeting_query, mock_attendees)

    if glean_prep:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Meeting Prep for: {meeting_query}*"
                }
            },
            {"type": "divider"}
        ]
        if glean_prep['summary']:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Glean Summary:*\n{glean_prep['summary']}"
                }
            })
        say(blocks=blocks, text=f"Here's your prep for {meeting_query}")
    else:
        say(f"Sorry, I couldn't get prep info for '{meeting_query}' from Glean.")

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
        refresh_token, _, _, _, _, expiry_dt, id_token = \
            google_calendar_client.exchange_code_for_tokens(authorization_response)
        
        google_email = None
        if id_token:
            decoded_token = jwt.decode(id_token, options={"verify_signature": False})
            google_email = decoded_token.get('email')
        
        user_info = slack_app.client.users_info(user=slack_user_id)
        slack_email = user_info['user']['profile']['email']

        if refresh_token:
            db.save_user_tokens(slack_user_id, slack_email, google_email, refresh_token, expiry_dt)
            slack_app.client.chat_postMessage(
                channel=slack_user_id,
                text="✅ Google Calendar connected successfully!"
            )
            return "Google Calendar connected successfully! You can close this tab."
        else:
            slack_app.client.chat_postMessage(
                channel=slack_user_id,
                text="❌ Failed to get a refresh token from Google. Please try connecting again."
            )
            return "Failed to connect Google Calendar.", 500

    except Exception as e:
        logger.error(f"Error during Google OAuth callback for user {slack_user_id}: {e}", exc_info=True)
        slack_app.client.chat_postMessage(
            channel=slack_user_id,
            text="❌ An unexpected error occurred during Google Calendar connection."
        )
        return "An error occurred during Google Calendar connection.", 500

@flask_app.before_first_request
def start_scheduler_on_startup():
    scheduler.start()

if __name__ == "__main__":
    flask_app.run(debug=True, port=os.environ.get("PORT", 5000))