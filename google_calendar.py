import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import datetime
import pytz
import logging
import json
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

class GoogleCalendar:
    def __init__(self, client_id, client_secret, redirect_uri, scopes):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    def get_auth_url(self, slack_user_id):
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=slack_user_id
        )
        return authorization_url, state

    def exchange_code_for_tokens(self, authorization_response):
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        return credentials.refresh_token, credentials.token_uri, credentials.client_id, credentials.client_secret, credentials.scopes, credentials.expiry, credentials.id_token

    def get_calendar_service(self, refresh_token, client_id, client_secret, token_uri, scopes):
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes
        )
        if not creds.valid or creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Successfully refreshed Google token.")
            except Exception as e:
                logger.error(f"Error refreshing Google token: {e}")
                return None
        return build('calendar', 'v3', credentials=creds)

    def get_upcoming_meetings(self, service, hours_ahead=3):
        # Always work with timezone-aware UTC datetimes for comparison
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        time_max_dt_utc = now_utc + datetime.timedelta(hours=hours_ahead) # Define the datetime object for comparison

        # Format times as ISO strings for the API query
        time_min_query = now_utc.isoformat()
        time_max_query = time_max_dt_utc.isoformat()

        logger.info(f"Querying Google Calendar from {time_min_query} to {time_max_query}")

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min_query,
            timeMax=time_max_query,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        logger.info(f"Received {len(events)} raw events from Google Calendar.")

        meetings = []
        for event in events:
            event_summary = event.get('summary', 'No Summary')
            event_status = event.get('status')

            if event_status == 'cancelled':
                logger.info(f"Skipping cancelled event: {event_summary}")
                continue
            
            # This logic correctly parses timezone-aware datetimes
            event_start_dt_utc = None
            if 'dateTime' in event['start']:
                try:
                    dt_obj = datetime.datetime.fromisoformat(event['start']['dateTime'])
                    event_start_dt_utc = dt_obj.astimezone(pytz.utc)
                except ValueError as e:
                    logger.error(f"Error parsing dateTime for event '{event_summary}': {e}. Skipping.")
                    continue
            elif 'date' in event['start']:
                try:
                    event_start_dt_utc = datetime.datetime.strptime(event['start']['date'], '%Y-%m-%d').replace(tzinfo=pytz.utc)
                except ValueError as e:
                    logger.error(f"Error parsing date for event '{event_summary}': {e}. Skipping.")
                    continue
            
            if not event_start_dt_utc:
                logger.warning(f"Could not determine valid UTC start time for event '{event_summary}'. Skipping.")
                continue

            # The logic to check if an event is in the past was already correct.
            # The bug was the undefined 'time_max_utc' variable in the next check.
            if event_start_dt_utc < now_utc:
                logger.info(f"Skipping event '{event_summary}' because it is in the past. Start: {event_start_dt_utc.isoformat()}")
                continue

            # This check now uses the correctly defined time_max_dt_utc
            if event_start_dt_utc > time_max_dt_utc:
                logger.info(f"Skipping event '{event_summary}' because it is outside the reminder window. Start: {event_start_dt_utc.isoformat()}")
                continue

            user_is_attendee = False
            attendees = event.get('attendees', [])
            is_creator_or_organizer = (event.get('creator', {}).get('self') or event.get('organizer', {}).get('self'))

            if not attendees and is_creator_or_organizer:
                user_is_attendee = True
            elif attendees:
                for attendee in attendees:
                    if attendee.get('self') and attendee.get('responseStatus') in ['accepted', 'tentative', 'needsAction']:
                        user_is_attendee = True
                        break
            
            if user_is_attendee:
                 meetings.append({
                    'id': event['id'],
                    'summary': event_summary,
                    'start': event['start'].get('dateTime', event['start'].get('date')),
                    'end': event['end'].get('dateTime', event['end'].get('date')),
                    'attendees': [{'email': a.get('email'), 'display_name': a.get('displayName')} for a in attendees if a.get('email')],
                    'html_link': event.get('htmlLink')
                })
        
        logger.info(f"Finished processing. Found {len(meetings)} valid meetings to return.")
        return meetings
            
        logger.info(f"Finished processing events. Found {len(meetings)} meetings to return.")
        return meetings

if __name__ == '__main__':
    from config import Config
    TEST_REFRESH_TOKEN = "YOUR_TEST_REFRESH_TOKEN_HERE"
    if TEST_REFRESH_TOKEN != "YOUR_TEST_REFRESH_TOKEN_HERE":
        gc = GoogleCalendar(Config.GOOGLE_CLIENT_ID, Config.GOOGLE_CLIENT_SECRET, Config.GOOGLE_REDIRECT_URI, Config.GOOGLE_SCOPES)
        service = gc.get_calendar_service(TEST_REFRESH_TOKEN, Config.GOOGLE_CLIENT_ID, Config.GOOGLE_CLIENT_SECRET, "https://oauth2.googleapis.com/token", Config.GOOGLE_SCOPES)
        if service:
            meetings = gc.get_upcoming_meetings(service, hours_ahead=24)
            print(f"Found {len(meetings)} upcoming meetings:")
            for meeting in meetings:
                print(f"- {meeting['summary']} at {meeting['start']}")
    else:
        print("Please provide a TEST_REFRESH_TOKEN in google_calendar.py for local testing.")