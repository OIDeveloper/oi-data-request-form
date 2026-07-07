"""
OI Data Request Form — internal sales intake tool.

Google Sign-In (allowlist) -> full request form -> validate -> transform to the
campaign-template fields -> save one row per submission to the Google Sheet,
tagged with the verified requester's email.
"""

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

import mappings
import storage

st.set_page_config(
    page_title="OI Data Request Form",
    page_icon="📋",
    layout="wide",
)

# Hide the auto-generated anchor-link icon that Streamlit adds to every header.
st.markdown(
    "<style>[data-testid='stHeaderActionElements']{display:none;}</style>",
    unsafe_allow_html=True,
)




# ── Secrets helpers ──────────────────────────────────────────────────────────
def _auth_configured():
    try:
        return bool(st.secrets["auth"])
    except Exception:
        return False


# Always allowed + always admin, regardless of the App Users sheet (anti-lockout).
BOOTSTRAP_ADMIN = "developer@oneinfinity.in"


def _secrets_allowlist():
    """Legacy allowlist from secrets — used only to seed the App Users sheet once."""
    try:
        raw = st.secrets["allowed_emails"]
    except Exception:
        return []
    if isinstance(raw, str):
        return [e.strip().lower() for e in raw.split(",") if e.strip()]
    return [str(e).strip().lower() for e in raw]


@st.cache_data(ttl=60, show_spinner=False)
def _user_records():
    try:
        return storage.get_or_seed_app_users(_secrets_allowlist(), BOOTSTRAP_ADMIN)
    except Exception:
        return []


def user_map():
    """email -> is_admin(bool), from the App Users sheet. The bootstrap admin is
    always present as admin so no edit can lock everyone out."""
    m = {}
    for r in _user_records():
        e = str(r.get("email", "")).strip().lower()
        if e:
            m[e] = str(r.get("is_admin", "")).strip().lower() in ("yes", "true", "1")
    m[BOOTSTRAP_ADMIN] = True
    return m


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
    if email not in user_map():
        st.title("📋 OI Data Request Form")
        st.error(
            f"Access denied for **{email}**. This tool is restricted to approved "
            "One Infinity users. Contact the data team if you need access."
        )
        st.button("Sign out", on_click=st.logout)
        st.stop()
    return email


user_email = require_login()
is_admin = user_map().get(user_email, False)

# Logo only after a successful, authorised login (require_login stops before here).
st.logo("assets/oneflo-logo.png", size="large")


def _i(x):
    """number_input value -> int or None (preserves an explicit 0)."""
    return int(x) if x is not None else None


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.caption("Signed in as")
    st.write(f"**{st.user.get('name', user_email)}**")
    st.write(user_email)
    st.button("Sign out", on_click=st.logout, use_container_width=True)
    if is_admin:
        st.divider()
        if st.button("👥 Manage users", use_container_width=True):
            st.session_state.page = "users"
            st.rerun()
        if st.button("🧹 Admin cleanup", use_container_width=True):
            st.session_state.page = "admin"
            st.rerun()

# ── Form version (bumping it gives every widget a fresh key = blank form) ────
if "form_ver" not in st.session_state:
    st.session_state.form_ver = 0
V = st.session_state.form_ver

# ── Page routing ─────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "landing"

