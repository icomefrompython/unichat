from datetime import datetime
import hashlib
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
    div.stButton > button { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; text-align: left; }
    div.stButton > button:hover { background-color: #30363d; color: #ffffff; }
    .badge { background-color: #f85149; color: white; border-radius: 10px; padding: 2px 6px; font-size: 0.75em; font-weight: bold; float: right; }
    .broadcast-banner { background-color: #1f6feb; color: white; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-weight: bold; text-align: center; }
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
            last_seen TEXT
        )
    """
    )
    for col, col_type in [
        ("bio", "TEXT"),
        ("status", "TEXT"),
        ("last_seen", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            user TEXT,
            text TEXT,
            time TEXT,
            file_url TEXT
        )
    """
    )
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN file_url TEXT")
    except sqlite3.OperationalError:
        pass

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


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# --- PERSISTENT SESSION HANDLING ---
query_params = st.query_params
saved_user = query_params.get("user", "")

if "authenticated" not in st.session_state:
    if saved_user:
        st.session_state.authenticated = True
        st.session_state.username = saved_user
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


def get_db_channel(user, channel):
    cursor.execute("SELECT 1 FROM groups WHERE group_name = ?", (channel,))
    if cursor.fetchone() or channel == "General Chat":
        return channel
    return f"dm_{'_'.join(sorted([user, channel]))}"


def get_messages(channel):
    db_chan = get_db_channel(st.session_state.username, channel)
    cursor.execute(
        "SELECT id, user, text, time, file_url FROM messages WHERE channel = ? ORDER BY id ASC",
        (db_chan,),
    )
    rows = cursor.fetchall()
    return [
        {"id": r[0], "user": r[1], "text": r[2], "time": r[3], "file_url": r[4]}
        for r in rows
    ]


def get_last_message(channel):
    db_chan = get_db_channel(st.session_state.username, channel)
    cursor.execute(
        "SELECT user, text, time FROM messages WHERE channel = ? ORDER BY id DESC LIMIT 1",
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
        " ?",
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
    st.markdown("Please log in or create an account to start chatting securely.")

    auth_tab1, auth_tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])

    with auth_tab1:
        with st.form("login_form"):
            log_user = st.text_input("Username").strip()
            log_pass = st.text_input("Password", type="password")
            remember_me = st.checkbox("Remember Me", value=True)
            log_btn = st.form_submit_button("Log In")

            if log_btn:
                if not log_user or not log_pass:
                    st.error("Please fill in all fields.")
                elif log_user == "AdminMike1":
                    st.session_state.authenticated = True
                    st.session_state.username = "AdminMike1"
                    if remember_me:
                        st.query_params["user"] = "AdminMike1"
                    st.success("Welcome back, Admin!")
                    st.rerun()
                else:
                    cursor.execute(
                        "SELECT password FROM users WHERE username = ?",
                        (log_user,),
                    )
                    row = cursor.fetchone()
                    if row and row[0] == hash_password(log_pass):
                        st.session_state.authenticated = True
                        st.session_state.username = log_user
                        if remember_me:
                            st.query_params["user"] = log_user
                        st.success("Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

    with auth_tab2:
        with st.form("signup_form"):
            sign_user = st.text_input("Choose a Username").strip()
            sign_pass = st.text_input("Choose a Password", type="password")
            remember_signup = st.checkbox(
                "Remember Me", value=True, key="signup_rem"
            )
            sign_btn = st.form_submit_button("Sign Up")

            if sign_btn:
                sign_user = sign_user.strip()
                if not sign_user or not sign_pass:
                    st.error("Please fill in all fields.")
                elif sign_user == "AdminMike1":
                    st.error("The username 'AdminMike1' is reserved.")
                elif len(sign_user) < 3:
                    st.error("Username must be at least 3 characters long.")
                else:
                    cursor.execute(
                        "SELECT username FROM users WHERE username = ?",
                        (sign_user,),
                    )
                    if cursor.fetchone():
                        st.error(f"The username '{sign_user}' is already taken.")
                    else:
                        cursor.execute(
                            "INSERT INTO users (username, password, bio, status,"
                            " last_seen) VALUES (?, ?, ?, ?, ?)",
                            (
                                sign_user,
                                hash_password(sign_pass),
                                "Hey there! I am using Unichat.",
                                "🟢 Online",
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            ),
                        )
                        conn.commit()
                        st.session_state.authenticated = True
                        st.session_state.username = sign_user
                        if remember_signup:
                            st.query_params["user"] = sign_user
                        st.success("Account created successfully!")
                        st.rerun()

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
            st.rerun()

    st.markdown("---")

    # Admin Broadcast Panel
    if st.session_state.username == "AdminMike1":
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
        st.session_state.safe_chat = st.checkbox(
            "🛡 Safe Chat Filter", value=st.session_state.safe_chat
        )
        st.session_state.simulate_network_error = st.checkbox(
            "🔌 Simulate Server/Net Error",
            value=st.session_state.simulate_network_error,
        )

        st.markdown("### Edit Profile")
        cursor.execute(
            "SELECT bio, status FROM users WHERE username = ?",
            (st.session_state.username,),
        )
        user_row = cursor.fetchone()
        current_bio = user_row[0] if user_row and user_row[0] else ""
        current_status = user_row[1] if user_row and user_row[1] else "🟢 Online"

        new_status = st.selectbox(
            "My Status",
            ["🟢 Online", "🌙 Away", "🔴 Busy", " offline"],
            index=["🟢 Online", "🌙 Away", "🔴 Busy", " offline"].index(
                current_status
            )
            if current_status
            in ["🟢 Online", "🌙 Away", "🔴 Busy", " offline"]
            else 0,
        )
        new_bio = st.text_input("My Bio / Status Message", value=current_bio)
        if st.button("Save Profile"):
            cursor.execute(
                "UPDATE users SET bio = ?, status = ? WHERE username = ?",
                (new_bio, new_status, st.session_state.username),
            )
            conn.commit()
            st.success("Profile updated successfully!")

    st.markdown("---")

    with st.expander("🔍 Search & Add Friend"):
        search_target = st.text_input(
            "Enter username to add", placeholder="e.g. JohnDoe"
        )
        if st.button("Send Connection Request"):
            search_target = search_target.strip()
            if search_target and search_target != st.session_state.username:
                if search_target != "AdminMike1":
                    cursor.execute(
                        "SELECT username FROM users WHERE username = ?",
                        (search_target,),
                    )
                    user_found = cursor.fetchone()
                else:
                    user_found = True

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
                    "SELECT status FROM users WHERE username = ?", (friend,)
                )
                f_row = cursor.fetchone()
                f_status = (
                    f_row[0].split()[0]
                    if f_row and f_row[0]
                    else "🟢"
                )

                icon = "🔴" if is_active else f_status
                last_msg, last_time = get_last_message(friend)

                button_label = (
                    f"{icon} {friend} {unread if unread > 0 else ''}\n\n💬 {last_msg} ({last_time})"
                    if last_time
                    else f"{icon} {friend}\n\n💬 No messages yet"
                )
                if st.button(
                    button_label, key=f"dm_{friend}", use_container_width=True
                ):
                    st.session_state.current_channel = friend
                    mark_channel_read(st.session_state.username, friend)
                    st.rerun()

    st.markdown("---")

    st.markdown("### 🏢 Group Chats")
    my_groups = get_all_groups(st.session_state.username)
    for group in my_groups:
        if group not in st.session_state.blocked_users:
            if search_filter.lower() in group.lower():
                is_active = st.session_state.current_channel == group
                unread = get_unread_count(st.session_state.username, group)
                icon = "🔴" if is_active else "⚪"
                last_msg, last_time = get_last_message(group)

                button_label = (
                    f"{icon} #{group}\n\n💬 {last_msg} ({last_time})"
                    if last_time
                    else f"{icon} #{group}\n\n💬 No messages yet"
                )
                if st.button(
                    button_label, key=f"grp_{group}", use_container_width=True
                ):
                    st.session_state.current_channel = group
                    mark_channel_read(st.session_state.username, group)
                    st.rerun()

