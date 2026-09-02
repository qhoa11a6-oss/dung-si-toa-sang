import streamlit as st
from datetime import date, datetime
from pathlib import Path
import base64
import sqlite3
import uuid

# ============================================================
# CẤU HÌNH
# ============================================================

st.set_page_config(
    page_title="Dũng Sĩ Tỏa Sáng",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# ĐƯỜNG DẪN ẢNH / VIDEO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "images"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "dung_si_toa_sang.db"

# Mật khẩu khu vực quản trị. Có thể đổi bằng Streamlit Secrets: ADMIN_PASSWORD = "..."
try:
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "291120")
except Exception:
    ADMIN_PASSWORD = "291120"

MEDIA_SIZES = {
    "character": 420,
    "mission": 340,
    "monster": 320,
    "boss": 680,
    "effect": 520,
}

VIDEO_HEIGHT = 520


# ============================================================
# CƠ SỞ DỮ LIỆU & KHO MINH CHỨNG
# ============================================================

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                lop TEXT NOT NULL,
                gender TEXT NOT NULL,
                stars INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                UNIQUE(name COLLATE NOCASE, lop COLLATE NOCASE)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                task_title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                media_path TEXT NOT NULL,
                parent_note TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                reward INTEGER NOT NULL DEFAULT 10,
                FOREIGN KEY(player_id) REFERENCES players(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_player ON submissions(player_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_date ON submissions(submitted_at)")
        conn.commit()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_or_create_player(name, lop, gender):
    name = name.strip()
    lop = lop.strip()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE lower(name)=lower(?) AND lower(lop)=lower(?)",
            (name, lop),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE players SET gender=?, last_seen=? WHERE id=?",
                (gender, now_text(), row["id"]),
            )
            return dict(row) | {"gender": gender, "last_seen": now_text()}

        player_id = uuid.uuid4().hex
        ts = now_text()
        conn.execute(
            "INSERT INTO players(id,name,lop,gender,stars,created_at,last_seen) VALUES(?,?,?,?,0,?,?)",
            (player_id, name, lop, gender, ts, ts),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
        return dict(row)


def update_player_stars(player_id, stars):
    with db_connect() as conn:
        conn.execute("UPDATE players SET stars=?, last_seen=? WHERE id=?", (int(stars), now_text(), player_id))
        conn.commit()


def load_player(player_id):
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    return dict(row) if row else None


def load_today_submissions(player_id):
    today_prefix = str(date.today())
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE player_id=? AND submitted_at LIKE ? ORDER BY submitted_at DESC",
            (player_id, today_prefix + "%"),
        ).fetchall()
    return [dict(r) for r in rows]


def save_submission(player_id, task, uploaded_file, parent_note):
    suffix = Path(uploaded_file.name).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    day_dir = UPLOAD_DIR / str(date.today())
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / safe_name
    target.write_bytes(uploaded_file.getvalue())

    media_type = "video" if suffix in VIDEO_EXTS else "image"
    submission_id = uuid.uuid4().hex
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO submissions(
                id,player_id,task_id,task_title,media_type,original_filename,
                media_path,parent_note,submitted_at,reward
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                submission_id,
                player_id,
                task["id"],
                task["title"],
                media_type,
                uploaded_file.name,
                str(target),
                parent_note.strip(),
                now_text(),
                task["reward"],
            ),
        )
        conn.execute(
            "UPDATE players SET stars=stars+?, last_seen=? WHERE id=?",
            (task["reward"], now_text(), player_id),
        )
        conn.commit()

    return {
        "id": submission_id,
        "task_id": task["id"],
        "media_type": media_type,
        "filename": uploaded_file.name,
        "path": str(target),
        "parent_note": parent_note.strip(),
        "submitted_at": now_text(),
    }


def load_all_players():
    with db_connect() as conn:
        rows = conn.execute("SELECT * FROM players ORDER BY last_seen DESC").fetchall()
    return [dict(r) for r in rows]


def load_all_submissions(player_id=None, class_name=None):
    query = """
        SELECT s.*, p.name, p.lop, p.gender
        FROM submissions s
        JOIN players p ON p.id=s.player_id
        WHERE 1=1
    """
    params = []
    if player_id:
        query += " AND p.id=?"
        params.append(player_id)
    if class_name and class_name != "Tất cả":
        query += " AND p.lop=?"
        params.append(class_name)
    query += " ORDER BY s.submitted_at DESC"
    with db_connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


init_database()
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
VIDEO_EXTS = [".mp4", ".webm", ".mov"]

def find_asset(stem: str):
    for ext in IMAGE_EXTS + VIDEO_EXTS:
        p = IMAGE_DIR / f"{stem}{ext}"
        if p.exists():
            return p
    return None

def show_media(stem: str, size_key="mission"):
    path = find_asset(stem)
    if not path:
        return False

    width = MEDIA_SIZES.get(size_key, MEDIA_SIZES["mission"])
    suffix = path.suffix.lower()

    if suffix in VIDEO_EXTS:
        st.video(str(path))
        return True

    if suffix == ".gif":
        try:
            data = base64.b64encode(path.read_bytes()).decode("utf-8")
            st.markdown(
                f'<div style="width:min(100%, {width}px); margin:auto;">'
                f'<img src="data:image/gif;base64,{data}" '
                f'style="width:100%;height:auto;display:block;'
                f'border-radius:12px; border: 3px solid #b8860b; box-shadow: 0 4px 15px rgba(0,0,0,0.3); object-fit:contain;">'
                f'</div>',
                unsafe_allow_html=True,
            )
        except OSError:
            return False
        return True

    st.image(str(path), width=width)
    return True