if st.session_state.page == "users":
    if not is_admin:
        st.session_state.page = "landing"
        st.rerun()
    uh_l, uh_r = st.columns([3, 2])
    uh_l.title("👥 Manage app users")
    if uh_r.button("← Back to my requests", use_container_width=True):
        st.session_state.page = "landing"
        st.rerun()

    if "udel_running" not in st.session_state:
        st.session_state.udel_running = False
    if "uconfirm_ver" not in st.session_state:
        st.session_state.uconfirm_ver = 0

    # Process a pending removal (disabled button + spinner = no double-click).
    if st.session_state.udel_running:
        with st.spinner("Removing user(s)…"):
            n_rm = storage.delete_app_users(st.session_state.get("pending_udel", []))
        st.session_state.udel_running = False
        st.session_state.pop("pending_udel", None)
        st.session_state.uconfirm_ver += 1
        _user_records.clear()
        st.session_state.user_msg = f"Removed {n_rm} user(s)."
        st.rerun()

    if "user_msg" in st.session_state:
        st.success(st.session_state.pop("user_msg"))

    st.caption(
        "Anyone listed here can sign in. Tick ‘Admin’ to grant admin access. "
        f"{BOOTSTRAP_ADMIN} is always an admin and cannot be removed."
    )

    with st.container(border=True):
        st.subheader("Add a user", anchor=False)
        ac1, ac2, ac3 = st.columns([3, 1, 1])
        new_email = ac1.text_input("Email", placeholder="name@oneinfinity.in", key="new_user_email")
        new_admin = ac2.checkbox("Admin", value=False, key="new_user_admin")
        if ac3.button("Add / update", type="primary"):
            e = (new_email or "").strip().lower()
            if not mappings.valid_email(e):
                st.error("Enter a valid email address.")
            else:
                with st.spinner("Saving…"):
                    storage.add_app_user(e, new_admin, user_email, mappings.ist_timestamp())
                _user_records.clear()
                st.session_state.user_msg = f"Saved {e}."
                st.rerun()

    try:
        urecs = storage.get_or_seed_app_users(_secrets_allowlist(), BOOTSTRAP_ADMIN)
    except Exception as exc:
        st.error(f"Couldn't load users: {type(exc).__name__}: {exc!r}")
        urecs = []

    udf = pd.DataFrame(urecs)
    if udf.empty:
        st.info("No users yet.")
        st.stop()

    ugb = GridOptionsBuilder.from_dataframe(udf)
    ugb.configure_default_column(editable=False, sortable=True, filter=False, resizable=True)
    ugb.configure_selection("multiple", use_checkbox=True, header_checkbox=True)
    uopts = ugb.build()
    uopts["autoSizeStrategy"] = {"type": "fitCellContents"}
    ugrid = AgGrid(
        udf, gridOptions=uopts, theme="alpine", height=360,
        allow_unsafe_jscode=True, fit_columns_on_grid_load=False,
        enable_enterprise_modules=False, update_mode=GridUpdateMode.SELECTION_CHANGED,
    )
    try:
        usel = ugrid["selected_rows"]
    except Exception:
        usel = getattr(ugrid, "selected_rows", None)
    if usel is None:
        sel_emails = []
    elif isinstance(usel, pd.DataFrame):
        sel_emails = usel["email"].dropna().tolist() if "email" in usel.columns else []
    else:
        sel_emails = [r.get("email") for r in usel if r.get("email")]
    # never allow removing the bootstrap admin
    sel_emails = [e for e in sel_emails if str(e).strip().lower() != BOOTSTRAP_ADMIN]

    st.write(f"**{len(sel_emails)}** user(s) selected for removal.")
    uconfirm = st.checkbox(
        "Yes, remove the selected users.", value=False,
        key=f"uconfirm_{st.session_state.uconfirm_ver}",
    )
    if st.button("Remove selected", type="primary",
                 disabled=st.session_state.udel_running or not (sel_emails and uconfirm)):
        st.session_state.udel_running = True
        st.session_state.pending_udel = sel_emails
        st.rerun()
    st.stop()

if st.session_state.page == "admin":
    if not is_admin:
        st.session_state.page = "landing"
        st.rerun()
    ah_l, ah_r = st.columns([3, 2])
    ah_l.title("🧹 Admin — Clean up requests")
    if ah_r.button("← Back to my requests", use_container_width=True):
        st.session_state.page = "landing"
        st.rerun()

    if "delete_running" not in st.session_state:
        st.session_state.delete_running = False
    if "confirm_ver" not in st.session_state:
        st.session_state.confirm_ver = 0

    # Process a pending delete (button stays disabled + spinner = no double-click).
    if st.session_state.delete_running:
        urls = st.session_state.get("pending_delete", [])
        with st.spinner("Deleting workbooks and log rows…"):
            n_done, errs = storage.delete_requests(urls)
        st.session_state.delete_running = False
        st.session_state.pop("pending_delete", None)
        st.session_state.confirm_ver += 1          # reset the confirm checkbox
        st.session_state.admin_result = (n_done, errs)
        st.rerun()

    if "admin_result" in st.session_state:
        n_done, errs = st.session_state.pop("admin_result")
        st.success(f"Deleted {n_done} request(s).")
        for e in errs:
            st.error(e)

    st.warning(
        "Deleting a request permanently removes its workbook file **and** its row "
        "in the master log. This cannot be undone."
    )

    try:
        records = storage.read_all_requests()
    except Exception as exc:
        st.error(f"Couldn't load requests: {type(exc).__name__}: {exc!r}")
        records = []
    if not records:
        st.info("No requests to clean up.")
        st.stop()

    adf = pd.DataFrame(records)
    if "submitted_at" in adf.columns:
        adf = adf.sort_values("submitted_at", ascending=False)

    gb = GridOptionsBuilder.from_dataframe(adf)
    gb.configure_default_column(editable=False, sortable=True, filter=False, resizable=True)
    gb.configure_selection("multiple", use_checkbox=True, header_checkbox=True)
    gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=25)
    gopts = gb.build()
    gopts["paginationPageSizeSelector"] = [10, 25, 50]
    gopts["autoSizeStrategy"] = {"type": "fitCellContents"}
    grid = AgGrid(
        adf, gridOptions=gopts, theme="alpine", height=470,
        allow_unsafe_jscode=True, fit_columns_on_grid_load=False,
        enable_enterprise_modules=False, update_mode=GridUpdateMode.SELECTION_CHANGED,
    )

    try:
        sel = grid["selected_rows"]
    except Exception:
        sel = getattr(grid, "selected_rows", None)
    if sel is None:
        sel_urls = []
    elif isinstance(sel, pd.DataFrame):
        sel_urls = sel["request_url"].dropna().tolist() if "request_url" in sel.columns else []
    else:
        sel_urls = [r.get("request_url") for r in sel if r.get("request_url")]

    st.write(f"**{len(sel_urls)}** request(s) selected.")
    confirm = st.checkbox(
        "Yes, permanently delete the selected requests and their workbooks.",
        value=False, key=f"confirm_del_{st.session_state.confirm_ver}",
    )
    if st.button("Delete selected", type="primary",
                 disabled=st.session_state.delete_running or not (sel_urls and confirm)):
        st.session_state.delete_running = True
        st.session_state.pending_delete = sel_urls
        st.rerun()
    st.stop()

