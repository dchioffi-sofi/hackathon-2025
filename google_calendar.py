from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import datetime
import pytz

class GoogleCalendar:
    """
    Handles all interactions with the Google Calendar API.
    """
    def __init__(self, client_id, client_secret, redirect_uri, scopes):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    def get_auth_url(self, slack_user_id):
        """
        Generates the Google OAuth URL for user authorization.
        """
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
        """
        Exchanges the authorization code for access and refresh tokens.
        """
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
        """
        Builds a Google Calendar service object using a refresh token.
        """
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
            except Exception as e:
                print(f"Error refreshing Google token: {e}")
                return None
        return build('calendar', 'v3', credentials=creds)

    def get_upcoming_meetings(self, service, hours_ahead=3):
        """
        Fetches upcoming meetings from the user's primary calendar.
        """
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        time_max = (datetime.datetime.utcnow() + datetime.timedelta(hours=hours_ahead)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        meetings = []
        for event in events:
            if event.get('status') == 'cancelled':
                continue

            user_is_attendee = False
            attendees = event.get('attendees', [])
            for attendee in attendees:
                if attendee.get('self') and attendee.get('responseStatus') in ['accepted', 'tentative']:
                    user_is_attendee = True
                    break
            
            if not attendees or user_is_attendee:
                 meetings.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No Title'),
                    'start': event['start'].get('dateTime', event['start'].get('date')),
                    'end': event['end'].get('dateTime', event['end'].get('date')),
                    'attendees': [{'email': a.get('email'), 'display_name': a.get('displayName')} for a in attendees if a.get('email')],
                    'html_link': event.get('htmlLink')
                })
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