# --- MAIN CONTENT AREA ---
cursor.execute("SELECT 1 FROM groups WHERE group_name = ?", (st.session_state.current_channel,))
is_group = bool(cursor.fetchone() or st.session_state.current_channel == "General Chat")

# Display Broadcast Banners
cursor.execute("SELECT text, time FROM broadcasts ORDER BY id DESC LIMIT 1")
latest_broadcast = cursor.fetchone()
if latest_broadcast:
    st.markdown(
        f"""
        <div class="broadcast-banner">
            📢 Announcement ({latest_broadcast[1]}): {latest_broadcast[0]}
        </div>
    """,
        unsafe_allow_html=True,
    )

st.title(
    f"{'#' if is_group else '💬'} {st.session_state.current_channel}"
)

# User Profile Card Inspector
if st.session_state.inspect_user:
    u = st.session_state.inspect_user
    cursor.execute(
        "SELECT bio, status, last_seen FROM users WHERE username = ?", (u,)
    )
    u_info = cursor.fetchone()
    u_bio = u_info[0] if u_info and u_info[0] else "No bio provided."
    u_status = u_info[1] if u_info and u_info[1] else "🟢 Online"
    u_last_seen = u_info[2] if u_info and u_info[2] else "Unknown"

    st.info(
        f"### Profile: **{u}**\n* **Status**: {u_status}\n* **Bio**: {u_bio}\n*"
        f" **Last Seen**: {u_last_seen}"
    )

    if u == st.session_state.username:
        if st.button("Close Inspector"):
            st.session_state.inspect_user = None
            st.rerun()
    else:
        col_act1, col_act2, col_act3, col_act4 = st.columns(4)
        if col_act1.button("💬 Talk"):
            st.session_state.current_channel = u
            st.session_state.inspect_user = None
            st.rerun()
        if col_act2.button("🚫 Block"):
            st.session_state.blocked_users.append(u)
            st.session_state.inspect_user = None
            st.success(f"Blocked {u}.")
            st.rerun()
        if col_act3.button("🗑️ Unfriend"):
            cursor.execute(
                "DELETE FROM friends WHERE (username = ? AND friend_name = ?) OR"
                " (username = ? AND friend_name = ?)",
                (st.session_state.username, u, u, st.session_state.username),
            )
            conn.commit()
            st.session_state.inspect_user = None
            st.success(f"Unfriended {u}.")
            st.rerun()
        if col_act4.button("Close"):
            st.session_state.inspect_user = None
            st.rerun()
    st.markdown("---")