if st.session_state.page == "landing":
    head_l, head_r = st.columns([3, 2])
    head_l.title("📋 My Data Requests")
    if head_r.button("➕ Submit new data request", type="primary",
                     use_container_width=True):
        st.session_state.page = "form"
        st.rerun()

    if st.session_state.pop("just_submitted", False):
        st.success("✅ Your request was submitted and saved.")

    try:
        records = storage.read_all_requests()
    except Exception as exc:
        st.error(f"Couldn't load your requests: {type(exc).__name__}: {exc!r}")
        records = []

    mine = [r for r in records
            if str(r.get("requested_by", "")).strip().lower() == user_email]

    if not mine:
        st.info("You haven't placed any requests yet. "
                "Use **Submit new data request** (top-right) to begin.")
        st.stop()

    df = pd.DataFrame(mine)
    if "submitted_at" in df.columns:
        df = df.sort_values("submitted_at", ascending=False)   # newest first
    # keep only columns this user actually filled (the data points they requested)
    non_empty = df.astype(str).apply(lambda col: col.str.strip().ne("").any())
    df = df.loc[:, non_empty]
    # Drop the workbook LINK (shared-drive, data-team only — requester may lack
    # access). Keep request_file (just a name) so the requester can trace their request.
    df = df.drop(columns=["request_url"], errors="ignore")

    # --- AG Grid: native pagination, page-size selector, sort/filter/resize ---
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(editable=False, sortable=True, filter=False, resizable=True)
    gb.configure_pagination(
        enabled=True, paginationAutoPageSize=False, paginationPageSize=10
    )
    grid_options = gb.build()
    grid_options["paginationPageSizeSelector"] = [10, 25, 50]
    # Size every column to its content at init (AG Grid v31+ native strategy).
    grid_options["autoSizeStrategy"] = {"type": "fitCellContents"}

    AgGrid(
        df,
        gridOptions=grid_options,
        theme="alpine",
        height=470,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
    )
    st.stop()

# ── Form ─────────────────────────────────────────────────────────────────────
head_l, head_r = st.columns([3, 2])
head_l.title("📋 New Data Request")
if head_r.button("← Back to my requests", use_container_width=True):
    st.session_state.page = "landing"
    st.rerun()
st.caption(
    "Fill in what you need — blank filters mean no restriction. "
    "Your verified email is recorded on every submission."
)

st.subheader("1 · Recipient")
c1, c2 = st.columns(2)
recipient_name = c1.text_input("Recipient name \\*", key=f"recipient_name_{V}")
if not recipient_name.strip():
    c1.markdown(":orange[Required]")
recipient_type = c2.selectbox(
    "Recipient type \\*", mappings.RECIPIENT_TYPES, index=None, placeholder="Select…",
    key=f"recipient_type_{V}",
)
if not recipient_type:
    c2.markdown(":orange[Required]")

c3, c4 = st.columns(2)
recipient_contact = c3.text_input("Contact number \\*", placeholder="10-digit mobile", key=f"recipient_contact_{V}")
if recipient_contact and not mappings.valid_mobile(recipient_contact):
    c3.markdown(":red[⚠️ 10-digit mobile starting 6–9]")
elif not recipient_contact:
    c3.markdown(":orange[Required]")
recipient_email = c4.text_input("Email \\*", key=f"recipient_email_{V}")
if recipient_email and not mappings.valid_email(recipient_email):
    c4.markdown(":red[⚠️ Invalid email address]")
elif not recipient_email:
    c4.markdown(":orange[Required]")

c5, c6 = st.columns(2)
recipient_gst = c5.text_input("GST (preferred)", placeholder="27ABCDE1234F1Z5", key=f"recipient_gst_{V}")
if recipient_gst and not mappings.valid_gstin(recipient_gst):
    c5.markdown(":red[⚠️ Not a valid 15-char GSTIN]")