# ============================================================
# TRẠNG THÁI GAME
# ============================================================

TODAY = str(date.today())

defaults = {
    "game_started": False,
    "stars": 0,
    "energy": 100,
    "completed_tasks": [],
    "last_day": TODAY,
    "name": "",
    "lop": "",
    "gender": "Nữ",
    "show_reward_fx": False,
    "show_attack_fx": False,
    "show_victory": False,
    "boss_defeated": False,
    "login_effect": False,
    "proofs": {},
    "player_id": "",
    "admin_mode": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Nếu người chơi đã đăng nhập trước đó, lấy dữ liệu thật từ cơ sở dữ liệu.
if st.session_state.player_id:
    saved_player = load_player(st.session_state.player_id)
    if saved_player:
        st.session_state.stars = saved_player["stars"]
        st.session_state.name = saved_player["name"]
        st.session_state.lop = saved_player["lop"]
        st.session_state.gender = saved_player["gender"]

if st.session_state.last_day != TODAY:
    st.session_state.completed_tasks = []
    st.session_state.last_day = TODAY
    st.session_state.show_reward_fx = False
    st.session_state.show_attack_fx = False


# ============================================================
# DỮ LIỆU NHIỆM VỤ (Đã cốt truyện hóa)
# ============================================================

TASKS = [
    {
        "id": "the_duc",
        "station": "Khu rừng Rèn Luyện",
        "icon": "🌲",
        "title": "KHỞI ĐẦU NGÀY MỚI",
        "description": "Dậy sớm vươn vai, ăn sáng, đi học đúng giờ để khởi đầu ngày mới thật khỏe mạnh và tràn đầy năng lượng.",
        "reward": 10,
        "asset": "nhiemvu_theduc",
    },
    {
        "id": "chay_bo",
        "station": "Thảo nguyên Tốc Độ",
        "icon": "⚡",
        "title": "BƯỚC CHÂN THẦN TỐC",
        "description": "Chạy bộ 15 phút để gia tăng tốc độ, giúp dũng sĩ dễ dàng né tránh đòn tấn công.",
        "reward": 10,
        "asset": "nhiemvu_chaybo",
    },
    {
        "id": "an_rau",
        "station": "Làng Thảo Mộc",
        "icon": "🌿",
        "title": "TINH HOA THẢO MỘC",
        "description": "Hấp thụ linh khí từ các loại rau xanh để nhanh chóng hồi phục Sinh lực (HP) sau những giờ chiến đấu.",
        "reward": 10,
        "asset": "nhiemvu_anrau",
    },
]

MONSTERS = [
    {
        "name": "YÊU TINH NGÁP NGỦ",
        "icon": "😴",
        "quote": "Zzz... Đi ngủ thôi, làm dũng sĩ mệt lắm...",
        "asset": "quai_vat_ngu",
        "start": 0,
    },
    {
        "name": "MA THÚ HÁU ĂN",
        "icon": "🍔",
        "quote": "Bỏ thanh kiếm xuống và ăn vặt với ta nào!",
        "asset": "quai_vat_an",
        "start": 50,
    },
    {
        "name": "QUỶ VƯƠNG MÀN HÌNH",
        "icon": "🎮",
        "quote": "Chỉ một ván game nữa thôi... ván cuối cùng...",
        "asset": "quai_vat_game",
        "start": 100,
    },
]


# ============================================================
# CSS: THEME NHẬP VAI - SIÊU CẤP TỎA SÁNG
# ============================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;700;900&family=Playpen+Sans:wght@600;800;900&display=swap');

    /* Nền trang web - Fantasy Light */
    .stApp {
        background-color: #fdfaf2; /* Trắng ngà */
        background-image: radial-gradient(circle at center, #ffffff 0%, #f4ebd8 100%);
    }

    html, body, [class*="css"], p, li, label, .stMarkdown {
        font-family: 'Nunito', sans-serif;
        color: #2b1d17; /* Nâu đen cực đậm cho dễ đọc */
    }

    h1, h2, h3, h4 {
        font-family: 'Playpen Sans', cursive;
        color: #9a1a1a !important; /* Đỏ đô sang trọng */
        font-weight: 900 !important;
    }

    /* Khung chứa nội dung (Bảng Cáo Thị rực rỡ) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px;
        border: 3px solid #d4af37 !important; /* Viền vàng hoàng gia */
        background: linear-gradient(135deg, #ffffff 0%, #fdf5e6 100%);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15), inset 0 0 10px rgba(212, 175, 55, 0.1);
        padding: 5px;
        transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s ease;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 0 15px 35px rgba(212, 175, 55, 0.3), inset 0 0 20px rgba(212, 175, 55, 0.4);
        border-color: #ffdf00 !important;
    }

    /* Sidebar Background */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #fdf5e6 0%, #faebd7 100%);
        border-right: 4px solid #d4af37;
        box-shadow: 3px 0 15px rgba(0,0,0,0.1);
    }
    
    /* Chữ Sidebar */
    section[data-testid="stSidebar"] [class*="css"], section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label {
        color: #3e2723 !important;
    }

    section[data-testid="stSidebar"] input {
        background: #ffffff !important;
        color: #3e2723 !important;
        border: 2px solid #b8860b !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.05);
        transition: box-shadow 0.3s ease, border-color 0.3s ease;
    }
    
    section[data-testid="stSidebar"] input:focus {
        border-color: #ffdf00 !important;
        box-shadow: 0 0 8px rgba(212, 175, 55, 0.6), inset 0 2px 4px rgba(0,0,0,0.05) !important;
    }

    /* Game Titles - GIỮ TRÊN 1 DÒNG VÀ TỎA SÁNG MẠNH HƠN */
    .game-title {
        text-align: center;
        /* Giảm kích thước xíu và dùng white-space để không bị rớt dòng */
        font-size: clamp(2rem, 4.5vw, 4.2rem); 
        white-space: nowrap; 
        font-family: 'Playpen Sans', cursive;
        font-weight: 900;
        color: #d4af37; /* Vàng kim */
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 0px;
        /* Kết hợp hiệu ứng lơ lửng và phát sáng (Glow) */
        animation: floatGlow 3s ease-in-out infinite;
    }

    @keyframes floatGlow {
        0% { 
            transform: translateY(0px); 
            text-shadow: 2px 2px 0px #fff, -1px -1px 0px #8a3d12, 0 0 10px rgba(212,175,55,0.4); 
        }
        50% { 
            transform: translateY(-8px); 
            text-shadow: 2px 2px 0px #fff, -1px -1px 0px #8a3d12, 0 0 25px rgba(255,223,0,0.8), 0 0 40px rgba(255,223,0,0.4); 
        }
        100% { 
            transform: translateY(0px); 
            text-shadow: 2px 2px 0px #fff, -1px -1px 0px #8a3d12, 0 0 10px rgba(212,175,55,0.4); 
        }
    }

    .game-subtitle {
        text-align: center;
        font-size: 1.3rem;
        font-weight: 800;
        color: #5c3a21; /* Nâu gạch */
        font-style: italic;
        text-shadow: 1px 1px 2px rgba(255,255,255,0.8);
        margin-bottom: 2.5rem;
    }

    /* Section Labels - Dấu ấn Hoàng gia */
    .section-label {
        font-size: 1.8rem;
        font-family: 'Playpen Sans', cursive;
        font-weight: 900;
        color: #8b0000;
        text-align: center;
        text-transform: uppercase;
        border-bottom: 2px solid #d4af37;
        padding-bottom: 15px;
        margin-top: 2rem;
        margin-bottom: 1.5rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        position: relative;
    }
    
    .section-label::before, .section-label::after {
        content: "✦";
        color: #d4af37;
        margin: 0 15px;
        font-size: 1.2rem;
        animation: twinkle 2s infinite alternate;
    }
    
    @keyframes twinkle {
        from { opacity: 0.5; transform: scale(0.8); }
        to { opacity: 1; transform: scale(1.2); color: #ffdf00; }
    }

    /* Nút bấm RPG - HIỆU ỨNG NHỊP ĐẬP (PULSE) & 3D */
    .stButton > button {
        border-radius: 12px !important;
        border: 2px solid #ffd700 !important;
        min-height: 55px !important;
        font-size: 1.2rem !important;
        font-weight: 900 !important;
        color: #ffffff !important;
        background: linear-gradient(180deg, #e53935, #b71c1c) !important;
        box-shadow: 0 6px 0 #7f0000, 0 10px 15px rgba(0,0,0,0.3) !important;
        transition: all 0.15s ease;
        font-family: 'Playpen Sans', cursive !important;
        text-transform: uppercase;
        animation: pulseButton 2s infinite;
    }
    
    @keyframes pulseButton {
        0% { box-shadow: 0 6px 0 #7f0000, 0 0 0 0 rgba(229, 57, 53, 0.6); }
        70% { box-shadow: 0 6px 0 #7f0000, 0 0 0 12px rgba(229, 57, 53, 0); }
        100% { box-shadow: 0 6px 0 #7f0000, 0 0 0 0 rgba(229, 57, 53, 0); }
    }

    .stButton > button:hover {
        transform: translateY(2px);
        box-shadow: 0 4px 0 #7f0000, 0 6px 10px rgba(0,0,0,0.3) !important;
        filter: brightness(1.1);
        animation: none; /* Dừng nhịp đập khi hover */
    }

    .stButton > button:active {
        transform: translateY(6px);
        box-shadow: 0 0 0 #7f0000 !important;
    }

    /* Quests & Boss Texts */
    .mission-title {
        font-size: 1.25rem;
        font-weight: 900;
        color: #b71c1c;
        text-align: center;
        line-height: 1.3;
        margin: 0.5rem 0;
        text-transform: uppercase;
    }
    
    .mission-desc {
        min-height: 3.5rem;
        font-size: 1rem;
        font-weight: 700;
        color: #3e2723;
        text-align: center;
    }

    .reward-text {
        font-size: 1.3rem;
        font-weight: 900;
        color: #d68100;
        text-align: center;
        margin-top: 0.8rem;
        background: rgba(255, 215, 0, 0.15);
        border-radius: 8px;
        padding: 8px;
        border: 1px dashed #d4af37;
        box-shadow: inset 0 0 8px rgba(212,175,55,0.2);
    }

    .monster-name {
        font-size: 1.2rem;
        font-weight: 900;
        color: #4a148c; /* Tím quái vật */
        text-align: center;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .monster-quote {
        font-size: 1rem;
        font-weight: 700;
        color: #5c3a21;
        font-style: italic;
        text-align: center;
        min-height: 3rem;
        background: rgba(0,0,0,0.04);
        border-radius: 8px;
        padding: 10px;
        margin-top: 10px;
    }

    /* Metrics Styling */
    div[data-testid="stMetricValue"] {
        color: #d32f2f;
        font-weight: 900;
        font-family: 'Playpen Sans', cursive;
        text-shadow: 1px 1px 1px rgba(0,0,0,0.1);
    }
    
    div[data-testid="stMetricLabel"] {
        font-weight: 900;
        color: #3e2723;
    }

    /* THANH TIẾN TRÌNH DÒNG CHẢY MA THUẬT (Animated Magic Flow) */
    div[data-testid="stProgress"] > div > div > div {
        background: linear-gradient(270deg, #ff4500, #ff8c00, #ffd700, #ff4500);
        background-size: 200% 200%;
        animation: flowMagic 3s ease infinite;
        box-shadow: 0 0 10px rgba(255, 140, 0, 0.7);
        border-radius: 10px;
    }
    
    @keyframes flowMagic {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    div[data-testid="stProgress"] > div {
        background-color: #eaddc7;
        border: 2px solid #b8860b;
        border-radius: 12px;
        height: 1.4rem;
        box-shadow: inset 0 2px 5px rgba(0,0,0,0.2);
    }
    
    /* --- ÉP MÀU TRẮNG CHO CÁC Ô NHẬP LIỆU (Khắc phục lỗi nền đen) --- */
    
    /* Ô tải file (File Uploader) */
    div[data-testid="stFileUploader"] > section {
        background-color: #ffffff !important;
        border: 2px dashed #d4af37 !important;
    }
    div[data-testid="stFileUploader"] > section * {
        color: #3e2723 !important;
    }
    div[data-testid="stFileUploader"] button {
        background-color: #fdf5e6 !important;
        color: #8b0000 !important;
        border: 1px solid #d4af37 !important;
        border-radius: 8px !important;
    }

    /* Ô nhập chữ (Text Input) */
    div[data-baseweb="input"] {
        background-color: #ffffff !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="input"] > div {
        background-color: #ffffff !important;
    }
    div[data-baseweb="input"] input {
        color: #3e2723 !important;
        background-color: #ffffff !important;
        font-weight: 700 !important;
    }
    div[data-baseweb="input"] input::placeholder {
        color: #a08c8c !important;
    }

    /* Nút Submit trong Form (Sửa lại cho đồng bộ với nút RPG Đỏ) */
    div[data-testid="stFormSubmitButton"] > button {
        border-radius: 12px !important;
        border: 2px solid #ffd700 !important;
        min-height: 55px !important;
        font-size: 1.2rem !important;
        font-weight: 900 !important;
        color: #ffffff !important;
        background: linear-gradient(180deg, #e53935, #b71c1c) !important;
        box-shadow: 0 6px 0 #7f0000, 0 10px 15px rgba(0,0,0,0.3) !important;
        transition: all 0.15s ease;
        font-family: 'Playpen Sans', cursive !important;
        text-transform: uppercase;
        animation: pulseButton 2s infinite;
        width: 100%;
    }
    div[data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(2px);
        box-shadow: 0 4px 0 #7f0000, 0 6px 10px rgba(0,0,0,0.3) !important;
        filter: brightness(1.1);
        animation: none;
    }
    div[data-testid="stFormSubmitButton"] > button:active {
        transform: translateY(6px);
        box-shadow: 0 0 0 #7f0000 !important;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# SIDEBAR (THẺ NHÂN VẬT & ĐĂNG NHẬP)
# ============================================================

with st.sidebar:
    st.markdown("### 👑 KHU VỰC CÔ GIÁO")
    if not st.session_state.admin_mode:
        admin_pw = st.text_input("🔐 Mật khẩu quản trị", type="password", key="admin_pw")
        if st.button("📊 MỞ BẢNG QUẢN LÝ", use_container_width=True):
            if admin_pw == ADMIN_PASSWORD:
                st.session_state.admin_mode = True
                st.rerun()
            else:
                st.error("❌ Mật khẩu chưa đúng.")
    else:
        st.success("✅ Đang ở chế độ Cô giáo")
        if st.button("🎮 QUAY LẠI GAME", use_container_width=True):
            st.session_state.admin_mode = False
            st.rerun()

    st.write("---")
    if not st.session_state.game_started:
        st.markdown("## 📜 ĐĂNG KÝ HÀNH TRÌNH")
        name_input = st.text_input("👤 Tên Dũng Sĩ", value=st.session_state.name, placeholder="Ví dụ: Anh Thư")
        lop_input = st.text_input("🏰 Tên Bang Hội (Lớp)", value=st.session_state.lop, placeholder="Ví dụ: 2A6")
        gender_input = st.radio("🧙 Chọn Hệ Phái", ["Nam", "Nữ"], index=0 if st.session_state.gender == "Nam" else 1, horizontal=True)

        if st.button("🚀 BƯỚC VÀO THẾ GIỚI", use_container_width=True):
            if not name_input.strip() or not lop_input.strip():
                st.error("⚠️ Nhà vua cần biết tên và bang hội của con!")
            else:
                player = get_or_create_player(name_input.strip(), lop_input.strip(), gender_input)
                st.session_state.player_id = player["id"]
                st.session_state.name = player["name"]
                st.session_state.lop = player["lop"]
                st.session_state.gender = player["gender"]
                st.session_state.stars = player["stars"]
                todays = load_today_submissions(player["id"])
                st.session_state.completed_tasks = list(dict.fromkeys([r["task_id"] for r in todays]))
                st.session_state.proofs = {
                    r["task_id"]: {
                        "filename": r["original_filename"],
                        "path": r["media_path"],
                        "media_type": r["media_type"],
                        "parent_note": r["parent_note"],
                        "submitted_at": r["submitted_at"],
                    } for r in todays
                }
                st.session_state.game_started = True
                st.session_state.login_effect = True
                st.rerun()
    else:
        st.markdown("## 🛡️ HỒ SƠ DŨNG SĨ")
        
        avatar_stem = "dungsi_nam" if st.session_state.gender == "Nam" else "dungsi_nu"
        if not show_media(avatar_stem, size_key="character"):
             st.markdown("## 🧙")
        
        st.markdown(f"### {st.session_state.name.upper()}")
        st.markdown(f"**Bang hội:** {st.session_state.lop}")
        
        # Hệ thống Cấp độ (EXP)
        current_exp = st.session_state.stars
        level = (current_exp // 100) + 1 
        exp_to_next = 100 - (current_exp % 100)
        progress_pct = (current_exp % 100) / 100
        
        st.markdown(f"### 🎖️ CẤP ĐỘ {level}")
        st.progress(progress_pct, text=f"EXP: {current_exp} (Cần {exp_to_next} EXP để lên cấp)")
        
        st.write("---")
        st.markdown("### 🏆 TÚI HUY HIỆU")
        
        # Danh sách huy hiệu chi tiết
        badges = [
            {"exp": 100, "icon": "🥉", "name": "Tân Binh"},
            {"exp": 300, "icon": "🥈", "name": "Tinh Anh"},
            {"exp": 500, "icon": "🥇", "name": "Kỵ Sĩ"},
            {"exp": 1000, "icon": "💎", "name": "Anh Hùng"},
            {"exp": 1500, "icon": "👑", "name": "Huyền Thoại"}
        ]
        
        badge_count = sum(1 for b in badges if st.session_state.stars >= b["exp"])
        st.write(f"Đã thu thập: **{badge_count}/5** huy hiệu")
        
        # Hiển thị huy hiệu dạng danh sách dọc (Chú thích bên phải)
        for b in badges:
            if st.session_state.stars >= b["exp"]:
                # Đã mở khóa
                st.markdown(
                    f"<div style='display: flex; align-items: center; background: rgba(255, 215, 0, 0.2); padding: 8px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #d4af37; box-shadow: inset 0 0 5px rgba(255,215,0,0.5);'>"
                    f"<div style='font-size: 2rem; margin-right: 15px; filter: drop-shadow(0 0 8px #d4af37);'>{b['icon']}</div>"
                    f"<div><strong style='color: #b71c1c; font-size: 1.1rem;'>{b['name']}</strong><br/>"
                    f"<span style='color: #d68100; font-weight: bold;'>✨ Đã mở khóa!</span></div>"
                    f"</div>", 
                    unsafe_allow_html=True
                )
            else:
                # Chưa mở khóa (Hiện icon nhưng mờ nhẹ, có chú thích cần bao nhiêu EXP bên phải)
                st.markdown(
                    f"<div style='display: flex; align-items: center; background: rgba(0, 0, 0, 0.03); padding: 8px; border-radius: 8px; margin-bottom: 8px; border: 1px dashed #a08c8c;'>"
                    f"<div style='font-size: 2rem; margin-right: 15px; opacity: 0.5;'>{b['icon']}</div>"
                    f"<div><strong style='color: #5c3a21; font-size: 1.1rem;'>{b['name']}</strong><br/>"
                    f"<span style='color: #8b0000; font-size: 0.9rem;'>🔒 Cần {b['exp']} EXP</span></div>"
                    f"</div>", 
                    unsafe_allow_html=True
                )

        
        if st.button("🚪 Thoát Hành Trình"):
            st.session_state.game_started = False
            st.rerun()


# ============================================================
# HEADER CHÍNH
# ============================================================

st.markdown('<div class="game-title">DŨNG SĨ TỎA SÁNG</div>', unsafe_allow_html=True)
st.markdown('<div class="game-subtitle">"Vận động cơ thể - Trừ yêu diệt bạo - Cứu lấy vương quốc!"</div>', unsafe_allow_html=True)

if st.session_state.get("login_effect", False) and st.session_state.game_started:
    st.balloons()
    st.session_state.login_effect = False

# ============================================================
# BẢNG QUẢN LÝ CÔ GIÁO / NHÀ VUA
# ============================================================

if st.session_state.admin_mode:
    st.markdown('<div class="section-label">👑 BẢNG ĐIỀU KHIỂN CÔ GIÁO</div>', unsafe_allow_html=True)
    players = load_all_players()
    submissions = load_all_submissions()

    total_players = len(players)
    total_submissions = len(submissions)
    total_classes = len({p["lop"] for p in players})
    total_exp = sum(p["stars"] for p in players)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👧👦 Dũng sĩ tham gia", total_players)
    m2.metric("🏫 Số lớp", total_classes)
    m3.metric("📸🎥 Lượt nộp minh chứng", total_submissions)
    m4.metric("⭐ Tổng EXP", total_exp)

    st.markdown("### 📋 DANH SÁCH DŨNG SĨ")
    class_options = ["Tất cả"] + sorted({p["lop"] for p in players})
    selected_class = st.selectbox("🏰 Lọc theo lớp", class_options)
    filtered_players = [p for p in players if selected_class == "Tất cả" or p["lop"] == selected_class]

    if filtered_players:
        import pandas as pd
        player_rows = []
        for p in filtered_players:
            level = (p["stars"] // 100) + 1
            count = sum(1 for s in submissions if s["player_id"] == p["id"])
            player_rows.append({
                "Tên Dũng sĩ": p["name"],
                "Lớp": p["lop"],
                "Giới tính": p["gender"],
                "EXP": p["stars"],
                "Cấp": level,
                "Đã nộp": count,
                "Lần hoạt động cuối": p["last_seen"],
            })
        st.dataframe(player_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có Dũng sĩ nào tham gia.")

    st.markdown("### 📷🎥 NHẬT KÝ MINH CHỨNG")
    filtered_submissions = load_all_submissions(class_name=selected_class)
    if filtered_submissions:
        for sub in filtered_submissions:
            with st.container(border=True):
                c1, c2 = st.columns([1.1, 1.9])
                with c1:
                    st.markdown(f"### 👤 {sub['name']}")
                    st.write(f"**🏰 Lớp:** {sub['lop']}")
                    st.write(f"**🎯 Nhiệm vụ:** {sub['task_title']}")
                    st.write(f"**🕒 Thời gian:** {sub['submitted_at']}")
                    st.write(f"**⭐ Thưởng:** +{sub['reward']} EXP")
                    st.info(f"📜 Xác nhận Bố/Mẹ: {sub['parent_note']}")
                    st.caption(f"📎 Tệp: {sub['original_filename']}")
                with c2:
                    media_path = Path(sub["media_path"])
                    if media_path.exists():
                        if sub["media_type"] == "video":
                            st.video(str(media_path))
                        else:
                            st.image(str(media_path), use_container_width=True)
                        try:
                            data = media_path.read_bytes()
                            st.download_button(
                                "⬇️ Tải minh chứng",
                                data=data,
                                file_name=sub["original_filename"],
                                key=f"download_{sub['id']}",
                                use_container_width=True,
                            )
                        except OSError:
                            st.warning("Không đọc được tệp minh chứng.")
                    else:
                        st.error("⚠️ Tệp đã không còn trong kho lưu trữ.")
    else:
        st.info("Chưa có ảnh/video minh chứng nào theo bộ lọc hiện tại.")

    st.markdown("### 📊 THỐNG KÊ THEO LỚP")
    if players:
        import pandas as pd
        class_stats = []
        for cls in sorted({p["lop"] for p in players}):
            cls_players = [p for p in players if p["lop"] == cls]
            cls_subs = [s for s in submissions if s["lop"] == cls]
            class_stats.append({
                "Lớp": cls,
                "Số bé": len(cls_players),
                "Tổng EXP": sum(p["stars"] for p in cls_players),
                "Lượt nộp": len(cls_subs),
            })
        st.dataframe(class_stats, use_container_width=True, hide_index=True)

    st.success("💡 Dữ liệu được lưu trong cơ sở dữ liệu và kho tệp của ứng dụng.")
    st.stop()

# ============================================================
# MÀN HÌNH CHƯA BẮT ĐẦU
# ============================================================

if not st.session_state.game_started:
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="section-label">📜 CHỈ DỤNG TỪ NHÀ VUA</div>', unsafe_allow_html=True)
            st.write("**Vương quốc đang bị đe dọa bởi binh đoàn Thói Quen Xấu!**")
            st.write("Ta cần sự giúp đỡ của các Dũng sĩ trẻ tuổi. Nhiệm vụ của các con là:")
            st.write("⚔️ Rèn luyện sức khỏe mỗi ngày thông qua Cáo Thị.")
            st.write("✨ Thu thập Điểm Kinh Nghiệm (EXP) để thăng cấp.")
            st.write("👹 Tiêu diệt Lười Biếng, Háu Ăn và Nghiện Game.")
            st.write("👑 Đạt 1.500 EXP để khiêu chiến Đại Ma Vương!")

    with right:
        if not show_media("welcome", size_key="effect"):
            with st.container(border=True):
                st.markdown("### 🗺️ BẢN ĐỒ THẾ GIỚI")
                st.write("Hãy ghi danh ở bảng bên trái để nhà vua cấp phát vũ khí.")

    st.info("👈 Ghi danh ở thanh Cáo Thị bên trái để bắt đầu cuộc phiêu lưu.")
    st.stop()


# ============================================================
# BẢN ĐỒ HÀNH TRÌNH
# ============================================================

st.markdown('<div class="section-label">🗺️ BẢN ĐỒ KHÁM PHÁ</div>', unsafe_allow_html=True)

with st.container(border=True):
    boss_unlocked = st.session_state.stars >= 1500
    route = [
        ("🏁", "THÀNH CHÍNH", True, "Nơi bắt đầu"),
        ("🌲", "RỪNG RÈN LUYỆN", "the_duc" in st.session_state.completed_tasks, "Bài tập Tiên Tộc"),
        ("⚡", "THẢO NGUYÊN", "chay_bo" in st.session_state.completed_tasks, "Đuổi bắt Gió"),
        ("🌿", "LÀNG THẢO MỘC", "an_rau" in st.session_state.completed_tasks, "Thần Dược Xanh"),
        ("👑", "HANG Ổ BOSS", boss_unlocked, "Cần 1.500 EXP"),
    ]

    route_cols = st.columns(len(route), gap="small")
    for i, (icon, title, unlocked, desc) in enumerate(route):
        with route_cols[i]:
            with st.container(border=True):
                st.markdown(f"<div style='text-align:center;font-size:2.5rem'>{icon}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center;font-weight:900;'>{title}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center;font-size:0.85rem;color:#5c3a21;font-weight:bold;'>{desc}</div>", unsafe_allow_html=True)
                if unlocked:
                    st.success("MỞ KHÓA")
                else:
                    st.info("BỊ PHONG ẤN")


# ============================================================
# HIỆU ỨNG NHẬN THƯỞNG & ĐÁNH QUÁI
# ============================================================

if st.session_state.show_reward_fx:
    with st.container(border=True):
        st.markdown("## ✨ THU THẬP KINH NGHIỆM! ✨")
        if not show_media("reward", size_key="effect"):
            st.success("⭐ Nhận được +10 EXP! Cấp độ đang tăng lên!")
        st.session_state.show_reward_fx = False

if st.session_state.show_attack_fx:
    with st.container(border=True):
        st.markdown("## ⚔️ DŨNG SĨ XUẤT CHIÊU!")
        if not show_media("attack", size_key="effect"):
            st.info("⚔️ Đòn đánh bạo kích! Sức khỏe dũng sĩ dồi dào!")
        st.session_state.show_attack_fx = False


# ============================================================
# BẢNG CÁO THỊ (NHIỆM VỤ)
# ============================================================

st.markdown('<div class="section-label">📜 BẢNG CÁO THỊ TỪ NHÀ VUA</div>', unsafe_allow_html=True)
st.caption("📅 Hoàn thành các uỷ thác dưới đây mỗi ngày để nhận EXP và tiêu diệt quái vật.")

task_cols = st.columns(3, gap="large")

for col, task in zip(task_cols, TASKS):
    with col:
        with st.container(border=True):
            st.markdown(f"### {task['station']} {task['icon']}")
            st.markdown(f'<div class="mission-title">{task["title"]}</div>', unsafe_allow_html=True)

            if show_media(task["asset"], size_key="mission"):
                st.write("")

            st.markdown(f'<div class="mission-desc">{task["description"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="reward-text">Phần thưởng: ⭐ +{task["reward"]} EXP</div>', unsafe_allow_html=True)

            done = task["id"] in st.session_state.completed_tasks

            if done:
                st.success("✅ ĐÃ GIAO BẢN HỢP ĐỒNG")
                proof = st.session_state.proofs.get(task["id"])
                if proof:
                    proof_path = Path(proof.get("path", ""))
                    if proof.get("media_type") == "video" and proof_path.exists():
                        st.video(str(proof_path))
                    elif proof_path.exists():
                        st.image(str(proof_path), width=280)
                    elif proof.get("data"):
                        st.image(proof["data"], width=280)
                    if proof.get("parent_note"):
                        st.info(f"📜 Ấn tín của gia đình: {proof['parent_note']}")
                    if proof.get("submitted_at"):
                        st.caption(f"🕒 Đã nộp: {proof['submitted_at']}")
            else:
                with st.form(key=f"proof_form_{task['id']}"):
                    proof_file = st.file_uploader(
                        "📷🎥 Nhật ký thám hiểm (Ảnh hoặc Video minh chứng)",
                        type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm"],
                        key=f"proof_file_{task['id']}",
                        help="Có thể gửi ảnh hoặc video. Ảnh tối đa 5MB; video tối đa 50MB.",
                    )
                    parent_note = st.text_input(
                        "📜 Chữ ký/Xác nhận của Hội Trưởng (Bố/Mẹ)",
                        placeholder="VD: Con đã hoàn thành xuất sắc!",
                        key=f"parent_note_{task['id']}",
                    )
                    submit_task = st.form_submit_button("✅ NỘP NHIỆM VỤ (+10 EXP)", use_container_width=True)

                if submit_task:
                    if proof_file is None:
                        st.error("⚠️ Nhà vua cần thấy bằng chứng (Ảnh hoặc Video)!")
                    else:
                        suffix = Path(proof_file.name).suffix.lower()
                        max_size = 50 * 1024 * 1024 if suffix in VIDEO_EXTS else 5 * 1024 * 1024
                        max_text = "50MB" if suffix in VIDEO_EXTS else "5MB"
                        if proof_file.size > max_size:
                            st.error(f"⚠️ Tệp quá nặng, tối đa {max_text}.")
                        elif not parent_note.strip():
                            st.error("⚠️ Cần có dấu ấn xác nhận của Hội Trưởng (Bố/Mẹ).")
                        elif not st.session_state.player_id:
                            st.error("⚠️ Chưa xác định được hồ sơ Dũng sĩ. Hãy vào game lại.")
                        else:
                            saved = save_submission(st.session_state.player_id, task, proof_file, parent_note)
                            st.session_state.stars += task["reward"]
                            st.session_state.completed_tasks.append(task["id"])
                            st.session_state.proofs[task["id"]] = saved
                            st.session_state.show_reward_fx = True
                            st.session_state.show_attack_fx = True
                            st.rerun()


# ============================================================
# QUÁI VẬT & BOSS
# ============================================================

st.markdown('<div class="section-label">👹 BINH ĐOÀN YÊU QUÁI</div>', unsafe_allow_html=True)

monster_cols = st.columns(3, gap="large")
for col, monster in zip(monster_cols, MONSTERS):
    damage = max(0, st.session_state.stars - monster["start"])
    hp = max(0, 50 - min(damage, 50))

    with col:
        with st.container(border=True):
            st.markdown(f'<div class="monster-name">{monster["icon"]} {monster["name"]}</div>', unsafe_allow_html=True)
            if show_media(monster["asset"], size_key="monster"):
                st.write("")
            st.markdown(f'<div class="monster-quote">“{monster["quote"]}”</div>', unsafe_allow_html=True)
            st.progress(hp / 50 if hp else 0, text=f"Sinh lực (HP): {hp}/50")
            
            if hp == 0:
                st.success("💥 ĐÃ BỊ THANH TẨY!")
            else:
                st.warning("⚔️ Đang giao tranh...")


st.markdown('<div class="section-label">👑 HANG Ổ ĐẠI MA VƯƠNG</div>', unsafe_allow_html=True)

with st.container(border=True):
    if not st.session_state.boss_defeated:
        st.markdown('<h2 style="text-align:center; color:#b71c1c; text-shadow: 1px 1px 2px rgba(0,0,0,0.1);">👹 MA VƯƠNG LƯỜI BIẾNG TỐI CAO 👹</h2>', unsafe_allow_html=True)
        if show_media("boss", size_key="boss"):
            st.write("")
        
        BOSS_MAX_HP = 1500
        boss_hp = BOSS_MAX_HP

        # EXP là điều kiện nạp đủ ma lực; không trừ trực tiếp vào HP Boss.
        boss_progress = min(st.session_state.stars / BOSS_MAX_HP, 1.0)

        st.progress(
            boss_progress,
            text=f"Ma lực tích tụ: {st.session_state.stars}/1500 EXP"
        )
        st.write(
            f"<div style='text-align:center;font-size:1.4rem;font-weight:900;color:#d32f2f;'>"
            f"❤️ HP BOSS: {boss_hp}/{BOSS_MAX_HP}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "⚔️ Boss có 1.500 máu. Khi Dũng sĩ tích đủ 1.500 EXP, "
            "tuyệt chiêu cuối sẽ sẵn sàng để tiêu diệt Boss."
        )

        if st.session_state.stars >= 1500:
            st.success("🎯 ĐÃ ĐỦ 1.500 EXP! THANH GƯƠM ÁNH SÁNG ĐÃ SẴN SÀNG!")
            if st.button("⚔️ THIỂN TRIỂN TUYỆT CHIÊU CUỐI CÙNG!", use_container_width=True):
                st.session_state.boss_defeated = True
                st.session_state.show_victory = True
                st.rerun()
        else:
            st.info(f"💡 Cần thêm {1500 - st.session_state.stars} EXP để phá vỡ kết giới của Boss.")

    else:
        st.markdown('<h1 style="text-align:center; color:#d4af37; font-size:3rem; text-shadow: 1px 1px 3px rgba(0,0,0,0.2);">👑 VƯƠNG QUỐC ĐÃ ĐƯỢC CỨU! 👑</h1>', unsafe_allow_html=True)
        if not show_media("boss_defeated", size_key="boss"):
            st.markdown("## 💥 MA VƯƠNG ĐÃ TAN BIẾN! 💥")
        st.write("<h3 style='text-align:center; color:#8b0000;'>🏆 NGÀI LÀ VỊ CỨU TINH CỦA CHÚNG TA!</h3>", unsafe_allow_html=True)
        
        if st.session_state.show_victory:
            st.balloons()
            st.session_state.show_victory = False


# ============================================================
# CHÂN TRANG
# ============================================================
st.write("---")
st.markdown("<p style='text-align:center; font-weight:900; color:#d4af37; font-size:1.2rem; text-shadow: 1px 1px 1px rgba(0,0,0,0.2);'>✨ DŨNG SĨ TỎA SÁNG ✨</p>", unsafe_allow_html=True)
