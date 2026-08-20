from datetime import datetime
import sqlite3
import streamlit as st
from streamlit_webrtc import RTCConfiguration, webrtc_streamer

# Page configuration
st.set_page_config(
    page_title="Unichat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    section[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
    .chat-box { background-color: #161b22; padding: 12px 16px; border-radius: 6px; border: 1px solid #30363d; margin-bottom: 10px; }
    div.stButton > button { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
    div.stButton > button:hover { background-color: #30363d; color: #ffffff; }
    </style>
""",
    unsafe_allow_html=True,
)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("unichat.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY)")
    cursor.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, user TEXT, text TEXT, time TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS friends (username TEXT, friend_name TEXT, PRIMARY KEY (username, friend_name))")
    cursor.execute("CREATE TABLE IF NOT EXISTS requests (username TEXT, requester TEXT, PRIMARY KEY (username, requester))")
    conn.commit()
    return conn, cursor

conn, cursor = init_db()

# --- INITIALIZATION ---
if "username" not in st.session_state:
    # Set default name to "User"
    default_user = "User"
    # Ensure "User" is in the database
    cursor.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (default_user,))
    conn.commit()
    st.session_state.username = default_user

if "safe_chat" not in st.session_state: st.session_state.safe_chat = True
if "simulate_network_error" not in st.session_state: st.session_state.simulate_network_error = False
if "current_channel" not in st.session_state: st.session_state.current_channel = "General Chat"
if "in_call" not in st.session_state: st.session_state.in_call = False
if "is_muted" not in st.session_state: st.session_state.is_muted = False
if "cam_off" not in st.session_state: st.session_state.cam_off = False
if "inspect_user" not in st.session_state: st.session_state.inspect_user = None
if "blocked_users" not in st.session_state: st.session_state.blocked_users = []

# Helper functions...
def get_friends(username):
    cursor.execute("SELECT friend_name FROM friends WHERE username = ?", (username,))
    return [row[0] for row in cursor.fetchall()]

def get_requests(username):
    cursor.execute("SELECT requester FROM requests WHERE username = ?", (username,))
    return [row[0] for row in cursor.fetchall()]

def get_messages(channel):
    cursor.execute("SELECT user, text, time FROM messages WHERE channel = ?", (channel,))
    rows = cursor.fetchall()
    return [{"user": r[0], "text": r[1], "time": r[2]} for r in rows]

# Group Config
if "groups" not in st.session_state:
    st.session_state.groups = {"General Chat": {"owner": "System", "members": ["User"], "banned": []}}

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"### 🅰️ **{st.session_state.username}**")
    
    with st.expander("⚙️ Edit Profile"):
        new_name = st.text_input("Change Username", value=st.session_state.username)
        if st.button("Update Profile"):
            new_name = new_name.strip()
            if not new_name:
                st.error("Username cannot be empty.")
            else:
                cursor.execute("SELECT username FROM users WHERE username = ?", (new_name,))
                if cursor.fetchone() and new_name != st.session_state.username:
                    st.error(f"The username '{new_name}' is already taken.")
                else:
                    cursor.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (new_name,))
                    conn.commit()
                    st.session_state.username = new_name
                    st.success("Updated!")
                    st.rerun()

    # (Rest of your original sidebar logic remains the same)
    # ... Add Friend, Requests, and Chat navigation code here ...
    # [Paste the rest of your sidebar code from the previous version]

# --- MAIN CONTENT AREA ---
# [Paste the rest of your Main Content Area and Call Interface code here]
