from datetime import datetime
import sqlite3
import streamlit as st
from streamlit_webrtc import RTCConfiguration, webrtc_streamer

# Page configuration for a sleek dark mode look
st.set_page_config(
    page_title="Unichat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS matching the dark UI theme
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
    }
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    .chat-box {
        background-color: #161b22;
        padding: 12px 16px;
        border-radius: 6px;
        border: 1px solid #30363d;
        margin-bottom: 10px;
    }
    div.stButton > button {
        background-color: #21262d;
        color: #c9d1d9;
        border: 1px solid #30363d;
    }
    div.stButton > button:hover {
        background-color: #30363d;
        color: #ffffff;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# --- DATABASE SETUP ---
def init_db():
  conn = sqlite3.connect("unichat.db", check_same_thread=False)
  cursor = conn.cursor()
  # Messages table
  cursor.execute(
      """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            user TEXT,
            text TEXT,
            time TEXT
        )
    """
  )
  # Friends table
  cursor.execute(
      """
        CREATE TABLE IF NOT EXISTS friends (
            username TEXT PRIMARY KEY,
            friend_name TEXT
        )
    """
  )
  # Requests table
  cursor.execute(
      """
        CREATE TABLE IF NOT EXISTS requests (
            username TEXT PRIMARY KEY,
            requester TEXT
        )
    """
  )
  conn.commit()
  return conn, cursor


conn, cursor = init_db()

# Initialize Session State defaults
if "username" not in st.session_state:
  st.session_state.username = "AdminMike1"

if "safe_chat" not in st.session_state:
  st.session_state.safe_chat = True

if "simulate_network_error" not in st.session_state:
  st.session_state.simulate_network_error = False

if "current_channel" not in st.session_state:
  st.session_state.current_channel = "WorkSpace"

if "in_call" not in st.session_state:
  st.session_state.in_call = False

if "is_muted" not in st.session_state:
  st.session_state.is_muted = False

if "cam_off" not in st.session_state:
  st.session_state.cam_off = False

if "inspect_user" not in st.session_state:
  st.session_state.inspect_user = None

if "blocked_users" not in st.session_state:
  st.session_state.blocked_users = []

# Populate initial default friends/requests in DB if empty
cursor.execute("SELECT COUNT(*) FROM friends")
if cursor.fetchone()[0] == 0:
  cursor.execute(
      "INSERT OR IGNORE INTO friends (username, friend_name) VALUES (?, ?)",
      ("AdminMike1", "User_Delta"),
  )
  cursor.execute(
      "INSERT OR IGNORE INTO friends (username, friend_name) VALUES (?, ?)",
      ("AdminMike1", "NewBuddy99"),
  )
  cursor.execute(
      "INSERT OR IGNORE INTO requests (username, requester) VALUES (?, ?)",
      ("AdminMike1", "User_Delta"),
  )
  conn.commit()


# Helper fetch functions
def get_friends():
  cursor.execute(
      "SELECT friend_name FROM friends WHERE username = ?",
      (st.session_state.username,),
  )
  return [row[0] for row in cursor.fetchall()]


def get_requests():
  cursor.execute(
      "SELECT requester FROM requests WHERE username = ?",
      (st.session_state.username,),
  )
  return [row[0] for row in cursor.fetchall()]


def get_messages(channel):
  cursor.execute(
      "SELECT user, text, time FROM messages WHERE channel = ?", (channel,)
  )
  rows = cursor.fetchall()
  return [{"user": r[0], "text": r[1], "time": r[2]} for r in rows]


# Groups Configuration (Stored locally or shared)
if "groups" not in st.session_state:
  st.session_state.groups = {
      "General Chat": {
          "owner": "System",
          "members": ["AdminMike1", "User_Delta"],
          "banned": [],
      },
      "WorkSpace": {
          "owner": "AdminMike1",
          "members": ["AdminMike1", "User_Delta"],
          "banned": [],
      },
  }

# Standard list of common swear words to filter when Safe Chat is on
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


# --- SIDEBAR (Left Panel) ---
with st.sidebar:
  col_avatar, col_info = st.columns([1, 3])
  with col_avatar:
    st.markdown("### 🅰️")
  with col_info:
    st.markdown(f"**{st.session_state.username}**")
    if st.button("Logout", key="logout_btn"):
      st.info("Logged out successfully.")

  st.markdown("---")

  with st.expander("⚙️ Edit Profile"):
    new_name = st.text_input(
        "Change Username", value=st.session_state.username
    )
    st.session_state.safe_chat = st.checkbox(
        "🛡️ Safe Chat Filter", value=st.session_state.safe_chat
    )
    st.session_state.simulate_network_error = st.checkbox(
        "🔌 Simulate Server/Net Error",
        value=st.session_state.simulate_network_error,
    )
    if st.button("Update Profile"):
      st.session_state.username = new_name
      st.success("Profile updated!")
      st.rerun()

  st.markdown("---")

  with st.expander("➕ Create Group Chat"):
    new_group_name = st.text_input("Group Name")
    if st.button("Create Group"):
      if new_group_name and new_group_name not in st.session_state.groups:
        st.session_state.groups[new_group_name] = {
            "owner": st.session_state.username,
            "members": [st.session_state.username],
            "banned": [],
        }
        st.success(f"Group '{new_group_name}' created!")
        st.rerun()
      else:
        st.error("Invalid or existing group name.")

  current_requests = get_requests()
  with st.expander(f"🔔 Connection Requests ({len(current_requests)})"):
    if not current_requests:
      st.write("No pending requests.")
    else:
      for req in list(current_requests):
        col_r1, col_r2 = st.columns(2)
        st.write(f"**{req}** wants to talk. Accept/Decline?")
        if col_r1.button("Accept", key=f"acc_{req}"):
          cursor.execute(
              "INSERT OR IGNORE INTO friends (username, friend_name) VALUES"
              " (?, ?)",
              (st.session_state.username, req),
          )
          cursor.execute(
              "DELETE FROM requests WHERE username = ? AND requester = ?",
              (st.session_state.username, req),
          )
          conn.commit()
          st.rerun()
        if col_r2.button("Reject", key=f"rej_{req}"):
          cursor.execute(
              "DELETE FROM requests WHERE username = ? AND requester = ?",
              (st.session_state.username, req),
          )
          conn.commit()
          st.rerun()

  search_filter = st.text_input(
      "Filter list...", placeholder="Filter list...", label_visibility="collapsed"
  )

  st.markdown("---")

  # Direct Messages Section
  st.markdown("### 💬 Direct Messages")
  current_friends = get_friends()
  for friend in current_friends:
    if friend not in st.session_state.blocked_users:
      if search_filter.lower() in friend.lower():
        is_active = st.session_state.current_channel == friend
        icon = "🔴" if is_active else "⚪"
        if st.button(
            f"{icon}  {friend}", key=f"dm_{friend}", use_container_width=True
        ):
          st.session_state.current_channel = friend
          st.rerun()

  st.markdown("---")

  # Group Chats Section
  st.markdown("### 🏢 Group Chats")
  for group in st.session_state.groups:
    if group not in st.session_state.blocked_users:
      if search_filter.lower() in group.lower():
        is_active = st.session_state.current_channel == group
        icon = "🔴" if is_active else "⚪"
        if st.button(
            f"{icon}  #{group}", key=f"grp_{group}", use_container_width=True
        ):
          st.session_state.current_channel = group
          st.rerun()

# --- MAIN CONTENT AREA ---
st.title(
    f"{'#' if st.session_state.current_channel in st.session_state.groups else '💬'} {st.session_state.current_channel}"
)

# Group Owner & Management Controls
curr_group = st.session_state.groups.get(st.session_state.current_channel)
if curr_group and curr_group["owner"] == st.session_state.username:
  with st.expander("🛡️ Group Owner Controls & Settings"):
    renamed_input = st.text_input(
        "Rename Group Chat", value=st.session_state.current_channel
    )
    if st.button("Save New Name"):
      old_name = st.session_state.current_channel
      if (
          renamed_input
          and renamed_input != old_name
          and renamed_input not in st.session_state.groups
      ):
        st.session_state.groups[renamed_input] = (
            st.session_state.groups.pop(old_name)
        )
        cursor.execute(
            "UPDATE messages SET channel = ? WHERE channel = ?",
            (renamed_input, old_name),
        )
        conn.commit()
        st.session_state.current_channel = renamed_input
        st.success("Group renamed successfully!")
        st.rerun()
      else:
        st.error("Invalid name or name already exists.")

    st.markdown("---")
    member_to_ban = st.selectbox(
        "Ban Member",
        [m for m in curr_group["members"] if m != st.session_state.username],
    )
    if st.button("Ban User"):
      if member_to_ban:
        curr_group["members"].remove(member_to_ban)
        curr_group["banned"].append(member_to_ban)
        st.success(f"{member_to_ban} has been banned from the group.")
        st.rerun()

# User Profile Card Inspector Overlay
if st.session_state.inspect_user:
  u = st.session_state.inspect_user
  st.info(f"Inspecting Profile: **{u}**")

  if u == st.session_state.username:
    st.warning("This is your own profile account.")
    if st.button("Close Inspector"):
      st.session_state.inspect_user = None
      st.rerun()
  else:
    current_friends = get_friends()
    col_act1, col_act2, col_act3, col_act4 = st.columns(4)
    if col_act1.button("💬 Talk"):
      if u in current_friends or u in st.session_state.groups:
        st.session_state.current_channel = u
        st.session_state.inspect_user = None
        st.rerun()
      else:
        cursor.execute(
            "INSERT OR IGNORE INTO requests (username, requester) VALUES (?, ?)",
            (u, st.session_state.username),
        )
        conn.commit()
        st.warning(
            f"Connection request sent to {u}! Waiting for them to accept..."
        )
    if col_act2.button("🚫 Block"):
      st.session_state.blocked_users.append(u)
      st.session_state.inspect_user = None
      st.success(f"Blocked {u}.")
      st.rerun()
    if col_act3.button("🗑️ Delete Contact"):
      cursor.execute(
          "DELETE FROM friends WHERE username = ? AND friend_name = ?",
          (st.session_state.username, u),
      )
      conn.commit()
      st.session_state.inspect_user = None
      st.success(f"Removed {u} from contacts.")
      st.rerun()
    if col_act4.button("Close"):
      st.session_state.inspect_user = None
      st.rerun()
  st.markdown("---")

# Action buttons row
col_btn1, col_btn2, col_spacer = st.columns([1, 1, 4])
with col_btn1:
  if st.button("📞 Start Call"):
    st.session_state.in_call = True
with col_btn2:
  if st.button("⚙️ Settings"):
    st.info("Settings panel active.")

# Optimized WebRTC Call Interface with Working Mute & Camera Controls
if st.session_state.in_call:
  st.markdown("### 🔴 Live Video/Audio Call Active")

  cc1, cc2, cc3 = st.columns(3)

  with cc1:
    mute_label = "🔊 Unmute Mic" if st.session_state.is_muted else "🔇 Mute Mic"
    if st.button(mute_label):
      st.session_state.is_muted = not st.session_state.is_muted
      st.rerun()

  with cc2:
    cam_label = (
        "📷 Turn Cam On" if st.session_state.cam_off else "🚫 Turn Cam Off"
    )
    if st.button(cam_label):
      st.session_state.cam_off = not st.session_state.cam_off
      st.rerun()

  with cc3:
    if st.button("🔴 End Call"):
      st.session_state.in_call = False
      st.session_state.is_muted = False
      st.session_state.cam_off = False
      st.rerun()

  # Multi-server configuration to eliminate connection delay & latency
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
          "audio": {
              "echoCancellation": True,
              "noiseSuppression": True,
              "autoGainControl": True,
          }
          if not st.session_state.is_muted
          else False,
          "video": False if st.session_state.cam_off else True,
      },
      async_processing=True,
  )