recipient_pan = c6.text_input("PAN", placeholder="ABCDE1234F", key=f"recipient_pan_{V}")
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
    "How many leads do you need? (target count) \\*", min_value=1, step=1000, value=None,
    key=f"target_count_{V}",
)
if not target_count:
    st.markdown(":orange[Required]")
allow_ntc = st.checkbox("Allow new-to-credit (no bureau score)", value=True, key=f"allow_ntc_{V}")

st.subheader("3 · Demographics")
c9, c10, c11 = st.columns(3)
min_age = c9.number_input("Min age", min_value=18, max_value=100, step=1, value=None, key=f"min_age_{V}")
max_age = c10.number_input("Max age", min_value=18, max_value=100, step=1, value=None, key=f"max_age_{V}")
min_salary = c11.number_input("Min monthly salary (₹)", min_value=0, step=5000, value=None, key=f"min_salary_{V}")
if min_age and max_age and min_age > max_age:
    st.markdown(":red[⚠️ Min age cannot exceed max age.]")
employment_type = st.selectbox("Employment type", mappings.EMPLOYMENT_ENABLED, index=0, key=f"employment_type_{V}")
st.caption("Self-employed / Both — coming later (only salaried data available today).")

st.subheader("4 · Bureau score bands")
score_bands = st.multiselect(
    "Which score bands?",
    mappings.SCORE_BAND_LABELS,
    help="Pick the bands, then set how many leads from each — they must add up to the target count.",
    key=f"score_bands_{V}",
)
quotas = {}
if score_bands:
    st.caption("Leads per band (must total the target count):")
    qcols = st.columns(len(score_bands))
    for i, b in enumerate(score_bands):
        quotas[b] = qcols[i].number_input(b, min_value=0, step=500, value=0, key=f"quota_{b}_{V}")
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
    key=f"products_include_{V}",
)
products_exclude = st.multiselect("Products to exclude", mappings.PRODUCT_LABELS, key=f"products_exclude_{V}")
lenders_include = st.multiselect("Lender types (include)", mappings.MEMBER_CLASS_LABELS, key=f"lenders_include_{V}")
lenders_exclude = st.multiselect("Lender types to exclude", mappings.MEMBER_CLASS_LABELS, key=f"lenders_exclude_{V}")
c12, c13 = st.columns(2)
enq_window_days = c12.number_input(
    "Enquiry look-back window (days)", min_value=1, step=15, value=None,
    help=f"Counted back from {mappings.REFERENCE_DATE}. Blank = all history.",
    key=f"enq_window_days_{V}",
)
enq_max_in_window = c13.number_input(
    "Max enquiries in that window", min_value=0, step=1, value=None, key=f"enq_max_in_window_{V}"
)

st.subheader("6 · Credit conduct")
credit_conduct = st.radio(
    "How clean should their credit be?",
    mappings.DPD_PRESET_LABELS,
    index=2,
    horizontal=True,
    help="Strict = spotless (no missed payments / overdue / write-off). "
         "Moderate = no serious recent delinquency. Any = no filter.",
    key=f"credit_conduct_{V}",
)
pan_required = st.checkbox("Require a PAN on every lead", value=False, key=f"pan_required_{V}")

with st.expander("Advanced (optional)"):
    ac1, ac2 = st.columns(2)
    min_score = ac1.number_input(
        "Min score", min_value=mappings.SCORE_MIN, max_value=mappings.SCORE_MAX, step=1, value=None,
        key=f"min_score_{V}",
    )
    max_score = ac2.number_input(
        "Max score", min_value=mappings.SCORE_MIN, max_value=mappings.SCORE_MAX, step=1, value=None,
        key=f"max_score_{V}",
    )
    city = st.text_input(
        "City", help="Not yet wired into the generator — flagged as a custom run.",
        key=f"city_{V}",
    )
    ac3, ac4 = st.columns(2)
    loan_amount_min = ac3.number_input("Loan amount min (₹)", min_value=0, step=50000, value=None, key=f"loan_amount_min_{V}")
    loan_amount_max = ac4.number_input(
        "Loan amount max (₹)", min_value=0, step=50000, value=None,
        help="Auto-capped at ₹1 cr to dodge data outliers.",
        key=f"loan_amount_max_{V}",
    )

st.subheader("7 · Output & notes")
extra_columns = st.text_input("Any extra output columns? (optional)", placeholder="e.g. State, Pincode", key=f"extra_columns_{V}")
notes = st.text_area("Notes for the data team (optional)", key=f"notes_{V}")

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
            st.session_state.page = "landing"
            st.session_state.form_ver += 1        # blank the form for next time
            st.session_state.just_submitted = True
            st.rerun()
