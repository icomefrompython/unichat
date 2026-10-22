from datetime import datetime, timedelta
import hashlib
import random
import re
import sqlite3
import string
import streamlit as st
from streamlit_webrtc import RTCConfiguration, webrtc_streamer

# Page configuration
st.set_page_config(
    page_title="Unichat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === HARDCODED OWNER IP CONFIGURATION ===
OWNER_IP_ADDRESS = "YOUR_IP_HERE"


def get_client_ip():
    try:
        if hasattr(st, "context") and hasattr(st.context, "ip_address"):
            ip = st.context.ip_address
            if ip:
                return ip
    except Exception:
        pass
    return "127.0.0.1"


# Initialize Theme & Background state
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Dark"

if "channel_bg" not in st.session_state:
    st.session_state.channel_bg = "#0d1117"

# Custom CSS depending on theme
if st.session_state.theme_mode == "Light":
    bg_color = (
        st.session_state.channel_bg
        if st.session_state.channel_bg != "#0d1117"
        else "#ffffff"
    )
    text_color = "#24292f"
    sidebar_bg = "#f6f8fa"
    border_color = "#d0d7de"
    chat_box_bg = "#f6f8fa"
else:
    bg_color = st.session_state.channel_bg
    text_color = "#e6edf3"
    sidebar_bg = "#161b22"
    border_color = "#30363d"
    chat_box_bg = "#161b22"

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    section[data-testid="stSidebar"] {{ background-color: {sidebar_bg}; border-right: 1px solid {border_color}; }}
    .chat-box {{ background-color: {chat_box_bg}; padding: 12px 16px; border-radius: 6px; border: 1px solid {border_color}; margin-bottom: 10px; }}
    div.stButton > button {{ background-color: {sidebar_bg}; color: {text_color}; border: 1px solid {border_color}; text-align: left; }}
    div.stButton > button:hover {{ background-color: {border_color}; color: {text_color}; }}
    .broadcast-banner {{ background-color: #1f6feb; color: white; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-weight: bold; text-align: center; }}
    .pinned-banner {{ background-color: #21262d; border: 1px solid #f0883e; padding: 10px; border-radius: 6px; margin-bottom: 15px; }}
    .badge-owner {{ background-color: #f0883e; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-left: 6px; }}
    .badge-admin {{ background-color: #238636; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-left: 6px; }}
    .badge-vip {{ background-color: #a371f7; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-left: 6px; }}
    .reply-quote {{ border-left: 3px solid #1f6feb; padding-left: 8px; margin-bottom: 6px; font-size: 0.85em; color: #8b949e; }}
    </style>
""",
    unsafe_allow_html=True,
)


# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("unichat.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            bio TEXT,
            status TEXT,
            last_seen TEXT,
            email TEXT,
            status_emoji TEXT DEFAULT '🟢',
            profile_color TEXT DEFAULT '#1f6feb'
        )
    """
    )
    for col, col_type in [
        ("bio", "TEXT"),
        ("status", "TEXT"),
        ("last_seen", "TEXT"),
        ("email", "TEXT"),
        ("status_emoji", "TEXT DEFAULT '🟢'"),
        ("profile_color", "TEXT DEFAULT '#1f6feb'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trusted_ips (
            username TEXT,
            ip TEXT,
            PRIMARY KEY (username, ip)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS login_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            ip TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            user TEXT,
            text TEXT,
            time TEXT,
            file_url TEXT,
            pinned INTEGER DEFAULT 0,
            reply_to_id INTEGER DEFAULT NULL,
            expires_at TEXT DEFAULT NULL,
            send_at TEXT DEFAULT NULL
        )
    """
    )
    for col, col_type in [
        ("file_url", "TEXT"),
        ("pinned", "INTEGER DEFAULT 0"),
        ("reply_to_id", "INTEGER DEFAULT NULL"),
        ("expires_at", "TEXT DEFAULT NULL"),
        ("send_at", "TEXT DEFAULT NULL"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_messages (
            username TEXT,
            message_id INTEGER,
            PRIMARY KEY (username, message_id)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS group_mutes (
            group_name TEXT,
            username TEXT,
            muted_until TEXT,
            PRIMARY KEY (group_name, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reactions (
            message_id INTEGER,
            emoji TEXT,
            username TEXT,
            PRIMARY KEY (message_id, emoji, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS typing_status (
            channel TEXT,
            username TEXT,
            timestamp TEXT,
            PRIMARY KEY (channel, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            creator TEXT,
            question TEXT,
            options TEXT,
            created_at TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id INTEGER,
            username TEXT,
            option_index INTEGER,
            PRIMARY KEY (poll_id, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS friends (
            username TEXT,
            friend_name TEXT,
            PRIMARY KEY (username, friend_name)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            username TEXT,
            requester TEXT,
            PRIMARY KEY (username, requester)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_reads (
            username TEXT,
            channel TEXT,
            last_read_id INTEGER,
            PRIMARY KEY (username, channel)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS groups (
            group_name TEXT PRIMARY KEY,
            owner TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS group_members (
            group_name TEXT,
            username TEXT,
            PRIMARY KEY (group_name, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS group_bans (
            group_name TEXT,
            username TEXT,
            PRIMARY KEY (group_name, username)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            time TEXT
        )
    """
    )
    conn.commit()
    return conn, cursor


conn, cursor = init_db()


def clean_expired_and_scheduled_messages():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "DELETE FROM messages WHERE expires_at IS NOT NULL AND expires_at < ?",
        (now_str,),
    )
    # Publish scheduled messages whose time has arrived
    cursor.execute(
        "UPDATE messages SET send_at = NULL WHERE send_at IS NOT NULL AND send_at < ?"
        ,
        (now_str,),
    )
    conn.commit()


clean_expired_and_scheduled_messages()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_random_suffix(length=20):
    return "".join(
        random.choices(string.ascii_letters + string.digits, k=length)
    )


# --- PERSISTENT SESSION HANDLING ---
query_params = st.query_params
saved_user = query_params.get("user", "")
saved_token = query_params.get("token", "")

if "authenticated" not in st.session_state:
    if saved_user and saved_token:
        cursor.execute(
            "SELECT password FROM users WHERE username = ?", (saved_user,)
        )
        row = cursor.fetchone()
        if row and row[0] == saved_token:
            st.session_state.authenticated = True
            st.session_state.username = saved_user
        else:
            st.session_state.authenticated = False
            st.session_state.username = ""
    else:
        st.session_state.authenticated = False
        st.session_state.username = ""

if "safe_chat" not in st.session_state:
    st.session_state.safe_chat = True

if "simulate_network_error" not in st.session_state:
    st.session_state.simulate_network_error = False

if "current_channel" not in st.session_state:
    st.session_state.current_channel = "General Chat"

if "in_call" not in st.session_state:
    st.session_state.in_call = False

if "is_muted" not in st.session_state:
    st.session_state.is_muted = False

if "cam_off" not in st.session_state:
    st.session_state.cam_off = False

if "inspect_user" not in st.session_state:
    st.session_state.inspect_user = None

if "inspect_group" not in st.session_state:
    st.session_state.inspect_group = False

if "blocked_users" not in st.session_state:
    st.session_state.blocked_users = []

if "editing_msg_id" not in st.session_state:
    st.session_state.editing_msg_id = None

if "replying_to_msg" not in st.session_state:
    st.session_state.replying_to_msg = None

if "draft_message" not in st.session_state:
    st.session_state.draft_message = ""

# Ensure default General Chat group exists
cursor.execute(
    "INSERT OR IGNORE INTO groups (group_name, owner) VALUES (?, ?)",
    ("General Chat", "System"),
)
conn.commit()

# Update last seen timestamp
if st.session_state.authenticated and st.session_state.username:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE users SET last_seen = ? WHERE username = ?",
        (now_str, st.session_state.username),
    )
    conn.commit()


# Helper functions
def get_friends(username):
    cursor.execute(
        "SELECT friend_name FROM friends WHERE username = ?", (username,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_requests(username):
    cursor.execute(
        "SELECT requester FROM requests WHERE username = ?", (username,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_all_groups(username):
    cursor.execute("SELECT group_name, owner FROM groups")
    all_g = cursor.fetchall()
    valid_groups = []
    for g_name, owner in all_g:
        if g_name == "General Chat":
            valid_groups.append(g_name)
        elif owner == username:
            valid_groups.append(g_name)
        else:
            cursor.execute(
                "SELECT 1 FROM group_members WHERE group_name = ? AND username = ?",
                (g_name, username),
            )
            if cursor.fetchone():
                valid_groups.append(g_name)
    return valid_groups


def get_group_owner(group_name):
    cursor.execute(
        "SELECT owner FROM groups WHERE group_name = ?", (group_name,)
    )
    row = cursor.fetchone()
    return row[0] if row else ""


def get_group_members(group_name):
    cursor.execute(
        "SELECT username FROM group_members WHERE group_name = ?", (group_name,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_group_bans(group_name):
    cursor.execute(
        "SELECT username FROM group_bans WHERE group_name = ?", (group_name,)
    )
    return [row[0] for row in cursor.fetchall()]


def is_user_muted_in_group(group_name, username):
    cursor.execute(
        "SELECT muted_until FROM group_mutes WHERE group_name = ? AND username = ?",
        (group_name, username),
    )
    row = cursor.fetchone()
    if row:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if row[0] > now_str:
            return True
    return False


def get_db_channel(user, channel):
    cursor.execute("SELECT 1 FROM groups WHERE group_name = ?", (channel,))
    if cursor.fetchone() or channel == "General Chat":
        return channel
    return f"dm_{'_'.join(sorted([user, channel]))}"


def get_messages(channel):
    db_chan = get_db_channel(st.session_state.username, channel)
    cursor.execute(
        "SELECT id, user, text, time, file_url, pinned, reply_to_id FROM messages WHERE channel = ? AND (send_at IS NULL OR send_at < datetime('now')) ORDER BY id ASC",
        (db_chan,),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "user": r[1],
            "text": r[2],
            "time": r[3],
            "file_url": r[4],
            "pinned": r[5],
            "reply_to_id": r[6],
        }
        for r in rows
    ]


def get_last_message(channel):
    db_chan = get_db_channel(st.session_state.username, channel)
    cursor.execute(
        "SELECT user, text, time FROM messages WHERE channel = ? AND (send_at IS NULL OR send_at < datetime('now')) ORDER BY id DESC LIMIT 1",
        (db_chan,),
    )
    row = cursor.fetchone()
    if row:
        return f"{row[0]}: {row[1]}", row[2]
    return "No messages yet", ""


def get_unread_count(username, channel):
    db_chan = get_db_channel(username, channel)
    cursor.execute(
        "SELECT last_read_id FROM channel_reads WHERE username = ? AND channel ="
        " ?",
        (username, db_chan),
    )
    row = cursor.fetchone()
    last_read_id = row[0] if row else 0

    cursor.execute(
        "SELECT COUNT(*) FROM messages WHERE channel = ? AND id > ? AND user !="
        " ? AND (send_at IS NULL OR send_at < datetime('now'))",
        (db_chan, last_read_id, username),
    )
    count_row = cursor.fetchone()
    return count_row[0] if count_row else 0


def mark_channel_read(username, channel):
    db_chan = get_db_channel(username, channel)
    cursor.execute(
        "SELECT MAX(id) FROM messages WHERE channel = ?", (db_chan,)
    )
    row = cursor.fetchone()
    max_id = row[0] if row and row[0] else 0

    cursor.execute(
        """
        INSERT INTO channel_reads (username, channel, last_read_id) 
        VALUES (?, ?, ?) 
        ON CONFLICT(username, channel) DO UPDATE SET last_read_id = ?
    """,
        (username, db_chan, max_id, max_id),
    )
    conn.commit()


def get_reactions(message_id):
    cursor.execute(
        "SELECT emoji, username FROM reactions WHERE message_id = ?",
        (message_id,),
    )
    rows = cursor.fetchall()
    reaction_map = {}
    for emoji, uname in rows:
        if emoji not in reaction_map:
            reaction_map[emoji] = []
        reaction_map[emoji].append(uname)
    return reaction_map


def get_user_badge_html(username, current_channel):
    if username == "System":
        return '<span class="badge-admin">🤖 System</span>'
    if username == "@Unichat Bot":
        return '<span class="badge-admin">🤖 AI Bot</span>'

    g_owner = get_group_owner(current_channel)
    if g_owner == username and current_channel != "General Chat":
        return '<span class="badge-owner">👑 Owner</span>'

    cursor.execute("SELECT ip FROM trusted_ips WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row and row[0] == OWNER_IP_ADDRESS:
        return '<span class="badge-admin">🛡️ Admin</span>'

    if len(username) > 15:
        return '<span class="badge-vip">🌟 VIP</span>'

    return ""


def extract_media_html(text):
    yt_match = re.search(
        r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        text,
    )
    if yt_match:
        video_id = yt_match.group(1)
        return f'<br><iframe width="100%" height="220" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen style="margin-top: 8px; border-radius: 6px;"></iframe>'

    img_match = re.search(
        r"(https?://\S+\.(?:png|jpg|jpeg|gif|webp))", text, re.IGNORECASE
    )
    if img_match:
        return f'<br><img src="{img_match.group(1)}" style="max-width: 300px; border-radius: 6px; margin-top: 8px;">'

    return ""


BAD_WORDS = [
    "shit",
    "fuck",
    "bitch",
    "ass",
    "damn",
    "crap",
    "bastard",
    "dick",
    "piss",
    "slut",
    "whore",
    "spam",
]


def filter_message(text):
    if st.session_state.safe_chat:
        words = text.split()
        filtered_words = [
            "***" if word.lower() in BAD_WORDS else word for word in words
        ]
        return " ".join(filtered_words)
    return text


# --- AUTHENTICATION SCREEN ---
if not st.session_state.authenticated:
    st.title("💬 Welcome to Unichat")
    st.markdown("Please log in or create an account to start chatting.")

    auth_tab1, auth_tab2, auth_tab3 = st.tabs(
        ["🔑 Login", "📝 Sign Up", "❓ Forgot Details"]
    )

    with auth_tab1:
        with st.form("login_form"):
            log_user = st.text_input("Full Username (with suffix)").strip()
            log_pass = st.text_input("Password", type="password")
            remember_me = st.checkbox("Remember Me", value=True)
            log_btn = st.form_submit_button("Log In")

            if log_btn:
                if not log_user or not log_pass:
                    st.error("Please fill in all fields.")
                else:
                    cursor.execute(
                        "SELECT password FROM users WHERE username = ?",
                        (log_user,),
                    )
                    row = cursor.fetchone()
                    hashed_pw = hash_password(log_pass)
                    if row and row[0] == hashed_pw:
                        current_ip = get_client_ip()

                        cursor.execute(
                            "SELECT 1 FROM trusted_ips WHERE username = ? AND ip = ?",
                            (log_user, current_ip),
                        )
                        is_trusted = cursor.fetchone()

                        if is_trusted or not cursor.execute(
                            "SELECT 1 FROM trusted_ips WHERE username = ?",
                            (log_user,),
                        ).fetchone():
                            cursor.execute(
                                "INSERT OR IGNORE INTO trusted_ips (username, ip) VALUES (?, ?)",
                                (log_user, current_ip),
                            )
                            conn.commit()
                            st.session_state.authenticated = True
                            st.session_state.username = log_user
                            if remember_me:
                                st.query_params["user"] = log_user
                                st.query_params["token"] = hashed_pw
                            st.success("Logged in successfully!")
                            st.rerun()
                        else:
                            cursor.execute(
                                "INSERT INTO login_requests (username, ip) VALUES (?, ?)",
                                (log_user, current_ip),
                            )
                            conn.commit()
                            st.error(
                                "⚠️ Unrecognized IP address! A login access"
                                " request has been sent to the account owner"
                                " for approval."
                            )
                    else:
                        st.error("Invalid username or password.")

    with auth_tab2:
        client_ip = get_client_ip()

        with st.form("signup_form"):
            sign_user = st.text_input("Choose a Base Username").strip()
            sign_email = st.text_input("Email Address").strip()
            sign_pass = st.text_input("Choose a Password", type="password")
            remember_signup = st.checkbox(
                "Remember Me", value=True, key="signup_rem"
            )
            sign_btn = st.form_submit_button("Sign Up")

            if sign_btn:
                sign_user = sign_user.strip()
                if not sign_user or not sign_pass or not sign_email:
                    st.error("Please fill in all fields.")
                elif len(sign_user) < 3:
                    st.error("Username must be at least 3 characters long.")
                else:
                    unique_handle = f"{sign_user}_{generate_random_suffix(24)}"
                    hashed_pw = hash_password(sign_pass)

                    cursor.execute(
                        "INSERT INTO users (username, password, bio, status,"
                        " last_seen, email) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            unique_handle,
                            hashed_pw,
                            "Hey there! I am using Unichat.",
                            "🟢 Online",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            sign_email,
                        ),
                    )
                    cursor.execute(
                        "INSERT OR IGNORE INTO trusted_ips (username, ip)"
                        " VALUES (?, ?)",
                        (unique_handle, client_ip),
                    )
                    conn.commit()
                    st.session_state.authenticated = True
                    st.session_state.username = unique_handle
                    if remember_signup:
                        st.query_params["user"] = unique_handle
                        st.query_params["token"] = hashed_pw
                    st.success(
                        f"Account created successfully! Your full handle is:"
                        f" {unique_handle}"
                    )
                    st.rerun()

    with auth_tab3:
        st.markdown("### Recover Account")
        recovery_choice = st.radio(
            "What do you need help with?",
            ["Forgot Username?", "Forgot Password?"],
        )

        if recovery_choice == "Forgot Username?":
            with st.form("forgot_user_form"):
                rec_email = st.text_input(
                    "Enter your registered email"
                ).strip()
                rec_btn = st.form_submit_button("Retrieve Username")
                if rec_btn:
                    cursor.execute(
                        "SELECT username FROM users WHERE email = ?",
                        (rec_email,),
                    )
                    rows = cursor.fetchall()
                    if rows:
                        usernames = [r[0] for r in rows]
                        st.success(
                            f"✅ Email found! Associated username(s):"
                            f" {', '.join(usernames)}"
                        )
                    else:
                        st.error(
                            "No account found associated with that email."
                        )

        else:
            with st.form("forgot_pass_form"):
                f_user = st.text_input("Enter your full username").strip()
                f_email = st.text_input(
                    "Enter your registered email"
                ).strip()
                new_pass = st.text_input(
                    "Enter New Password", type="password"
                )
                reset_btn = st.form_submit_button("Reset Password")
                if reset_btn:
                    cursor.execute(
                        "SELECT username FROM users WHERE username = ? AND email"
                        " = ?",
                        (f_user, f_email),
                    )
                    if cursor.fetchone():
                        cursor.execute(
                            "UPDATE users SET password = ? WHERE username = ?",
                            (hash_password(new_pass), f_user),
                        )
                        conn.commit()
                        st.success(
                            "🔒 Password successfully reset! You can now log in"
                            " with your new password."
                        )
                    else:
                        st.error(
                            "Username and email combination do not match our"
                            " records."
                        )

    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    col_avatar, col_info = st.columns([1, 3])
    with col_avatar:
        st.markdown("### 🅰")
    with col_info:
        st.markdown(f"**{st.session_state.username}**")
        if st.button("Logout", key="logout_btn"):
            st.session_state.authenticated = False
            st.session_state.username = ""
            if "user" in st.query_params:
                del st.query_params["user"]
            if "token" in st.query_params:
                del st.query_params["token"]
            st.rerun()

    st.markdown("---")

    # Analytics Leaderboard Expander
    with st.expander("📈 Channel Leaderboards"):
        cursor.execute(
            "SELECT user, COUNT(*) as msg_count FROM messages GROUP BY user ORDER BY msg_count DESC LIMIT 5"
        )
        top_chatters = cursor.fetchall()
        st.markdown("**Top Contributors:**")
        for c_usr, c_cnt in top_chatters:
            st.caption(f"💬 {c_usr}: {c_cnt} msgs")

    # Saved Messages / Bookmarks Expander
    with st.expander("📌 Saved Bookmarks"):
        cursor.execute(
            "SELECT m.user, m.text, m.time FROM saved_messages s JOIN messages"
            " m ON s.message_id = m.id WHERE s.username = ?",
            (st.session_state.username,),
        )
        saved_items = cursor.fetchall()
        if not saved_items:
            st.caption("No saved messages yet.")
        else:
            for s_usr, s_txt, s_tm in saved_items:
                st.markdown(f"**{s_usr}** ({s_tm}): {s_txt}")

    # Global Search
    with st.expander("🔎 Global Search"):
        g_query = st.text_input(
            "Search Unichat...", placeholder="Messages, users, groups..."
        )
        if g_query.strip():
            q = f"%{g_query.strip()}%"
            cursor.execute(
                "SELECT channel, user, text, time FROM messages WHERE text LIKE"
                " ? ORDER BY id DESC LIMIT 5",
                (q,),
            )
            found_msgs = cursor.fetchall()
            if found_msgs:
                st.markdown("**Messages:**")
                for m_chan, m_usr, m_txt, m_tm in found_msgs:
                    st.caption(f"[{m_chan}] **{m_usr}**: {m_txt} ({m_tm})")

            cursor.execute(
                "SELECT username, status FROM users WHERE username LIKE ? LIMIT"
                " 3",
                (q,),
            )
            found_users = cursor.fetchall()
            if found_users:
                st.markdown("**Users:**")
                for u_name, u_st in found_users:
                    st.caption(f"👤 {u_name} ({u_st})")

    cursor.execute(
        "SELECT id, ip FROM login_requests WHERE username = ?",
        (st.session_state.username,),
    )
    pending_ips = cursor.fetchall()
    if pending_ips:
        with st.expander(
            f"🔔 Device Login Requests ({len(pending_ips)})", expanded=True
        ):
            st.warning("An unknown IP is trying to log into your account!")
            for req_id, req_ip in pending_ips:
                st.write(f"IP: **{req_ip}**")
                col_app1, col_app2 = st.columns(2)
                if col_app1.button("Approve", key=f"app_ip_{req_id}"):
                    cursor.execute(
                        "INSERT OR IGNORE INTO trusted_ips (username, ip)"
                        " VALUES (?, ?)",
                        (st.session_state.username, req_ip),
                    )
                    cursor.execute(
                        "DELETE FROM login_requests WHERE id = ?", (req_id,)
                    )
                    conn.commit()
                    st.success(f"Approved IP {req_ip}!")
                    st.rerun()
                if col_app2.button("Deny", key=f"den_ip_{req_id}"):
                    cursor.execute(
                        "DELETE FROM login_requests WHERE id = ?", (req_id,)
                    )
                    conn.commit()
                    st.rerun()

    # IP-Based Admin Broadcast Check
    current_user_ip = get_client_ip()
    if current_user_ip == OWNER_IP_ADDRESS:
        with st.expander("📢 Send Broadcast Announcement"):
            broadcast_text = st.text_area("Broadcast Message")
            if st.button("Publish Broadcast"):
                if broadcast_text.strip():
                    cursor.execute(
                        "INSERT INTO broadcasts (text, time) VALUES (?, ?)",
                        (
                            broadcast_text.strip(),
                            datetime.now().strftime("%Y-%m-%d %H:%M"),
                        ),
                    )
                    conn.commit()
                    st.success("Broadcast sent to all users!")
                    st.rerun()

    with st.expander("⚙️ Settings & Profile"):
        st.session_state.theme_mode = st.selectbox(
            "🌓 Theme Appearance",
            ["Dark", "Light"],
            index=0 if st.session_state.theme_mode == "Dark" else 1,
        )

        st.session_state.channel_bg = st.color_picker(
            "🎨 Custom Background Color", value=st.session_state.channel_bg
        )

        st.session_state.safe_chat = st.checkbox(
            "🛡 Safe Chat Filter", value=st.session_state.safe_chat
        )
        st.session_state.simulate_network_error = st.checkbox(
            "🔌 Simulate Server/Net Error",
            value=st.session_state.simulate_network_error,
        )

        st.markdown("### Edit Profile")
        cursor.execute(
            "SELECT bio, status, status_emoji, profile_color FROM users WHERE username = ?",
            (st.session_state.username,),
        )
        user_row = cursor.fetchone()
        current_bio = user_row[0] if user_row and user_row[0] else ""
        current_status = (
            user_row[1] if user_row and user_row[1] else "🟢 Online"
        )
        current_emoji = (
            user_row[2] if user_row and user_row[2] else "🟢"
        )
        current_color = (
            user_row[3] if user_row and user_row[3] else "#1f6feb"
        )

        new_emoji = st.selectbox(
            "Status Emoji", ["🟢", "🌙", "🔴", "⭐", "🔥", "💻"], index=0
        )
        new_status = st.selectbox(
            "My Status",
            ["🟢 Online", "🌙 Away", "🔴 Busy", " offline"],
            index=["🟢 Online", "🌙 Away", "🔴 Busy", " offline"].index(
                current_status
            )
            if current_status in ["🟢 Online", "🌙 Away", "🔴 Busy", " offline"]
            else 0,
        )
        new_bio = st.text_input("My Bio / Status Message", value=current_bio)
        new_color = st.color_picker(
            "Profile Theme Accent Color", value=current_color
        )

        if st.button("Save Profile"):
            cursor.execute(
                "UPDATE users SET bio = ?, status = ?, status_emoji = ?, profile_color = ? WHERE username = ?",
                (
                    new_bio,
                    new_status,
                    new_emoji,
                    new_color,
                    st.session_state.username,
                ),
            )
            conn.commit()
            st.success("Profile updated successfully!")
            st.rerun()

    st.markdown("---")

    with st.expander("🔍 Search & Add Friend"):
        search_target = st.text_input(
            "Enter full username (with suffix)", placeholder="e.g. user_Hhdf..."
        )
        if st.button("Send Connection Request"):
            search_target = search_target.strip()
            if search_target and search_target != st.session_state.username:
                cursor.execute(
                    "SELECT username FROM users WHERE username = ?",
                    (search_target,),
                )
                user_found = cursor.fetchone()

                if not user_found:
                    st.error(f"User '{search_target}' does not exist.")
                else:
                    current_friends = get_friends(st.session_state.username)
                    if search_target in current_friends:
                        st.warning("You are already connected.")
                    else:
                        cursor.execute(
                            "INSERT OR IGNORE INTO requests (username,"
                            " requester) VALUES (?, ?)",
                            (search_target, st.session_state.username),
                        )
                        conn.commit()
                        st.success(f"Request sent to {search_target}!")

    with st.expander("➕ Create Group Chat"):
        new_g_name = st.text_input("Group Name", placeholder="e.g. ProjectTeam")
        if st.button("Create Group"):
            new_g_name = new_g_name.strip()
            if not new_g_name:
                st.error("Please enter a group name.")
            else:
                cursor.execute(
                    "SELECT 1 FROM groups WHERE group_name = ?", (new_g_name,)
                )
                if cursor.fetchone():
                    st.error("A group with this name already exists.")
                else:
                    cursor.execute(
                        "INSERT INTO groups (group_name, owner) VALUES (?, ?)",
                        (new_g_name, st.session_state.username),
                    )
                    cursor.execute(
                        "INSERT OR IGNORE INTO group_members (group_name,"
                        " username) VALUES (?, ?)",
                        (new_g_name, st.session_state.username),
                    )
                    conn.commit()
                    st.success(f"Group #{new_g_name} created!")
                    st.session_state.current_channel = new_g_name
                    st.rerun()

    current_requests = get_requests(st.session_state.username)
    with st.expander(f"🔔 Connection Requests ({len(current_requests)})"):
        if not current_requests:
            st.write("No pending requests.")
        else:
            for req in list(current_requests):
                col_r1, col_r2 = st.columns(2)
                st.write(f"**{req}** wants to connect.")
                if col_r1.button("Accept", key=f"acc_{req}"):
                    cursor.execute(
                        "INSERT OR IGNORE INTO friends (username, friend_name)"
                        " VALUES (?, ?)",
                        (st.session_state.username, req),
                    )
                    cursor.execute(
                        "INSERT OR IGNORE INTO friends (username, friend_name)"
                        " VALUES (?, ?)",
                        (req, st.session_state.username),
                    )
                    cursor.execute(
                        "DELETE FROM requests WHERE username = ? AND requester ="
                        " ?",
                        (st.session_state.username, req),
                    )
                    conn.commit()
                    st.success(f"Connected with {req}!")
                    st.rerun()
                if col_r2.button("Reject", key=f"rej_{req}"):
                    cursor.execute(
                        "DELETE FROM requests WHERE username = ? AND requester ="
                        " ?",
                        (st.session_state.username, req),
                    )
                    conn.commit()
                    st.rerun()

    search_filter = st.text_input(
        "Filter list...",
        placeholder="Filter list...",
        label_visibility="collapsed",
    )

    st.markdown("---")

    st.markdown("### 💬 Direct Messages")
    current_friends = get_friends(st.session_state.username)
    for friend in current_friends:
        if friend not in st.session_state.blocked_users:
            if search_filter.lower() in friend.lower():
                is_active = st.session_state.current_channel == friend
                unread = get_unread_count(st.session_state.username, friend)

                cursor.execute(
                    "SELECT status_emoji FROM users WHERE username = ?",
                    (friend,),
                )
                f_row = cursor.fetchone()
                f_status = f_row[0] if f_row and f_row[0] else "🟢"

                icon = "🔴" if is_active else f_status
                last_msg, last_time = get_last_message(friend)

                button_label = (
                    f"{icon} {friend} {unread if unread > 0 else ''}\n\n💬"
                    f"
