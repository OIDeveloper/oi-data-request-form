"""
mappings.py — single source of truth for the OI Data Request Form.

Holds the CORRECTED Experian code mappings, score bands, DPD presets, recipient
types, validators, and small builder helpers. No Streamlit dependency, so this
module can also be imported by the lakehouse generator scripts to keep one
source of truth (see project_purpose_code_decodes_corrected).

Codes verified 2026-07-06 against live experian_enquiry (4.69M rows) and
Mapping Master Appendix I.
"""

import re
from datetime import datetime, timedelta, timezone

# ── Constants ────────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))   # India Standard Time (no DST)


def ist_timestamp():
    """Current timestamp in IST, e.g. '2026-07-07 01:18:46 IST'."""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def ist_compact():
    """Compact IST stamp for worksheet names, e.g. '20260707_011846'."""
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


REFERENCE_DATE = "2026-04-06"   # all age / recency math anchors here
SCORE_MIN      = 300            # Experian V3 floor
SCORE_MAX      = 900            # Experian V3 ceiling
AMOUNT_CAP     = 10_000_000     # ₹1 cr — cap max enquiry amount to dodge outliers


# ── Purpose codes (products) ─────────────────────────────────────────────────
# CORRECTED decode. The template's old "likely" guesses were wrong:
#   7 = Credit Card (was mislabelled "Auto"), 2 = Auto (was "Housing"),
#   14 = Property/Housing (the real housing code, not 2).
# Code 6 "Consumer Search" is a bureau soft-pull, NOT a product -> excluded.
# Reach hints (distinct-mobile counts per code) are NOT stored here — they are
# private business intel. They load at runtime from Streamlit secrets or a
# gitignored reach_hints.json (see load_reach_hints); absent = no hint shown.
PRODUCTS = [
    {"label": "Personal Loan",           "code": 13},
    {"label": "Credit Card",             "code": 7},
    {"label": "Auto Loan",               "code": 2},
    {"label": "Property / Housing Loan", "code": 14},
    {"label": "Two/Three-Wheeler",       "code": 16},
    {"label": "Agriculture Loan",        "code": 1},
    {"label": "Business Loan",           "code": 3},
    {"label": "Other",                   "code": 99},
]
PRODUCT_LABELS = [p["label"] for p in PRODUCTS]
_LABEL_TO_CODE = {p["label"]: p["code"] for p in PRODUCTS}


# ── Member classes (M_SUB_ID) ────────────────────────────────────────────────
# Class code, NOT a unique lender — per-lender suppression is impossible.
MEMBER_CLASSES = [
    {"label": "Private bank / NBFC", "code": "PVT"},
    {"label": "NBFC",                "code": "NBF"},
    {"label": "Public-sector bank",  "code": "PUB"},
    {"label": "Foreign bank",        "code": "FOR"},
    {"label": "Housing Finance Co",  "code": "HFC"},
]
MEMBER_CLASS_LABELS = [m["label"] for m in MEMBER_CLASSES]
_MCLASS_LABEL_TO_CODE = {m["label"]: m["code"] for m in MEMBER_CLASSES}


# ── Score bands ──────────────────────────────────────────────────────────────
# (label, lo, hi, template_quota_field). lo/hi are [lo, hi) score bounds.
# <650 uses SCORE_MIN as its floor so the bucket SQL branch fires (a None lo
# is not handled by the generator's _bucket_sql_expr). NTC = no score at all.
SCORE_BANDS = [
    {"label": "<650",    "lo": SCORE_MIN, "hi": 650,  "field": "bucket_below_650_quota"},
    {"label": "650-699", "lo": 650,       "hi": 700,  "field": "bucket_650_699_quota"},
    {"label": "700-749", "lo": 700,       "hi": 750,  "field": "bucket_700_749_quota"},
    {"label": "750-799", "lo": 750,       "hi": 800,  "field": "bucket_750_799_quota"},
    {"label": "800+",    "lo": 800,       "hi": None,  "field": "bucket_800_plus_quota"},
    {"label": "NTC",     "lo": None,      "hi": None,  "field": "bucket_ntc_quota"},
]
SCORE_BAND_LABELS = [b["label"] for b in SCORE_BANDS]
_BAND_BY_LABEL = {b["label"]: b for b in SCORE_BANDS}


