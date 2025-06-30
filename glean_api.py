import requests
import json

class GleanAPI:
    """
    Handles all interactions with the Glean API.
    """
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def summarize_meeting_prep(self, meeting_title, attendees):
        """
        Calls the Glean API to get meeting preparation information.
        """
        endpoint = f"{self.base_url}/meeting_prep"
        payload = {
            "meeting_title": meeting_title,
            "attendees": [{"email": a['email'], "name": a.get('display_name')} for a in attendees]
        }

        try:
            response = requests.post(endpoint, headers=self.headers, json=payload)
            response.raise_for_status()
            glean_data = response.json()
            return {
                "summary": glean_data.get("summary", "No summary available from Glean."),
                "prep_notes": glean_data.get("prep_notes", []),
                "questions": glean_data.get("questions", [])
            }
        except requests.exceptions.RequestException as e:
            print(f"Error calling Glean API: {e}")
            return None

if __name__ == '__main__':
    from config import Config
    if Config.GLEAN_API_KEY != "YOUR_GLEAN_API_KEY":
        glean = GleanAPI(Config.GLEAN_BASE_URL, Config.GLEAN_API_KEY)
        mock_meeting_title = "Q3 Planning Session"
        mock_attendees = [
            {"email": "john.doe@sofi.com", "display_name": "John Doe"},
            {"email": "jane.smith@sofi.com", "display_name": "Jane Smith"}
        ]
        prep_info = glean.summarize_meeting_prep(mock_meeting_title, mock_attendees)
        if prep_info:
            print("Glean Prep Info:")
            print(f"Summary: {prep_info['summary']}")
    else:
        print("Please set GLEAN_API_KEY in your .env file for Glean API testing.")