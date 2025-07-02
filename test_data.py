# test_data.py - Hardcoded data for testing Glean flow

import datetime

# Mock user data (simulates database)
MOCK_USERS = {
    "U123456789": {  # Replace with your actual Slack user ID
        "slack_user_id": "U123456789",
        "slack_email": "test@company.com", 
        "google_email": "test@gmail.com",
        "google_refresh_token": "fake_refresh_token"
    }
}

# Mock meeting data (simulates Google Calendar API response)
MOCK_MEETINGS = [
    {
        "id": "meeting_001",
        "summary": "Project Review with Engineering Team",
        "start": "2024-01-15T14:00:00-08:00",
        "end": "2024-01-15T15:00:00-08:00", 
        "attendees": [
            {"email": "john@company.com", "display_name": "John Smith"},
            {"email": "sarah@company.com", "display_name": "Sarah Johnson"},
            {"email": "test@company.com", "display_name": "Test User"}
        ],
        "html_link": "https://calendar.google.com/calendar/event?eid=fake123"
    },
    {
        "id": "meeting_002", 
        "summary": "Client Demo - Q1 Features",
        "start": "2024-01-15T16:30:00-08:00",
        "end": "2024-01-15T17:30:00-08:00",
        "attendees": [
            {"email": "client@external.com", "display_name": "Client Contact"},
            {"email": "demo@company.com", "display_name": "Demo Team"},
            {"email": "test@company.com", "display_name": "Test User"}
        ],
        "html_link": "https://calendar.google.com/calendar/event?eid=fake456"
    },
    {
        "id": "meeting_003",
        "summary": "Weekly Standup",
        "start": "2024-01-16T09:00:00-08:00", 
        "end": "2024-01-16T09:30:00-08:00",
        "attendees": [
            {"email": "team@company.com", "display_name": "Team Lead"},
            {"email": "dev1@company.com", "display_name": "Developer 1"},
            {"email": "test@company.com", "display_name": "Test User"}
        ],
        "html_link": "https://calendar.google.com/calendar/event?eid=fake789"
    }
]

def get_mock_user(slack_user_id):
    """Simulate database.get_user()"""
    return MOCK_USERS.get(slack_user_id)

def get_mock_meetings_for_user(slack_user_id):
    """Simulate getting upcoming meetings for a user"""
    user = get_mock_user(slack_user_id)
    if not user:
        return []
    
    user_email = user["slack_email"]
    
    # Return meetings where user is an attendee
    user_meetings = []
    for meeting in MOCK_MEETINGS:
        attendee_emails = [a["email"] for a in meeting["attendees"]]
        if user_email in attendee_emails:
            user_meetings.append(meeting)
    
    return user_meetings

# Test function to trigger Glean requests manually
def trigger_test_glean_request(scheduler, test_user_id="U123456789"):
    """
    Manually trigger a Glean request for testing
    Usage: trigger_test_glean_request(scheduler, "YOUR_SLACK_USER_ID")
    """
    print(f"🧪 Testing Glean flow for user {test_user_id}")
    
    meetings = get_mock_meetings_for_user(test_user_id)
    
    if not meetings:
        print("❌ No meetings found for test user")
        return
    
    # Use the first meeting for testing
    meeting = meetings[0]
    
    print(f"📅 Found test meeting: {meeting['summary']}")
    
    # Simulate the Glean posting logic from scheduler
    attendee_emails = [a['email'] for a in meeting['attendees'] if a.get('email')]
    attendee_text = ", ".join(attendee_emails)
    message_text = f"@Glean Prep for meeting: '{meeting['summary']}' with attendees: {attendee_text}"
    
    print(f"📤 Would post to Glean: {message_text}")
    
    # Actually post to Glean (uncomment to test)
    # response = scheduler.slack_client.chat_postMessage(
    #     channel="C093W3B7F9T", 
    #     text=message_text
    # )
    # 
    # if response.get('ok'):
    #     message_ts = response['ts']
    #     scheduler.glean_requests[message_ts] = test_user_id
    #     print(f"✅ Posted to Glean, tracking ts: {message_ts}")

if __name__ == "__main__":
    # Quick test
    print("🧪 Mock Data Test")
    print(f"Users: {len(MOCK_USERS)}")
    print(f"Meetings: {len(MOCK_MEETINGS)}")
    
    test_meetings = get_mock_meetings_for_user("U123456789")
    print(f"Test user has {len(test_meetings)} meetings")
    
    for meeting in test_meetings:
        print(f"  - {meeting['summary']}") 