# ── DPD / credit-conduct presets ─────────────────────────────────────────────
# One sales-facing choice expands to a bundle of template filter fields.
# Tune thresholds here if the risk policy changes.
DPD_PRESETS = {
    "Strict": {   # spotless — no missed payment ever, no overdue, no write-off
        "exclude_writeoff": "Yes",
        "max_dpd_30": 0,
        "max_dpd_60": 0,
        "max_dpd_90": 0,
        "max_total_past_due_am": 0,
    },
    "Moderate": {  # no serious RECENT delinquency; tolerates old minor DPD
        "exclude_writeoff": "Yes",
        "max_dpd_90_in_24m": 0,
        "max_dpd_60_in_12m": 0,
        "max_total_past_due_am": 0,
    },
    "Any": {       # no DPD filter at all
        "exclude_writeoff": "No",
    },
}
DPD_PRESET_LABELS = list(DPD_PRESETS.keys())


# ── Recipient / employment enums ─────────────────────────────────────────────
RECIPIENT_TYPES = ["Connector", "DDSA", "DSA", "DST", "NBFC"]  # alphabetical

# (label, enabled). Only Salaried has data today; others are shown-but-disabled.
EMPLOYMENT_TYPES = [
    {"label": "Salaried",      "enabled": True},
    {"label": "Self-employed", "enabled": False},
    {"label": "Both",          "enabled": False},
]
EMPLOYMENT_ENABLED = [e["label"] for e in EMPLOYMENT_TYPES if e["enabled"]]


# ── Validators ───────────────────────────────────────────────────────────────
_PAN_RE    = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE  = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
_MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")


def valid_pan(pan):
    return bool(_PAN_RE.match((pan or "").strip().upper()))


def valid_gstin(gstin):
    """Blank is allowed (GST is optional); a non-blank value must be well-formed."""
    g = (gstin or "").strip().upper()
    return g == "" or bool(_GSTIN_RE.match(g))


def gstin_pan_match(gstin, pan):
    """If a GSTIN is given, its embedded PAN (chars 3-12) must equal the PAN."""
    g = (gstin or "").strip().upper()
    if g == "":
        return True
    return g[2:12] == (pan or "").strip().upper()


def valid_mobile(mobile):
    return bool(_MOBILE_RE.match((mobile or "").strip()))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    return bool(_EMAIL_RE.match((email or "").strip()))


# ── Normalizer & builders ────────────────────────────────────────────────────
def norm_purp(code):
    """Normalize an INQ_PURP_CD for comparison.

    The mart stores codes BOTH zero-padded and unpadded ('7' and '07'), so raw
    string equality drops the padded rows. Match on the integer value instead.
    Returns '' for blank/non-numeric. SQL twin: CAST(inq_purp_cd AS INTEGER).
    """
    try:
        return str(int(str(code).strip()))
    except (TypeError, ValueError):
        return ""


def purpose_codes_csv(labels):
    """Selected product labels -> comma-separated normalized codes, e.g. '13,7'."""
    return ",".join(norm_purp(_LABEL_TO_CODE[l]) for l in labels if l in _LABEL_TO_CODE)


def member_classes_csv(labels):
    """Selected lender-type labels -> comma-separated M_SUB_ID codes, e.g. 'NBF,PVT'."""
    return ",".join(_MCLASS_LABEL_TO_CODE[l] for l in labels if l in _MCLASS_LABEL_TO_CODE)


def band(label):
    """Look up a score band dict by its label."""
    return _BAND_BY_LABEL.get(label)


def dpd_preset_fields(preset):
    """Credit-conduct preset name -> dict of template filter field values."""
    return dict(DPD_PRESETS.get(preset, {}))


# ── Campaign-template transform ──────────────────────────────────────────────
# Ordered exactly like the OI_Campaign_Request_Template Filter Criteria sheet.
TEMPLATE_FIELDS = [
    "recipient_code", "recipient_name", "recipient_type", "batch_label",
    "target_count", "fresh", "ntc_allowed",
    "min_age", "max_age", "min_salary_monthly", "employment_type", "city",
    "min_score", "max_score",
    "bucket_below_650_quota", "bucket_650_699_quota", "bucket_700_749_quota",
    "bucket_750_799_quota", "bucket_800_plus_quota", "bucket_ntc_quota",
    "pan_required", "unique_pan_per_mobile",
    "max_dpd_30", "max_dpd_60", "max_dpd_90",
    "max_dpd_30_in_3m", "max_dpd_30_in_6m", "max_dpd_30_in_12m",
    "max_dpd_60_in_6m", "max_dpd_60_in_12m", "max_dpd_60_in_18m", "max_dpd_60_in_24m",
    "max_dpd_90_in_12m", "max_dpd_90_in_24m",
    "exclude_writeoff", "max_total_past_due_am",
    "max_pl_enq_7d", "max_pl_enq_10d", "max_pl_enq_30d", "max_pl_enq_90d",
    "enq_include_purpose_codes", "enq_exclude_purpose_codes",
    "enq_include_member_classes", "enq_exclude_member_classes",
    "enq_window_days", "enq_max_in_window", "enq_date_from", "enq_date_to",
    "min_enq_amount", "max_enq_amount",
]


