"""
OI Data Request Form — internal sales intake tool.

Google Sign-In (allowlist) -> full request form -> validate -> transform to the
campaign-template fields -> save one row per submission to the Google Sheet,
tagged with the verified requester's email.
"""

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
    try:
        return bool(st.secrets["auth"])
    except Exception:
        return False


def allowed_emails():
    try:
        raw = st.secrets["allowed_emails"]
    except Exception:
        return []
    if isinstance(raw, str):
        return [e.strip().lower() for e in raw.split(",") if e.strip()]
    return [str(e).strip().lower() for e in raw]


# ── Auth gate ────────────────────────────────────────────────────────────────
def require_login():
    if not _auth_configured():
        st.title("📋 OI Data Request Form")
        st.warning(
            "🔒 Login isn't configured yet. Add the `[auth]` block and "
            "`allowed_emails` to the app secrets, then reload."
        )
        st.stop()

    if not st.user.is_logged_in:
        st.title("📋 OI Data Request Form")
        st.write("Sign in with your **One Infinity** Google account to continue.")
        st.button("Sign in with Google", type="primary", on_click=st.login)
        st.stop()

    email = (st.user.email or "").strip().lower()
    if email not in allowed_emails():
        st.title("📋 OI Data Request Form")
        st.error(
            f"Access denied for **{email}**. This tool is restricted to approved "
            "One Infinity users. Contact the data team if you need access."
        )
        st.button("Sign out", on_click=st.logout)
        st.stop()
    return email


user_email = require_login()


def _i(x):
    """number_input value -> int or None (preserves an explicit 0)."""
    return int(x) if x is not None else None


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.caption("Signed in as")
    st.write(f"**{st.user.get('name', user_email)}**")
    st.write(user_email)
    st.button("Sign out", on_click=st.logout, use_container_width=True)

# ── Form ─────────────────────────────────────────────────────────────────────
st.title("📋 OI Data Request Form")
st.caption(
    "Fill in what you need — blank filters mean no restriction. "
    "Your verified email is recorded on every submission."
)

st.subheader("1 · Recipient")
c1, c2 = st.columns(2)
recipient_name = c1.text_input("Recipient name \\*")
if not recipient_name.strip():
    c1.markdown(":orange[Required]")
recipient_type = c2.selectbox(
    "Recipient type \\*", mappings.RECIPIENT_TYPES, index=None, placeholder="Select…"
)
if not recipient_type:
    c2.markdown(":orange[Required]")

c3, c4 = st.columns(2)
recipient_contact = c3.text_input("Contact number \\*", placeholder="10-digit mobile")
if recipient_contact and not mappings.valid_mobile(recipient_contact):
    c3.markdown(":red[⚠️ 10-digit mobile starting 6–9]")
elif not recipient_contact:
    c3.markdown(":orange[Required]")
recipient_email = c4.text_input("Email \\*")
if recipient_email and not mappings.valid_email(recipient_email):
    c4.markdown(":red[⚠️ Invalid email address]")
elif not recipient_email:
    c4.markdown(":orange[Required]")

c5, c6 = st.columns(2)
recipient_gst = c5.text_input("GST (preferred)", placeholder="27ABCDE1234F1Z5")
if recipient_gst and not mappings.valid_gstin(recipient_gst):
    c5.markdown(":red[⚠️ Not a valid 15-char GSTIN]")
recipient_pan = c6.text_input("PAN", placeholder="ABCDE1234F")
if recipient_pan and not mappings.valid_pan(recipient_pan):
    c6.markdown(":red[⚠️ Must look like ABCDE1234F]")
_gst_ok = bool(recipient_gst) and mappings.valid_gstin(recipient_gst)
_pan_ok = bool(recipient_pan) and mappings.valid_pan(recipient_pan)
if not recipient_gst and not recipient_pan:
    st.markdown(":orange[Provide **GST or PAN** — GST preferred. At least one is required.]")