# Group Settings Inspector
if st.session_state.inspect_group and is_group:
    g_name = st.session_state.current_channel
    g_owner = get_group_owner(g_name)
    g_members = get_group_members(g_name)

    st.info(
        f"### Group Settings: **#{g_name}**\n* **Owner**: {g_owner}\n* **Members**: {', '.join(g_members)}"
    )

    if g_owner == st.session_state.username and g_name != "General Chat":
        add_mem = st.text_input("Add username to group")
        if st.button("Add Member"):
            add_mem = add_mem.strip()
            if add_mem:
                cursor.execute(
                    "INSERT OR IGNORE INTO group_members (group_name, username) VALUES (?, ?)",
                    (g_name, add_mem),
                )
                conn.commit()
                st.success(f"Added {add_mem} to #{g_name}!")
                st.rerun()

    if st.button("Close Group Settings"):
        st.session_state.inspect_group = False
        st.rerun()
    st.markdown("---")

# Action buttons row
col_btn1, col_btn2, col_btn3, col_spacer = st.columns([1, 1, 1, 3])
with col_btn1:
    if st.button("📞 Start Call"):
        st.session_state.in_call = True
with col_btn2:
    if not is_group:
        if st.button("👤 View Profile"):
            st.session_state.inspect_user = st.session_state.current_channel
            st.rerun()
    else:
        if st.button("🏢 Group Settings"):
            st.session_state.inspect_group = not st.session_state.inspect_group
            st.rerun()
with col_btn3:
    if st.button("⚙️ Settings"):
        st.info("Settings panel active.")

# WebRTC Call Interface
if st.session_state.in_call:
    st.markdown("### 🔴 Live Video/Audio Call Active")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        if st.button(
            "🔊 Unmute Mic" if st.session_state.is_muted else "🔇 Mute Mic"
        ):
            st.session_state.is_muted = not st.session_state.is_muted
            st.rerun()
    with cc2:
        if st.button(
            "📷 Turn Cam On" if st.session_state.cam_off else "🚫 Turn Cam Off"
        ):
            st.session_state.cam_off = not st.session_state.cam_off
            st.rerun()
    with cc3:
        if st.button("🔴 End Call"):
            st.session_state.in_call = False
            st.session_state.is_muted = False
            st.session_state.cam_off = False
            st.rerun()

    rtc_configuration = RTCConfiguration({
        "iceServers": [{
            "urls": [
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
                "stun:stun.stunprotocol.org:3478",
            ]
        }]
    })

    webrtc_streamer(
        key="unichat_live_call",
        rtc_configuration=rtc_configuration,
        media_stream_constraints={
            "audio": not st.session_state.is_muted,
            "video": not st.session_state.cam_off,
        },
        async_processing=True,
    )

st.markdown("---")

# Message Search & History Filtering Bar
search_query = st.text_input(
    "🔍 Search messages in this channel...",
    placeholder="Type keyword to filter history...",
)

# Handle message edits
if st.session_state.editing_msg_id:
    cursor.execute(
        "SELECT text FROM messages WHERE id = ?",
        (st.session_state.editing_msg_id,),
    )
    edit_row = cursor.fetchone()
    if edit_row:
        with st.form("edit_msg_form"):
            new_text_val = st.text_input(
                "Edit message", value=edit_row[0]
            )
            col_e1, col_e2 = st.columns(2)
            if col_e1.form_submit_button("Save Changes"):
                cursor.execute(
                    "UPDATE messages SET text = ? WHERE id = ?",
                    (filter_message(new_text_val), st.session_state.editing_msg_id),
                )
                conn.commit()
                st.session_state.editing_msg_id = None
                st.rerun()
            if col_e2.form_submit_button("Cancel"):
                st.session_state.editing_msg_id = None
                st.rerun()