def _num(x):
    """Format a number for a template cell: '' for blank, else integer string."""
    if x is None or x == "":
        return ""
    try:
        return str(int(x))
    except (TypeError, ValueError):
        return str(x)


def to_template_values(a):
    """Map a form-answers dict to the campaign-template field values.

    Unset fields stay blank (the generator then skips them). recipient_code /
    batch_label are left blank for the data team to assign at ingestion.
    """
    v = {f: "" for f in TEMPLATE_FIELDS}

    v["recipient_name"] = (a.get("recipient_name") or "").strip()
    v["recipient_type"] = a.get("recipient_type") or ""
    v["target_count"] = _num(a.get("target_count"))
    v["fresh"] = "Yes" if a.get("exclude_previously_sent") else "No"
    v["ntc_allowed"] = "Yes" if a.get("allow_ntc") else "No"

    v["min_age"] = _num(a.get("min_age"))
    v["max_age"] = _num(a.get("max_age"))
    v["min_salary_monthly"] = _num(a.get("min_salary_monthly"))
    v["employment_type"] = a.get("employment_type") or ""
    v["city"] = (a.get("city") or "").strip()

    v["min_score"] = _num(a.get("min_score"))
    v["max_score"] = _num(a.get("max_score"))
    quotas = a.get("quotas") or {}
    for b in SCORE_BANDS:
        q = quotas.get(b["label"])
        if q:
            v[b["field"]] = _num(q)

    v["pan_required"] = "Yes" if a.get("pan_required") else "No"
    v["unique_pan_per_mobile"] = "Yes"

    for k, val in dpd_preset_fields(a.get("credit_conduct") or "Any").items():
        v[k] = str(val)

    v["enq_include_purpose_codes"] = purpose_codes_csv(a.get("products_include") or [])
    v["enq_exclude_purpose_codes"] = purpose_codes_csv(a.get("products_exclude") or [])
    v["enq_include_member_classes"] = member_classes_csv(a.get("lenders_include") or [])
    v["enq_exclude_member_classes"] = member_classes_csv(a.get("lenders_exclude") or [])
    v["enq_window_days"] = _num(a.get("enq_window_days"))
    v["enq_max_in_window"] = _num(a.get("enq_max_in_window"))

    v["min_enq_amount"] = _num(a.get("loan_amount_min"))
    lam = a.get("loan_amount_max")
    v["max_enq_amount"] = _num(min(lam, AMOUNT_CAP)) if lam else ""

    return v


def validate_submission(a):
    """Return a list of human-readable errors (empty = valid)."""
    errs = []
    if not (a.get("recipient_name") or "").strip():
        errs.append("Recipient name is required.")
    if a.get("recipient_type") not in RECIPIENT_TYPES:
        errs.append("Select a recipient type.")
    if not valid_mobile(a.get("recipient_contact")):
        errs.append("Recipient contact must be a 10-digit Indian mobile (starts 6-9).")
    if not valid_email(a.get("recipient_email")):
        errs.append("Recipient email looks invalid.")
    pan = (a.get("recipient_pan") or "").strip()
    gst = (a.get("recipient_gst") or "").strip()
    if not pan and not gst:
        errs.append("Provide a GST or PAN number (GST preferred).")
    else:
        if pan and not valid_pan(pan):
            errs.append("PAN must look like ABCDE1234F.")
        if gst and not valid_gstin(gst):
            errs.append("GST must be a valid 15-char GSTIN.")
        if (pan and gst and valid_pan(pan) and valid_gstin(gst)
                and not gstin_pan_match(gst, pan)):
            errs.append("GST does not embed the given PAN (GSTIN characters 3-12).")

    tc = a.get("target_count")
    if not tc or tc <= 0:
        errs.append("Target count must be a positive number.")

    mn, mx = a.get("min_age"), a.get("max_age")
    if mn and mx and mn > mx:
        errs.append("Min age cannot exceed max age.")

    for s in (a.get("min_score"), a.get("max_score")):
        if s and not (SCORE_MIN <= s <= SCORE_MAX):
            errs.append(f"Scores must be between {SCORE_MIN} and {SCORE_MAX}.")
            break

    bands = a.get("score_bands") or []
    quotas = a.get("quotas") or {}
    if bands:
        total = sum(int(quotas.get(b) or 0) for b in bands)
        if tc and total != tc:
            errs.append(
                f"Score-band quotas add up to {total}, but target count is {tc}. "
                "They must match."
            )
    return errs


