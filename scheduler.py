from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

# The channel ID for #test-sidesh. 
# Get this by right-clicking the channel in Slack > View channel details > Copy channel ID
SLACK_CHANNEL_ID = "C093W3B7F9T"

class MeetingScheduler:
    def __init__(self, db, google_calendar_service, slack_client, config):
        self.db = db
        self.google_calendar = google_calendar_service
        self.slack_client = slack_client
        self.config = config
        self.scheduler = BackgroundScheduler(timezone=pytz.utc)
        self.sent_reminders = set()
        # Track Glean requests: {message_ts: user_id}
        self.glean_requests = {}

    def start(self):
        self.scheduler.add_job(
            self._check_and_send_reminders,
            IntervalTrigger(minutes=self.config.CALENDAR_CHECK_INTERVAL_MINUTES),
            id='check_calendars_job',
            name='Check Google Calendars',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"Scheduler started.")

    def shutdown(self):
        self.scheduler.shutdown()

    def _check_and_send_reminders(self):
        logger.info("Running scheduled job: Checking calendars...")
        authorized_users = self.db.get_all_authorized_users()

        for user_data in authorized_users:
            slack_user_id = user_data['slack_user_id']
            refresh_token = user_data['google_refresh_token']
            
            if not refresh_token:
                continue

            try:
                gc_service = self.google_calendar.get_calendar_service(
                    refresh_token,
                    self.config.GOOGLE_CLIENT_ID, self.config.GOOGLE_CLIENT_SECRET,
                    "https://oauth2.googleapis.com/token", self.config.GOOGLE_SCOPES
                )
                
                if not gc_service:
                    continue

                upcoming_meetings = self.google_calendar.get_upcoming_meetings(gc_service, hours_ahead=self.config.REMINDER_WINDOW_HOURS)
                
                for meeting in upcoming_meetings:
                    if (slack_user_id, meeting['id']) not in self.sent_reminders:
                        logger.info(f"Meeting found for {slack_user_id}: {meeting['summary']}")
                        
                        # --- New Glean Logic ---
                        attendee_emails = [a['email'] for a in meeting['attendees'] if a.get('email')]
                        attendee_text = ", ".join(attendee_emails)
                        message_text = f"@Glean Prep for meeting: '{meeting['summary']}' with attendees: {attendee_text}"
                        
                        # Post to Glean and capture the timestamp
                        response = self.slack_client.chat_postMessage(channel=SLACK_CHANNEL_ID, text=message_text)
                        
                        if response.get('ok'):
                            message_ts = response['ts']
                            # Store which user this request is for
                            self.glean_requests[message_ts] = slack_user_id
                            logger.info(f"Posted prep request to Glean for {slack_user_id}, tracking ts: {message_ts}")
                        
                        # --- End New Glean Logic ---
                        
                        self.sent_reminders.add((slack_user_id, meeting['id']))
                        
                        # NOTE: This flow sends the request to the @Glean bot.
                        # The next step would be to listen for the Glean bot's response in the channel.
                        # For now, we are just sending the request.

            except Exception as e:
                logger.error(f"Error processing calendar for user {slack_user_id}: {e}", exc_info=True)

    def get_user_for_glean_response(self, thread_ts):
        """
        Check if a thread timestamp corresponds to one of our Glean requests.
        Returns the user_id to notify, or None if not our request.
        """
        return self.glean_requests.get(thread_ts)