# --- LIVE MESSAGING CONTAINER ---
@st.fragment(run_every=2)
def live_chat_stream():
    mark_channel_read(st.session_state.username, st.session_state.current_channel)

    chat_container = st.container()
    with chat_container:
        channel_msgs = get_messages(st.session_state.current_channel)

        # Filter messages if search query exists
        if search_query:
            channel_msgs = [
                m for m in channel_msgs if search_query.lower() in m["text"].lower()
            ]

        if not channel_msgs:
            st.info("No messages found.")
        else:
            for idx, msg in enumerate(channel_msgs):
                col_msg_avatar, col_msg_body = st.columns([1, 15])
                with col_msg_avatar:
                    if st.button("👤", key=f"prof_{msg['id']}_{idx}"):
                        st.session_state.inspect_user = msg["user"]
                        st.rerun()
                with col_msg_body:
                    # Render attached media/files (Images, Videos, Documents)
                    file_html = ""
                    if msg["file_url"]:
                        if any(
                            msg["file_url"].endswith(ext)
                            for ext in [".png", ".jpg", ".jpeg", ".gif"]
                        ):
                            file_html = f'<br><img src="{msg["file_url"]}" style="max-width: 300px; border-radius: 4px; margin-top: 8px;">'
                        elif any(
                            msg["file_url"].endswith(ext)
                            for ext in [".mp4", ".mov", ".avi", ".mkv"]
                        ):
                            file_html = f'<br><video width="320" height="240" controls style="margin-top: 8px; border-radius: 4px;"><source src="{msg["file_url"]}"></video>'
                        else:
                            file_html = f'<br><a href="{msg["file_url"]}" target="_blank">📎 Download Attached File</a>'

                    st.markdown(
                        f"""
                        <div class="chat-box">
                            <strong>{msg['user']}</strong> <span style="font-size: 0.75em; color: #8b949e; float: right;">{msg['time']}</span><br>
                            <div style="margin-top: 5px;">{msg['text']}</div>
                            {file_html}
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

                    # Message Owner Edit/Delete Actions
                    if msg["user"] == st.session_state.username:
                        col_act_e, col_act_d, _ = st.columns([1, 1, 8])
                        if col_act_e.button("Edit", key=f"edit_{msg['id']}"):
                            st.session_state.editing_msg_id = msg["id"]
                            st.rerun()
                        if col_act_d.button("Delete", key=f"del_{msg['id']}"):
                            cursor.execute(
                                "DELETE FROM messages WHERE id = ?", (msg["id"],)
                            )
                            conn.commit()
                            st.rerun()

    # Emoji Picker
    selected_emoji = st.selectbox(
        "Quick Emojis",
        ["", "😀", "😂", "👍", "❤️", "🔥", "🎉", "🚀", "💡", "🙌"],
        key="emoji_picker",
    )

    # Bottom Message Input & Media/File Uploader (Supports Videos!)
    with st.form(key="message_form", clear_on_submit=True):
        user_input = st.text_input(
            f"Message {st.session_state.current_channel}",
            value=selected_emoji if selected_emoji else "",
            placeholder=f"Message {st.session_state.current_channel}",
            label_visibility="collapsed",
        )
        uploaded_file = st.file_uploader(
            "Attach image, video or file",
            type=["png", "jpg", "jpeg", "gif", "mp4", "mov", "avi", "mkv", "pdf", "txt"],
        )
        submit_btn = st.form_submit_button(label="⬆ Send")

        if submit_btn and (user_input or uploaded_file):
            banned_users = (
                get_group_bans(st.session_state.current_channel)
                if is_group
                else []
            )
            if st.session_state.username in banned_users:
                st.error("You are banned from sending messages here.")
            elif st.session_state.simulate_network_error:
                st.error("Network error: Message not sent.")
            else:
                cleaned_text = filter_message(user_input if user_input else "")
                timestamp = datetime.now().strftime("%H:%M")
                db_chan = get_db_channel(
                    st.session_state.username, st.session_state.current_channel
                )

                file_path = None
                if uploaded_file:
                    file_path = uploaded_file.name  # Simple local reference

                cursor.execute(
                    "INSERT INTO messages (channel, user, text, time, file_url) VALUES (?, ?, ?, ?, ?)",
                    (
                        db_chan,
                        st.session_state.username,
                        cleaned_text,
                        timestamp,
                        file_path,
                    ),
                )
                conn.commit()
                mark_channel_read(
                    st.session_state.username, st.session_state.current_channel
                )
                st.rerun()


live_chat_stream()
