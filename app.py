# app.py
import os
import io
import base64
import logging
import html
from typing import Optional, List

import streamlit as st
from PIL import Image, UnidentifiedImageError

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Streamlit page config (must be first Streamlit call)
# =============================================================================
st.set_page_config(
    page_title="Karma's Kitchen - Nepali Restaurant",
    page_icon="🍛",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# Image helpers (robust + cached)
# =============================================================================
IMAGE_DIR_CANDIDATES = [
    ".",  # as given
    "images",
    os.path.join(os.getcwd(), "images"),
    os.path.dirname(os.path.abspath(__file__)),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "images"),
]
IMAGE_EXT_CANDIDATES = [".jpg", ".jpeg", ".png", ".webp", ".gif"]

# Turn this ON only when debugging broken image files (slower).
STRICT_IMAGES = False


def _split_basename_ext(path: str):
    base = os.path.basename(path)
    root, ext = os.path.splitext(base)
    subdir = os.path.dirname(path)
    return subdir, root, ext.lower()


def _generate_candidate_paths(image_path: str) -> List[str]:
    """
    Given 'images/momo/chicken_steam_momo.jpg', try multiple base directories
    and alternate file extensions to find a usable file.
    """
    subdir, root, orig_ext = _split_basename_ext(image_path)

    # Also try without the leading 'images/' piece
    rel_no_prefix = os.path.join(
        subdir.replace("images" + os.sep, "").replace("images/", ""),
        root + orig_ext,
    ).lstrip("/\\")
    rel_subdir_only = os.path.join(subdir, root + orig_ext).lstrip("/\\")

    candidates = [image_path]

    # Relative variants under candidate bases
    for base in IMAGE_DIR_CANDIDATES:
        candidates.append(os.path.join(base, rel_no_prefix))
        candidates.append(os.path.join(base, rel_subdir_only))

    # Try alternate extensions across directories
    for base in IMAGE_DIR_CANDIDATES:
        for ext in ([orig_ext] + [e for e in IMAGE_EXT_CANDIDATES if e != orig_ext]):
            if subdir:
                candidates.append(os.path.join(base, subdir, root + ext))
            candidates.append(os.path.join(base, root + ext))

    # De-duplicate while preserving order
    seen = set()
    final = []
    for c in candidates:
        c_norm = os.path.normpath(c)
        if c_norm not in seen:
            seen.add(c_norm)
            final.append(c_norm)
    return final


@st.cache_data(show_spinner=False)
def resolve_image_path_cached(image_key: str) -> Optional[str]:
    """
    Cache the expensive multi-path probing so we only do it once per key.
    """
    for candidate in _generate_candidate_paths(image_key):
        if os.path.exists(candidate) and os.path.isfile(candidate):
            logger.info(f"Found image at: {candidate}")
            return candidate
    logger.warning(f"Image not found for: {image_key}")
    return None


@st.cache_data(show_spinner=False)
def _stat_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


@st.cache_data(show_spinner=False)
def load_thumbnail_b64(path: str, mtime: float, target_px: int = 400) -> str:
    """
    Open once, make a ~400px wide thumbnail, return base64 JPEG (fast & small).
    Cache key includes (path, mtime, target_px).
    """
    # Read file once
    with open(path, "rb") as f:
        raw = f.read()

    if STRICT_IMAGES:
        # Deep verification path for debugging bad files (slower)
        bio = io.BytesIO(raw)
        with Image.open(bio) as im:
            im.verify()  # validate header
        bio2 = io.BytesIO(raw)
        with Image.open(bio2) as im2:
            img = im2.convert("RGB")
    else:
        img = Image.open(io.BytesIO(raw)).convert("RGB")

    # Resize to target width while preserving aspect
    w, h = img.size
    if w > target_px:
        new_h = int(h * (target_px / float(w)))
        img = img.resize((target_px, new_h), Image.LANCZOS)

    # JPEG (smaller than PNG for photos)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    b64 = base64.b64encode(out.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def render_responsive_image_fast(image_key: str, alt: str = ""):
    """
    Resolve the image (cached), load/resize/encode once (cached),
    and inject with fixed responsive CSS widths.
    """
    path = resolve_image_path_cached(image_key)
    safe_alt = html.escape(alt or "")
    if not path:
        st.markdown(
            f"<div class='warning-message'>🖼️ Image not found for <strong>{safe_alt}</strong>.</div>",
            unsafe_allow_html=True,
        )
        return
    try:
        mtime = _stat_mtime(path)
        data_uri = load_thumbnail_b64(path, mtime=mtime, target_px=400)
        st.markdown(
            f"""
            <div class="responsive-image">
                <img src="{data_uri}" alt="{safe_alt}" loading="lazy" />
            </div>
            """,
            unsafe_allow_html=True,
        )
    except UnidentifiedImageError:
        st.markdown(
            f"<div class='warning-message'>🖼️ Couldn't decode the file for <strong>{safe_alt}</strong> (invalid image format).</div>",
            unsafe_allow_html=True,
        )
    except Exception as e:
        logger.error(f"Image decode error for {safe_alt} @ {path}: {e}")
        st.markdown(
            f"<div class='warning-message'>🖼️ Error loading image for <strong>{safe_alt}</strong>.</div>",
            unsafe_allow_html=True,
        )

