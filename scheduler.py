from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

# The channel ID for #test-sidesh.
SLACK_CHANNEL_ID = "C093W3B7F9T"

class MeetingScheduler:
    def __init__(self, db, google_calendar_service, slack_client, config):
        self.db = db
        self.google_calendar = google_calendar_service
        self.slack_client = slack_client
        self.config = config
        self.scheduler = BackgroundScheduler(timezone=pytz.utc)
        # self.sent_reminders = set() # THIS IS NO LONGER NEEDED

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
                    # CHECK THE DATABASE INSTEAD OF THE IN-MEMORY SET
                    if not self.db.has_notification_been_sent(slack_user_id, meeting['id']):
                        logger.info(f"Meeting found for {slack_user_id}: {meeting['summary']}")

                        attendee_emails = [a['email'] for a in meeting['attendees'] if a.get('email')]
                        attendee_text = ", ".join(attendee_emails)
                        message_text = f"@Glean Prep for meeting: '{meeting['summary']}' with attendees: {attendee_text}"

                        self.slack_client.chat_postMessage(channel=SLACK_CHANNEL_ID, text=message_text)
                        logger.info(f"Posted prep request to Glean channel for meeting '{meeting['summary']}'")
                        
                        # RECORD THE SENT NOTIFICATION IN THE DATABASE
                        self.db.record_notification_sent(slack_user_id, meeting['id'])

            except Exception as e:
                logger.error(f"Error processing calendar for user {slack_user_id}: {e}", exc_info=True)