elif _gst_ok and _pan_ok and not mappings.gstin_pan_match(recipient_gst, recipient_pan):
    st.markdown(":red[⚠️ GST does not embed this PAN (characters 3–12).]")

st.subheader("2 · Campaign")
target_count = st.number_input(
    "How many leads do you need? (target count) \\*", min_value=1, step=1000, value=None
)
if not target_count:
    st.markdown(":orange[Required]")
allow_ntc = st.checkbox("Allow new-to-credit (no bureau score)", value=True)

st.subheader("3 · Demographics")
c9, c10, c11 = st.columns(3)
min_age = c9.number_input("Min age", min_value=18, max_value=100, step=1, value=None)
max_age = c10.number_input("Max age", min_value=18, max_value=100, step=1, value=None)
min_salary = c11.number_input("Min monthly salary (₹)", min_value=0, step=5000, value=None)
if min_age and max_age and min_age > max_age:
    st.markdown(":red[⚠️ Min age cannot exceed max age.]")
employment_type = st.selectbox("Employment type", mappings.EMPLOYMENT_ENABLED, index=0)
st.caption("Self-employed / Both — coming later (only salaried data available today).")

st.subheader("4 · Bureau score bands")
score_bands = st.multiselect(
    "Which score bands?",
    mappings.SCORE_BAND_LABELS,
    help="Pick the bands, then set how many leads from each — they must add up to the target count.",
)
quotas = {}
if score_bands:
    st.caption("Leads per band (must total the target count):")
    qcols = st.columns(len(score_bands))
    for i, b in enumerate(score_bands):
        quotas[b] = qcols[i].number_input(b, min_value=0, step=500, value=0, key=f"quota_{b}")
    running = sum(int(quotas[b] or 0) for b in score_bands)
    tc = int(target_count) if target_count else 0
    if tc:
        if running == tc:
            st.success(f"Quotas total {running:,} = target {tc:,} ✓")
        else:
            st.warning(f"Quotas total {running:,}, target {tc:,} (off by {running - tc:+,})")

st.subheader("5 · Products & enquiry behaviour")
products_include = st.multiselect(
    "Products they enquired for (include)",
    mappings.PRODUCT_LABELS,
    help="Blank = any product. Deepest pools: Personal Loan and Credit Card.",
)
products_exclude = st.multiselect("Products to exclude", mappings.PRODUCT_LABELS)
lenders_include = st.multiselect("Lender types (include)", mappings.MEMBER_CLASS_LABELS)
lenders_exclude = st.multiselect("Lender types to exclude", mappings.MEMBER_CLASS_LABELS)
c12, c13 = st.columns(2)
enq_window_days = c12.number_input(
    "Enquiry look-back window (days)", min_value=1, step=15, value=None,
    help=f"Counted back from {mappings.REFERENCE_DATE}. Blank = all history.",
)
enq_max_in_window = c13.number_input(
    "Max enquiries in that window", min_value=0, step=1, value=None
)

st.subheader("6 · Credit conduct")
credit_conduct = st.radio(
    "How clean should their credit be?",
    mappings.DPD_PRESET_LABELS,
    index=2,
    horizontal=True,
    help="Strict = spotless (no missed payments / overdue / write-off). "
         "Moderate = no serious recent delinquency. Any = no filter.",
)
pan_required = st.checkbox("Require a PAN on every lead", value=True)

with st.expander("Advanced (optional)"):
    ac1, ac2 = st.columns(2)
    min_score = ac1.number_input(
        "Min score", min_value=mappings.SCORE_MIN, max_value=mappings.SCORE_MAX, step=1, value=None
    )
    max_score = ac2.number_input(
        "Max score", min_value=mappings.SCORE_MIN, max_value=mappings.SCORE_MAX, step=1, value=None
    )
    city = st.text_input(
        "City", help="Not yet wired into the generator — flagged as a custom run."
    )
    ac3, ac4 = st.columns(2)
    loan_amount_min = ac3.number_input("Loan amount min (₹)", min_value=0, step=50000, value=None)
    loan_amount_max = ac4.number_input(
        "Loan amount max (₹)", min_value=0, step=50000, value=None,
        help="Auto-capped at ₹1 cr to dodge data outliers.",
    )