# =============================================================================
# Data import (menu)
# =============================================================================
try:
    from menu_data import menu, taste_options, meal_options, dietary_options
    logger.info("Successfully imported menu data")
except Exception as e:
    logger.error(f"Failed to import menu_data: {e}")
    # Fallback minimal menu so app still runs
    menu = {
        "momo": [
            {"name": "Chicken Steam Momo", "price": "$14.99",
             "image": "images/momo/chicken_steam_momo.jpg",
             "taste": ["savory", "soft", "traditional"]},
            {"name": "Veg Tikka Momo", "price": "$13.99",
             "image": "images/momo/veg_tikka_momo.jpg",
             "taste": ["savory", "spiced", "herby"]},
        ],
        "veg_appetizers": [
            {"name": "Vegetable Pakora", "price": "$10.99",
             "image": "images/veg_appetizers/veg_pakora.jpg",
             "taste": ["savory", "crispy", "fried"]},
        ],
        "non_veg_appetizers": [
            {"name": "Dry Chicken Lollipop (5pcs)", "price": "$15.99",
             "image": "images/non_veg_appetizers/dry_chicken_lollipop.jpg",
             "taste": ["spicy", "crispy", "juicy"]},
        ],
        "veg_entrees": [
            {"name": "Paneer Butter Masala", "price": "$14.49",
             "image": "images/veg_entrees/paneer_butter_masala.jpg",
             "taste": ["savory", "creamy", "mild"]},
        ],
        "non_veg_entrees": [
            {"name": "Butter Chicken", "price": "$15.99",
             "image": "images/non_veg_entrees/butter_chicken.jpg",
             "taste": ["savory", "creamy", "mild"]},
        ],
        "biryani": [
            {"name": "Chicken Biryani", "price": "$14.99",
             "image": "images/biryani/chicken_biryani.jpg",
             "taste": ["savory", "aromatic", "spiced"]},
        ],
        "desserts": [
            {"name": "Gajar Halwa Fusion", "price": "$9.99",
             "image": "images/desserts/gajar_halwa.jpg",
             "taste": ["sweet", "warm", "nutty"]},
        ],
    }
    taste_options = [
        "spicy", "sweet", "savory", "creamy", "soft", "crispy",
        "fried", "traditional", "herby", "aromatic", "mild", "spiced",
        "no preference",
    ]
    meal_options = ["Breakfast", "Lunch", "Dinner", "Snacks"]
    dietary_options = ["Vegetarian", "Non-Vegetarian"]
    st.warning("Using fallback data. Please check your menu_data.py file.", icon="⚠️")

