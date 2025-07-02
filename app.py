import os
from flask import Flask, request, redirect
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
import jwt

from config import Config
from database import Database
from google_calendar import GoogleCalendar
from scheduler import MeetingScheduler
from test_data import trigger_test_glean_request, MOCK_USERS, get_mock_meetings_for_user

import logging
# This line is added to get more detailed logs
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from werkzeug.middleware.proxy_fix import ProxyFix # Add this line

flask_app = Flask(__name__)
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_proto=1) # Add this line

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
def handle_app_home_opened(event, client, logger):
    try:
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
    except Exception as e:
        logger.error(f"Error in app_home_opened: {e}")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return slack_handler.handle(request)

@flask_app.route("/google_oauth_callback", methods=["GET"])
def google_oauth_callback():
    # --- ADDED LOGGING HERE ---
    logger.info(f"Received Google OAuth callback. Full request URL: {request.url}")

    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        logger.error("Callback missing 'code' or 'state' parameter.")
        return "Invalid Google OAuth callback.", 400

    slack_user_id = state

    try:
        authorization_response = request.url

        # --- ADDED LOGGING HERE ---
        logger.info("Attempting to exchange authorization code for tokens...")

        refresh_token, _, _, _, _, expiry_dt, id_token = google_calendar_client.exchange_code_for_tokens(authorization_response)

        logger.info("Successfully exchanged code for tokens.")

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
            logger.error("No refresh token was received from Google.")
            slack_app.client.chat_postMessage(channel=slack_user_id, text="❌ Failed to get a refresh token from Google.")
            return "Failed to connect Google Calendar.", 500

    except Exception as e:
        logger.error(f"Error during Google OAuth callback for user {slack_user_id}: {e}", exc_info=True)
        slack_app.client.chat_postMessage(channel=slack_user_id, text="❌ An unexpected error occurred.")
        return "An error occurred.", 500

@slack_app.event("message")
def handle_glean_responses(message, client):
    """Listen for Glean bot responses in threads"""
    # Only skip messages from OUR bot to avoid loops
    our_bot_id = client.auth_test()["user_id"]
    if message.get("user") == our_bot_id:
        return
    
    # Only process threaded replies
    if message.get("thread_ts"):
        channel = message.get("channel")
        user_id = message.get("user")
        glean_text = message.get("text", "")
        
        # Only listen in the Glean channel
        if channel == "C093W3B7F9T":  # Your #test-sidesh channel
            logger.info(f"📩 Threaded reply detected in Glean channel from user {user_id}: {glean_text}")
            
            # Check if this is a response to one of our Glean requests
            thread_ts = message.get("thread_ts")
            target_user = scheduler.get_user_for_glean_response(thread_ts)
            
            if target_user:
                logger.info(f"🎯 This is a response to our request! Forwarding to user {target_user}")
                
                # Forward Glean's response to the user
                client.chat_postMessage(
                    channel=target_user,
                    text=f"📋 **Meeting Prep from Glean:**\n\n{glean_text}"
                )
                
                # Clean up the tracking
                scheduler.glean_requests.pop(thread_ts, None)
            else:
                                 logger.info("Not a response to our request, ignoring")

# === TEST ENDPOINTS ===

@flask_app.route("/test/glean", methods=["GET"])
def test_glean_flow():
    """
    Test endpoint to manually trigger Glean request
    Visit: http://localhost:8080/test/glean?user_id=YOUR_SLACK_USER_ID
    """
    user_id = request.args.get("user_id", "U123456789")  # Default test user
    
    try:
        # Get mock meetings for user
        meetings = get_mock_meetings_for_user(user_id)
        
        if not meetings:
            return f"❌ No test meetings found for user {user_id}", 404
        
        # Use first meeting for testing
        meeting = meetings[0]
        
        # Post to Glean
        attendee_emails = [a['email'] for a in meeting['attendees'] if a.get('email')]
        attendee_text = ", ".join(attendee_emails)
        message_text = f"@Glean Prep for meeting: '{meeting['summary']}' with attendees: {attendee_text}"
        
        response = slack_app.client.chat_postMessage(
            channel="C093W3B7F9T", 
            text=message_text
        )
        
        if response.get('ok'):
            message_ts = response['ts']
            # Store tracking info
            scheduler.glean_requests[message_ts] = user_id
            
            return f"""
            ✅ Test Glean request posted!
            
            📅 Meeting: {meeting['summary']}
            👤 User: {user_id}
            📍 Message TS: {message_ts}
            📤 Posted: {message_text}
            
            Now reply to the message in #test-sidesh to test the response flow!
            """
        else:
            return f"❌ Failed to post to Slack: {response}", 500
            
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        return f"❌ Error: {str(e)}", 500

@flask_app.route("/test/status", methods=["GET"])
def test_status():
    """Check what Glean requests are being tracked"""
    return {
        "tracked_requests": len(scheduler.glean_requests),
        "requests": {ts: user_id for ts, user_id in scheduler.glean_requests.items()},
        "mock_users": list(MOCK_USERS.keys())
    }

if __name__ == "__main__":
    flask_app.run(host='0.0.0.0', port=8080, debug=True)