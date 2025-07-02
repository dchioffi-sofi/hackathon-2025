import psycopg2
from psycopg2 import sql
import logging

# Get the logger instance
logger = logging.getLogger(__name__)

class Database:
    """
    Handles all database operations.
    """
    def __init__(self, host, dbname, user, password):
        self.conn_params = {
            "host": host,
            "dbname": dbname,
            "user": user,
            "password": password
        }
        self.conn = None

    def connect(self):
        """
        Establishes a connection to the database.
        """
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            self.conn.autocommit = True
            self.create_tables()
            print("Database connected successfully.")
        except Exception as e:
            print(f"Error connecting to database: {e}")
            self.conn = None

    def create_tables(self):
        """
        Creates the necessary tables if they don't already exist.
        """
        if not self.conn:
            print("Database not connected, cannot create tables.")
            return

        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    slack_user_id VARCHAR(50) PRIMARY KEY,
                    slack_email VARCHAR(255) UNIQUE NOT NULL,
                    google_email VARCHAR(255) UNIQUE,
                    google_refresh_token TEXT,
                    google_token_expiry TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # ADD THIS NEW TABLE TO TRACK SENT REMINDERS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sent_notifications (
                    slack_user_id VARCHAR(50) NOT NULL,
                    event_id VARCHAR(255) NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (slack_user_id, event_id)
                );
            """)
        print("Tables checked/created.")

    def get_user(self, slack_user_id=None, google_email=None):
        """
        Retrieves a user from the database by Slack user ID or Google email.
        """
        if not self.conn:
            print("Database not connected.")
            return None
        with self.conn.cursor() as cur:
            if slack_user_id:
                cur.execute("SELECT * FROM users WHERE slack_user_id = %s", (slack_user_id,))
            elif google_email:
                cur.execute("SELECT * FROM users WHERE google_email = %s", (google_email,))
            else:
                return None
            user_data = cur.fetchone()
            if user_data:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, user_data))
            return None

    def save_user_tokens(self, slack_user_id, slack_email, google_email, refresh_token, token_expiry):
        """
        Saves or updates a user's Google tokens in the database.
        """
        if not self.conn:
            print("Database not connected.")
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (slack_user_id, slack_email, google_email, google_refresh_token, google_token_expiry)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (slack_user_id) DO UPDATE SET
                        slack_email = EXCLUDED.slack_email,
                        google_email = EXCLUDED.google_email,
                        google_refresh_token = EXCLUDED.google_refresh_token,
                        google_token_expiry = EXCLUDED.google_token_expiry,
                        updated_at = CURRENT_TIMESTAMP;
                """, (slack_user_id, slack_email, google_email, refresh_token, token_expiry))
            print(f"User {slack_user_id} tokens saved/updated.")
            return True
        except Exception as e:
            print(f"Error saving user tokens: {e}")
            return False

    def get_all_authorized_users(self):
        """
        Retrieves all users who have authorized their Google Calendar.
        """
        if not self.conn:
            print("Database not connected.")
            return []
        with self.conn.cursor() as cur:
            cur.execute("SELECT slack_user_id, google_email, google_refresh_token FROM users WHERE google_refresh_token IS NOT NULL;")
            users_data = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, user_data)) for user_data in users_data]

    def record_notification_sent(self, slack_user_id, event_id):
        """Records that a notification for a specific event has been sent."""
        if not self.conn: return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sent_notifications (slack_user_id, event_id)
                    VALUES (%s, %s)
                    ON CONFLICT (slack_user_id, event_id) DO NOTHING;
                """, (slack_user_id, event_id))
            return True
        except Exception as e:
            logger.error(f"Error recording notification sent: {e}")
            return False

    def has_notification_been_sent(self, slack_user_id, event_id):
        """Checks if a notification for a specific event has already been sent."""
        if not self.conn: return True # Default to true to prevent duplicates on db error
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sent_notifications WHERE slack_user_id = %s AND event_id = %s", (slack_user_id, event_id))
            return cur.fetchone() is not None

    def close(self):
        """
        Closes the database connection.
        """
        if self.conn:
            self.conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    from config import Config
    db = Database(Config.DB_HOST, Config.DB_NAME, Config.DB_USER, Config.DB_PASSWORD)
    db.connect()
    db.close()