st.markdown("---")

# Message Display Container
chat_container = st.container()
with chat_container:
  channel_msgs = get_messages(st.session_state.current_channel)
  if not channel_msgs:
    st.info(
        f"No messages in {st.session_state.current_channel} yet. Say hi below!"
    )
  else:
    for idx, msg in enumerate(channel_msgs):
      col_msg_avatar, col_msg_body = st.columns([1, 15])
      with col_msg_avatar:
        if st.button(
            "👤", key=f"prof_{idx}_{msg['user']}={msg['time']}"
        ):
          st.session_state.inspect_user = msg["user"]
          st.rerun()
      with col_msg_body:
        st.markdown(
            f"""
                <div class="chat-box">
                    <strong>{msg['user']}</strong> <span style="font-size: 0.75em; color: #8b949e; float: right;">{msg['time']}</span><br>
                    <div style="margin-top: 5px;">{msg['text']}</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

# Bottom Message Input Box
with st.form(key="message_form", clear_on_submit=True):
  user_input = st.text_input(
      f"Message {st.session_state.current_channel}",
      placeholder=f"Message {st.session_state.current_channel}",
      label_visibility="collapsed",
  )
  submit_btn = st.form_submit_button(label="⬆ Send")

  if submit_btn and user_input:
    is_banned = False
    if curr_group and st.session_state.username in curr_group["banned"]:
      is_banned = True

    if is_banned:
      st.error("You are banned from sending messages in this group.")
    elif st.session_state.simulate_network_error:
      st.error("This message has not been sent. Server or internet problem")
    else:
      cleaned_text = filter_message(user_input)
      timestamp = datetime.now().strftime("%H:%M")

      cursor.execute(
          "INSERT INTO messages (channel, user, text, time) VALUES (?, ?, ?,"
          " ?)",
          (
              st.session_state.current_channel,
              st.session_state.username,
              cleaned_text,
              timestamp,
          ),
      )
      conn.commit()
      st.rerun()