def load_reach_hints(secrets=None):
    """Return reach-count hints, or {} if none are available.

    Reach counts are private business intel and are NEVER committed. Source order:
      1. `secrets` dict passed in (e.g. st.secrets['reach_hints']) — deployed app.
      2. gitignored ./reach_hints.json — local dev only.
      3. {} — no hints; the form simply omits the reach labels.

    Shape: {"products": {"<code>": <count>, ...}, "classes": {...}, "bands": {...}}
    """
    if secrets:
        try:
            return dict(secrets)
        except Exception:
            pass
    try:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "reach_hints.json")
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Self-test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Normalizer: padded == unpadded
    assert norm_purp("7") == norm_purp("07") == "7"
    assert norm_purp("2") == norm_purp("02") == "2"
    assert norm_purp("13") == "13"
    assert norm_purp("") == "" and norm_purp(None) == "" and norm_purp("x") == ""

    # Builders
    assert purpose_codes_csv(["Personal Loan", "Credit Card"]) == "13,7"
    assert member_classes_csv(["NBFC", "Private bank / NBFC"]) == "NBF,PVT"

    # Validators
    assert valid_pan("ABCDE1234F") and not valid_pan("ABCDE1234")
    assert valid_mobile("9876543210") and not valid_mobile("1234567890")
    assert valid_gstin("") and valid_gstin("27ABCDE1234F1Z5")
    assert gstin_pan_match("27ABCDE1234F1Z5", "ABCDE1234F")
    assert not gstin_pan_match("27ABCDE1234F1Z5", "ZZZZZ9999Z")

    # Transform + validation
    sample = {
        "recipient_name": "Fast Credit Pvt Ltd", "recipient_type": "NBFC",
        "recipient_contact": "9876543210", "recipient_email": "a@b.com",
        "recipient_pan": "ABCDE1234F", "recipient_gst": "27ABCDE1234F1Z5",
        "target_count": 15000, "exclude_previously_sent": True, "allow_ntc": True,
        "min_age": 23, "max_age": 55, "min_salary_monthly": 50000,
        "employment_type": "Salaried",
        "score_bands": ["750-799", "800+"],
        "quotas": {"750-799": 8000, "800+": 7000},
        "products_include": ["Personal Loan", "Credit Card"],
        "lenders_exclude": ["Housing Finance Co"],
        "credit_conduct": "Strict", "pan_required": True,
        "loan_amount_max": 50_000_000,   # above the 1cr cap -> should clamp
    }
    assert validate_submission(sample) == [], validate_submission(sample)
    tv = to_template_values(sample)
    assert tv["fresh"] == "Yes" and tv["ntc_allowed"] == "Yes"
    assert tv["enq_include_purpose_codes"] == "13,7"
    assert tv["enq_exclude_member_classes"] == "HFC"
    assert tv["bucket_750_799_quota"] == "8000" and tv["bucket_800_plus_quota"] == "7000"
    assert tv["exclude_writeoff"] == "Yes" and tv["max_dpd_90"] == "0"
    assert tv["max_enq_amount"] == str(AMOUNT_CAP)   # clamped to 1cr
    # quota mismatch is caught
    bad = dict(sample, quotas={"750-799": 1, "800+": 1})
    assert any("add up to" in e for e in validate_submission(bad))
    # bad PAN caught
    assert any("PAN" in e for e in validate_submission(dict(sample, recipient_pan="x")))
    # GST or PAN: neither -> error; GST-only or PAN-only -> ok
    assert any("GST or PAN" in e
               for e in validate_submission(dict(sample, recipient_pan="", recipient_gst="")))
    assert validate_submission(dict(sample, recipient_pan="")) == []          # GST only
    assert validate_submission(dict(sample, recipient_gst="")) == []          # PAN only

    print("mappings.py self-test: ALL PASS")
    print(f"  products: {len(PRODUCTS)}  classes: {len(MEMBER_CLASSES)}  "
          f"bands: {len(SCORE_BANDS)}  dpd presets: {DPD_PRESET_LABELS}")
    print(f"  reference_date={REFERENCE_DATE}  amount_cap={AMOUNT_CAP:,}")
