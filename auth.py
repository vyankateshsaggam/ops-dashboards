"""
auth.py
--------
Lightweight, session-based authentication module for the Streamlit dashboard.
Supports two roles: Admin (can upload/replace data) and Viewer (read-only).

Note: credentials are stored in config.json for simplicity/demo purposes.
For real production use, replace the `_check_credentials` function with a
call to your corporate identity provider (LDAP / SSO / Azure AD / OAuth2)
or hash passwords with bcrypt and store them in a secure DB.
"""
import streamlit as st
import hashlib
import base64
from pathlib import Path

# Path to the brand logo used on the login screen.
# Replace this file to swap the logo without touching any code.
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def _get_logo_base64() -> str:
    """Reads the logo file and returns a base64 data URI, or '' if missing."""
    try:
        data = LOGO_PATH.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except FileNotFoundError:
        return ""


class AuthManager:
    def __init__(self, users_config: dict):
        """users_config = config["users"] dict loaded from config.json"""
        self.users_config = users_config

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _check_credentials(self, username: str, password: str):
        user = self.users_config.get(username.strip().lower())
        if user and user["password"] == password:
            return user["role"]
        return None

    def is_logged_in(self) -> bool:
        return st.session_state.get("authenticated", False)

    def current_user(self):
        return st.session_state.get("username"), st.session_state.get("role")

    def logout(self):
        for key in ("authenticated", "username", "role"):
            st.session_state.pop(key, None)
        st.rerun()

    def login_screen(self):
        """Renders a centered glassmorphism-styled login card."""
        st.markdown(
            """
            <style>
            .login-wrap {display:flex; justify-content:center; margin-top:60px;}
            .login-card {
                background: rgba(255,255,255,0.07);
                backdrop-filter: blur(12px);
                border-radius: 20px;
                padding: 40px 45px;
                width: 380px;
                border: 1px solid rgba(255,255,255,0.18);
                box-shadow: 0 8px 32px rgba(31,38,135,0.25);
            }
            .login-logo-row {
                display:flex; align-items:center; justify-content:center;
                gap:12px; margin-bottom:4px;
            }
            .login-logo-row img {
                height:44px; width:auto; object-fit:contain;
            }
            .login-title {
                font-size:26px; font-weight:800;
                background: linear-gradient(90deg,#7C3AED,#06B6D4);
                -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            }
            .login-sub {text-align:center; color:#9CA3AF; margin-bottom:22px; font-size:13px;}
            </style>
            """,
            unsafe_allow_html=True,
        )
        logo_uri = _get_logo_base64()
        logo_html = f'<img src="{logo_uri}" alt="logo"/>' if logo_uri else "📦"

        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.markdown(
                f'<div class="login-logo-row">{logo_html}'
                f'<span class="login-title">Ops Intelligence</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="login-sub">Sign in to access the dashboard</div>', unsafe_allow_html=True)
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign In →", use_container_width=True)
                if submitted:
                    role = self._check_credentials(username, password)
                    if role:
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.session_state.role = role
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
