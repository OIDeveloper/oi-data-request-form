"""
OI Data Request Form — internal sales intake tool.

Auth: Google Sign-In (Streamlit native OIDC) restricted to an allowlist of
emails held in secrets. The verified signed-in email is captured on every
request so we always know who asked for each data cut.

The full request form is built on top of this in later steps.
"""

from datetime import datetime, timezone

import streamlit as st

import mappings
import storage

st.set_page_config(
    page_title="OI Data Request Form",
    page_icon="📋",
    layout="centered",
)


# ── Secrets helpers ──────────────────────────────────────────────────────────
def _auth_configured():
    """True once the [auth] OIDC block exists in secrets."""
    try:
        return bool(st.secrets["auth"])
    except Exception:
        return False


def allowed_emails():
    """Lowercased allowlist from secrets. Accepts a TOML list or CSV string.

    Empty/absent -> returns [] which means 'deny everyone' (fail closed).
    """
    try:
        raw = st.secrets["allowed_emails"]
    except Exception:
        return []
    if isinstance(raw, str):
        return [e.strip().lower() for e in raw.split(",") if e.strip()]
    return [str(e).strip().lower() for e in raw]


# ── Auth gate ────────────────────────────────────────────────────────────────
def require_login():
    """Enforce Google Sign-In + allowlist. Returns the verified email, or stops."""
    # Before OAuth secrets are configured, don't crash — show a setup notice.
    if not _auth_configured():
        st.title("📋 OI Data Request Form")
        st.warning(
            "🔒 Login isn't configured yet. Add the `[auth]` block and "
            "`allowed_emails` to the app secrets (Step 6), then reload."
        )
        st.stop()

    if not st.user.is_logged_in:
        st.title("📋 OI Data Request Form")
        st.write("Sign in with your **One Infinity** Google account to continue.")
        st.button("Sign in with Google", type="primary", on_click=st.login)
        st.stop()

    email = (st.user.email or "").strip().lower()
    allow = allowed_emails()
    if email not in allow:
        st.title("📋 OI Data Request Form")
        st.error(
            f"Access denied for **{email}**. This tool is restricted to "
            "approved One Infinity users. Contact the data team if you need access."
        )
        st.button("Sign out", on_click=st.logout)
        st.stop()

    return email


user_email = require_login()


# ── Authed content (skeleton) ────────────────────────────────────────────────
with st.sidebar:
    st.caption("Signed in as")
    st.write(f"**{st.user.get('name', user_email)}**")
    st.write(user_email)
    st.button("Sign out", on_click=st.logout, use_container_width=True)

st.title("📋 OI Data Request Form")
st.success(f"Signed in and authorised as **{user_email}** ✅")
st.caption(
    "Internal sales tool. Every request you submit will be tagged with your "
    "verified email. The full data-cut request form is built here next."
)

with st.expander("Sanity check — mappings.py loaded on this host"):
    st.write(f"**Products:** {len(mappings.PRODUCTS)}")
    st.write(f"**Member classes:** {len(mappings.MEMBER_CLASSES)}")
    st.write(f"**Score bands:** {len(mappings.SCORE_BANDS)}")
    st.write(f"**DPD presets:** {', '.join(mappings.DPD_PRESET_LABELS)}")
    st.write(f"**Reference date:** {mappings.REFERENCE_DATE}")

st.divider()
st.subheader("Step 7 — Google Sheet persistence test")
if storage.storage_configured():
    if st.button("Send a test row to the Sheet"):
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            storage.append_row([ts, user_email, "test submission"])
            st.success("✅ Wrote a test row — check the Google Sheet.")
        except Exception as exc:
            st.error(f"Write failed: {exc}")
else:
    st.info(
        "Google Sheet not configured yet — add the `[sheets]` and "
        "`[gcp_service_account]` sections to secrets (Step 7)."
    )
