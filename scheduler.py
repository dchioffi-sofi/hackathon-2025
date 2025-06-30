from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import datetime
import pytz
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeetingScheduler:
    """
    Schedules and runs the task to check for upcoming meetings.
    """
    def __init__(self, db, google_calendar_service, glean_api_service, slack_client, config):
        self.db = db
        self.google_calendar = google_calendar_service
        self.glean_api = glean_api_service
        self.slack_client = slack_client
        self.config = config
        self.scheduler = BackgroundScheduler(timezone=pytz.utc)
        self.sent_reminders = set()

    def start(self):
        """
        Starts the scheduler.
        """
        self.scheduler.add_job(
            self._check_and_send_reminders,
            IntervalTrigger(minutes=self.config.CALENDAR_CHECK_INTERVAL_MINUTES),
            id='check_calendars_job',
            name='Check Google Calendars for upcoming meetings',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"Scheduler started, checking calendars every {self.config.CALENDAR_CHECK_INTERVAL_MINUTES} minutes.")

    def shutdown(self):
        """
        Shuts down the scheduler.
        """
        self.scheduler.shutdown()
        logger.info("Scheduler shut down.")

    def _check_and_send_reminders(self):
        """
        Checks for upcoming meetings and sends reminders to users.
        """
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
                    self.config.GOOGLE_CLIENT_ID,
                    self.config.GOOGLE_CLIENT_SECRET,
                    "https://oauth2.googleapis.com/token",
                    self.config.GOOGLE_SCOPES
                )

                if not gc_service:
                    continue

                upcoming_meetings = self.google_calendar.get_upcoming_meetings(
                    gc_service,
                    hours_ahead=self.config.REMINDER_WINDOW_HOURS + 1
                )
                
                now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
                reminder_time_end = now_utc + datetime.timedelta(hours=self.config.REMINDER_WINDOW_HOURS)

                for meeting in upcoming_meetings:
                    meeting_start_str = meeting['start']
                    if 'T' in meeting_start_str:
                        meeting_start_dt = datetime.datetime.fromisoformat(meeting_start_str.replace('Z', '+00:00')).astimezone(pytz.utc)
                    else:
                        meeting_start_dt = datetime.datetime.strptime(meeting_start_str, '%Y-%m-%d').replace(tzinfo=pytz.utc)

                    if now_utc <= meeting_start_dt <= reminder_time_end and \
                       (slack_user_id, meeting['id']) not in self.sent_reminders:
                        
                        glean_prep = self.glean_api.summarize_meeting_prep(
                            meeting['summary'],
                            meeting['attendees']
                        )

                        if glean_prep:
                            self._send_slack_reminder(slack_user_id, meeting, glean_prep)
                            self.sent_reminders.add((slack_user_id, meeting['id']))

            except Exception as e:
                logger.error(f"Error processing calendar for user {slack_user_id}: {e}", exc_info=True)

    def _send_slack_reminder(self, slack_user_id, meeting_info, glean_prep):
        """
        Sends a formatted meeting reminder to the user in Slack.
        """
        try:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Upcoming Meeting Reminder: {meeting_info['summary']}*"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"⏰ Starts at: *{datetime.datetime.fromisoformat(meeting_info['start'].replace('Z', '+00:00')).astimezone(pytz.timezone('America/Los_Angeles')).strftime('%Y-%m-%d %I:%M %p %Z')}*"
                        }
                    ]
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

            if glean_prep['prep_notes']:
                notes_list = "\n".join([f"• {note}" for note in glean_prep['prep_notes']])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Preparation Notes:*\n{notes_list}"
                    }
                })

            if glean_prep['questions']:
                questions_list = "\n".join([f"• {q}" for q in glean_prep['questions']])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Possible Questions to Ask:*\n{questions_list}"
                    }
                })
            
            if meeting_info['html_link']:
                    blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{meeting_info['html_link']}|View Meeting in Google Calendar>"
                    }
                })

            self.slack_client.chat_postMessage(
                channel=slack_user_id,
                blocks=blocks,
                text=f"Upcoming meeting: {meeting_info['summary']}"
            )
            logger.info(f"Sent meeting reminder for {meeting_info['summary']} to {slack_user_id}")
        except Exception as e:
            logger.error(f"Error sending Slack reminder to {slack_user_id}: {e}", exc_info=True)