# =============================================================================
# Styling (responsive, fixed image sizes by device)
# =============================================================================
st.markdown("""
<style>
    .chat-container {
        display: flex;
        flex-direction: column;
        max-width: 100%;
        margin: 0 auto;
    }
    .chat-message {
        padding: 12px;
        border-radius: 12px;
        margin-bottom: 12px;
        display: flex;
        align-items: flex-start;
        color: black;
        font-size: 14px;
        word-wrap: break-word;
    }
    .chat-message.user {
        background-color: #f0f2f6;
        margin-left: 10%;
        gap: 8px;
    }
    .chat-message.bot {
        background-color: #e6f7ff;
        margin-right: 10%;
    }
    .chat-avatar {
        width: 35px;
        height: 35px;
        border-radius: 50%;
        margin-right: 8px;
        flex-shrink: 0;
        font-size: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
    }

    .recommendation-card {
        border: 1px solid #ddd;
        border-radius: 12px;
        padding: 14px;
        margin: 14px 0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    }
    .rec-title {
        font-size: 18px !important;
        line-height: 1.3;
        margin: 0 0 10px 0;
        color: #d35400;
        font-weight: 700;
        text-align: center;
    }
    .price-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .price-tag {
        font-weight: 600;
        color: #27ae60;
        background-color: #e8f5e8;
        padding: 4px 12px;
        border-radius: 15px;
        font-size: 16px;
    }
    .taste-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 8px;
    }
    .taste-tag {
        background-color: #f39c12;
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        display: inline-block;
    }
    .stButton button {
        width: 100%;
        font-size: 14px;
        padding: 12px;
        border-radius: 8px;
        margin: 5px 0;
    }

    /* Fixed-size responsive images */
    .responsive-image {
        text-align: center;
        margin: 8px 0 18px 0;
    }
    .responsive-image img {
        border-radius: 10px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.15);
        border: 2px solid #f0f0f0;
        display: block;
        margin-left: auto;
        margin-right: auto;
        width: 400px;
        height: auto;
        object-fit: cover;
    }
    .responsive-image .img-caption {
        font-size: 12px;
        color: #666;
        margin-top: 6px;
    }
    
    hr {
        margin: 18px 0;
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent 0%, #e0e0e0 50%, transparent 100%);
    }
    
    /* Tablet (iPad) */
    @media (max-width: 1024px) {
        .responsive-image img { width: 320px; }
    }
    
    /* Mobile responsive adjustments */
    @media (max-width: 768px) {
        .chat-message {
            padding: 8px;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .chat-message.user {
            margin-left: 3%;
        }
        .chat-message.bot {
            margin-right: 3%;
        }
        .chat-avatar {
            width: 28px;
            height: 28px;
            font-size: 9px;
            margin-right: 6px;
        }
        .recommendation-card {
            padding: 12px;
            margin: 10px 0;
            border-radius: 10px;
        }
        .rec-title {
            font-size: 16px !important;
            margin: 0 0 8px 0;
        }
        .price-tag {
            font-size: 14px;
            padding: 3px 10px;
        }
        .taste-tag {
            font-size: 0.75rem;
            padding: 3px 8px;
        }
        .stButton button {
            font-size: 12px;
            padding: 10px;
            margin: 4px 0;
        }
        .responsive-image {
        text-align: center;
        }
        .responsive-image img {
            width: 220px;
            margin: 6px auto 12px auto;
            display: block;
        }
        .responsive-image .img-caption {
            font-size: 11px;
            margin-top: 4px;
        }
    }
    
    /* Extra small devices (phones in portrait) */
    @media (max-width: 480px) {
        .recommendation-card {
            padding: 10px;
        }
        .rec-title {
            font-size: 15px !important;
        }
        .price-tag {
            font-size: 13px;
            padding: 2px 8px;
        }
        .taste-tag {
            font-size: 0.7rem;
            padding: 2px 6px;
        }
        .responsive-image img {
            width: 200px;
        }
    }

    .error-message {
        background-color: #ffe6e6;
        color: #d63031;
        padding: 10px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 4px solid #d63031;
    }
    .warning-message {
        background-color: #fff3cd;
        color: #856404;
        padding: 10px;
        border-radius: 8px; /* FIXED: was borderRadius */
        margin: 10px 0;
        border-left: 4px solid #ffc107;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Session state
# =============================================================================
if 'step' not in st.session_state:
    st.session_state.step = 0
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'meal_type' not in st.session_state:
    st.session_state.meal_type = ""
if 'dietary_pref' not in st.session_state:
    st.session_state.dietary_pref = ""
if 'selected_tastes' not in st.session_state:
    st.session_state.selected_tastes = []
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'last_message' not in st.session_state:
    st.session_state.last_message = ""
if 'welcome_shown' not in st.session_state:
    st.session_state.welcome_shown = False


def add_message(sender, message, is_html=False):
    # Escape user/bot content unless explicitly HTML
    if message != st.session_state.last_message:
        safe = message if is_html else html.escape(str(message))
        st.session_state.chat_history.append({
            "sender": sender,
            "message": safe,
            "is_html": True,  # stored as HTML-safe
        })
        st.session_state.last_message = safe


def display_chat():
    chat_container = st.container()
    with chat_container:
        for chat in st.session_state.chat_history:
            if chat["sender"] == "user":
                st.markdown(f"""
                <div class="chat-message user">
                    <div style="flex-grow: 1; text-align: right;">
                        {chat["message"]}
                    </div>
                    <div class="chat-avatar" style="background-color: #007bff; color: white;">
                        You
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message bot">
                    <div class="chat-avatar" style="background-color: #28a745; color: white;">
                        Bot
                    </div>
                    <div style="flex-grow: 1;">
                        {chat["message"]}
                    </div>
                </div>
                """, unsafe_allow_html=True)

# =============================================================================
# Recommendation logic
# =============================================================================
def recommend_dishes():
    """
    Recommend ALL dishes that match user selections.
    - If meal type is Snacks -> appetizers/momo (+desserts excluded)
    - Else -> entrees/biryani/momo + desserts
    - If user selected tastes -> include dish if ANY taste matches (or "no preference")
    - Return ALL matches (not just 3)
    """
    try:
        recs = []

        # Map meal type -> sections
        mt = st.session_state.meal_type.lower()
        dp = st.session_state.dietary_pref.lower()

        if mt == "snacks":
            sections = (["veg_appetizers", "momo"]
                        if dp == "vegetarian"
                        else ["veg_appetizers", "non_veg_appetizers", "momo"])
        elif mt == "breakfast":
            sections = (["veg_appetizers", "momo"]
                        if dp == "vegetarian"
                        else ["veg_appetizers", "non_veg_appetizers", "momo"])
        else:  # lunch/dinner
            sections = (["veg_entrees", "biryani", "momo"]
                        if dp == "vegetarian"
                        else ["veg_entrees", "non_veg_entrees", "biryani", "momo"])

        if mt != "snacks":
            sections.append("desserts")

        selected = [t.lower() for t in st.session_state.selected_tastes]
        for section in sections:
            if section in menu:
                for dish in menu[section]:
                    dish_tastes = [t.lower() for t in dish.get("taste", [])]
                    if (
                        not selected or
                        "no preference" in selected or
                        any(t in dish_tastes for t in selected)
                    ):
                        recs.append(dish)

        # If nothing matched, fall back to first few of each section
        if not recs:
            for sec in sections:
                if sec in menu and menu[sec]:
                    recs.extend(menu[sec])

        # Deduplicate by name while preserving order
        seen = set()
        uniq = []
        for d in recs:
            nm = d.get("name", "")
            if nm and nm not in seen:
                uniq.append(d)
                seen.add(nm)

        return uniq  # ALL items
    except Exception as e:
        logger.error(f"Error in recommend_dishes: {e}")
        return menu.get("momo", [])


def _render_taste_tags(tastes: List[str]) -> str:
    return "".join([f"<span class='taste-tag'>{html.escape(t)}</span>" for t in tastes or []])


def _show_dish_card(dish: dict):
    """
    Always show: name + price + tastes; then show image using cached pipeline.
    """
    # Create taste tags HTML
    taste_tags_html = _render_taste_tags(dish.get('taste', []))
    name = html.escape(dish.get('name', 'Dish'))
    price = html.escape(dish.get('price', ''))

    st.markdown(
        f"""
        <div class="recommendation-card">
            <div class="rec-title">{name}</div>
            <div class="price-row">
                <div class="taste-container">
                    {taste_tags_html}
                </div>
                <div class="price-tag">{price}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    image_key = dish.get("image", "")
    if image_key:
        render_responsive_image_fast(image_key, alt=dish.get('name', ''))
    else:
        st.markdown(
            "<div class='warning-message'>🖼️ No image path specified for this item.</div>",
            unsafe_allow_html=True,
        )

# =============================================================================
# Recommendations UI
# =============================================================================
def display_recommendations():
    try:
        add_message("bot", "Based on your preferences, here are your recommendations:")
        recs = st.session_state.recommendations

        # If more than 3 are found, we still display ALL (as requested)
        for i, dish in enumerate(recs):
            _show_dish_card(dish)
            if i < len(recs) - 1:
                st.markdown("---")

        add_message("bot", "Would you like to start over?")
        if st.button("Start New Conversation", key="restart_btn"):
            keep = {'welcome_shown'}
            for key in list(st.session_state.keys()):
                if key not in keep:
                    del st.session_state[key]
            st.session_state.step = 0
            st.session_state.chat_history = []
            st.session_state.welcome_shown = True
            st.rerun()

    except Exception as e:
        logger.error(f"Error in display_recommendations: {e}")
        st.markdown(
            """
            <div class='error-message'>
                ❌ Sorry, there was an error displaying recommendations. Please try again.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Start Over", key="error_restart"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.step = 0
            st.session_state.chat_history = []
            st.session_state.welcome_shown = True
            st.rerun()

# =============================================================================
# Main UI flow
# =============================================================================
def main():
    try:
        # Header
        st.markdown('<h1 style="text-align: center; color: #d35400;">Karma & Kocktail\'s Chatbot</h1>', unsafe_allow_html=True)
        st.markdown("### Authentic Nepali Cuisine")

        # First welcome
        if not st.session_state.welcome_shown and not st.session_state.chat_history:
            add_message("bot", "Welcome to Karma & Kocktails! May I know your name?")
            st.session_state.welcome_shown = True
            st.rerun()

        # Chat history
        display_chat()

        # Steps
        if st.session_state.step == 0:
            name = st.text_input("Your name:", key="name_input", label_visibility="collapsed",
                                 placeholder="Type your name here…")
            if name and st.button("Submit", key="name_submit"):
                st.session_state.user_name = name
                st.session_state.step = 1
                add_message("user", name)
                st.rerun()

        elif st.session_state.step == 1:
            prompt = f"Hello {html.escape(st.session_state.user_name)}! What type of meal are you looking for?"
            if not any(chat["message"] == prompt for chat in st.session_state.chat_history):
                add_message("bot", prompt)

            cols = st.columns(2)
            for meal, col in [("Breakfast", cols[0]), ("Lunch", cols[1]),
                              ("Dinner", cols[0]), ("Snacks", cols[1])]:
                with col:
                    if st.button(meal, key=f"meal_{meal}"):
                        st.session_state.meal_type = meal
                        st.session_state.step = 2
                        add_message("user", meal)
                        st.rerun()

        elif st.session_state.step == 2:
            prompt = f"Great choice! {html.escape(st.session_state.meal_type)} it is. Do you prefer vegetarian or non-vegetarian food?"
            if not any(chat["message"] == prompt for chat in st.session_state.chat_history):
                add_message("bot", prompt)

            cols = st.columns(2)
            with cols[0]:
                if st.button("Vegetarian", key="veg_btn"):
                    st.session_state.dietary_pref = "Vegetarian"
                    st.session_state.step = 3
                    add_message("user", "Vegetarian")
                    st.rerun()
            with cols[1]:
                if st.button("Non-Vegetarian", key="non_veg_btn"):
                    st.session_state.dietary_pref = "Non-Vegetarian"
                    st.session_state.step = 3
                    add_message("user", "Non-Vegetarian")
                    st.rerun()

        elif st.session_state.step == 3:
            q = "What kind of flavors do you enjoy? (You can select multiple)"
            if not any(chat["message"] == q for chat in st.session_state.chat_history):
                add_message("bot", q)

            selected_tastes = st.multiselect(
                "Select your taste preferences:",
                options=taste_options,
                default=st.session_state.selected_tastes,
                key="taste_select_unique",
                label_visibility="collapsed"
            )
            if st.button("Find Recommendations", key="find_recs"):
                st.session_state.selected_tastes = selected_tastes
                st.session_state.step = 4
                tastes_text = ", ".join(selected_tastes) if selected_tastes else "No preference"
                add_message("user", tastes_text)
                st.rerun()

        elif st.session_state.step == 4:
            if not st.session_state.recommendations:
                st.session_state.recommendations = recommend_dishes()
            display_recommendations()

    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        st.markdown(
            """
            <div class='error-message'>
                ❌ Sorry, something went wrong. Please refresh the page and try again.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Restart Application", key="full_restart"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.step = 0
            st.session_state.chat_history = []
            st.session_state.welcome_shown = False
            st.rerun()


if __name__ == "__main__":
    main()