st.subheader("7 · Output & notes")
extra_columns = st.text_input("Any extra output columns? (optional)", placeholder="e.g. State, Pincode")
notes = st.text_area("Notes for the data team (optional)")

st.divider()
if "submit_running" not in st.session_state:
    st.session_state.submit_running = False

if st.button("Submit data request", type="primary",
             disabled=st.session_state.submit_running):
    st.session_state.submit_running = True
    st.rerun()

if st.session_state.submit_running:
    answers = {
        "recipient_name": recipient_name,
        "recipient_type": recipient_type,
        "recipient_contact": recipient_contact,
        "recipient_email": recipient_email,
        "recipient_pan": recipient_pan,
        "recipient_gst": recipient_gst,
        "target_count": _i(target_count),
        "allow_ntc": allow_ntc,
        "min_age": _i(min_age),
        "max_age": _i(max_age),
        "min_salary_monthly": _i(min_salary),
        "employment_type": employment_type,
        "city": city,
        "score_bands": score_bands,
        "quotas": quotas,
        "min_score": _i(min_score),
        "max_score": _i(max_score),
        "products_include": products_include,
        "products_exclude": products_exclude,
        "lenders_include": lenders_include,
        "lenders_exclude": lenders_exclude,
        "enq_window_days": _i(enq_window_days),
        "enq_max_in_window": _i(enq_max_in_window),
        "loan_amount_min": _i(loan_amount_min),
        "loan_amount_max": _i(loan_amount_max),
        "credit_conduct": credit_conduct,
        "pan_required": pan_required,
    }

    errors = mappings.validate_submission(answers)
    st.session_state.submit_running = False
    if errors:
        st.error("Please fix the following before submitting:")
        for e in errors:
            st.markdown(f"- {e}")
    else:
        save_error = None
        with st.spinner("Submitting your request — creating the workbook and logging it… (a few seconds)"):
            tvals = mappings.to_template_values(answers)
            ts = mappings.ist_timestamp()
            meta_pairs = [
                ("submitted_at", ts),
                ("requested_by", user_email),
                ("recipient_contact", recipient_contact),
                ("recipient_email", recipient_email),
                ("recipient_pan", recipient_pan),
                ("recipient_gst", recipient_gst),
            ]
            template_pairs = [(f, tvals[f]) for f in mappings.TEMPLATE_FIELDS]
            tail_pairs = [("extra_output_columns", extra_columns), ("notes", notes)]
            pairs = meta_pairs + template_pairs + tail_pairs
            request_title = f"{user_email} — {recipient_name} — {ts}"
            try:
                fname, furl = storage.create_request_workbook(request_title, pairs)
                header = (
                    ["submitted_at", "requested_by", "request_file", "request_url",
                     "recipient_contact", "recipient_email", "recipient_pan", "recipient_gst"]
                    + mappings.TEMPLATE_FIELDS
                    + ["extra_output_columns", "notes"]
                )
                row = (
                    [ts, user_email, fname, furl, recipient_contact, recipient_email,
                     recipient_pan, recipient_gst]
                    + [tvals[f] for f in mappings.TEMPLATE_FIELDS]
                    + [extra_columns, notes]
                )
                storage.append_master(header, row)
            except Exception as exc:
                save_error = exc

        if save_error is not None:
            st.error(f"Save failed: {type(save_error).__name__}: {save_error!r}")
            st.exception(save_error)
        else:
            st.success(f"✅ Request submitted and recorded against **{user_email}**.")
            st.markdown(f"📄 Request workbook: **[{fname}]({furl})**")
