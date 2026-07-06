"""
OI Data Request Form — internal sales intake tool.

Step 4 skeleton: password gate + pipeline sanity check. The full request form
is built on top of this in later steps.
"""

import streamlit as st

import mappings

st.set_page_config(
    page_title="OI Data Request Form",
    page_icon="📋",
    layout="centered",
)


def _get_secret(key, default=None):
    """Read a Streamlit secret without crashing when none are configured yet."""
    try:
        return st.secrets[key]
    except Exception:
        return default


def check_password():
    """Shared-password gate.

    Before an `app_password` secret is configured (Step 6) this runs in dev mode
    and lets you in with a visible warning, so the very first cloud deploy works.
    Once the secret is set, access requires the password.
    """
    expected = _get_secret("app_password")
    if not expected:
        st.info(
            "⚠️ Dev mode — no `app_password` secret set yet. "
            "Anyone with the URL can view this. We lock it down in Step 6."
        )
        return True
    if st.session_state.get("authed"):
        return True
    st.title("📋 OI Data Request Form")
    with st.form("login"):
        pw = st.text_input("Access password", type="password")
        if st.form_submit_button("Enter"):
            if pw == expected:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ── Authed content (skeleton) ────────────────────────────────────────────────
st.title("📋 OI Data Request Form")
st.success("Skeleton deployed successfully — the pipeline works. ✅")
st.caption("Internal sales tool. The full data-cut request form is built here next.")

with st.expander("Sanity check — mappings.py loaded on this host"):
    st.write(f"**Products:** {len(mappings.PRODUCTS)}")
    st.write(f"**Member classes:** {len(mappings.MEMBER_CLASSES)}")
    st.write(f"**Score bands:** {len(mappings.SCORE_BANDS)}")
    st.write(f"**DPD presets:** {', '.join(mappings.DPD_PRESET_LABELS)}")
    st.write(f"**Reference date:** {mappings.REFERENCE_DATE}")
