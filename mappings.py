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
RECIPIENT_TYPES = ["NBFC", "DSA", "Connector", "DDSA", "DST"]

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

    print("mappings.py self-test: ALL PASS")
    print(f"  products: {len(PRODUCTS)}  classes: {len(MEMBER_CLASSES)}  "
          f"bands: {len(SCORE_BANDS)}  dpd presets: {DPD_PRESET_LABELS}")
    print(f"  reference_date={REFERENCE_DATE}  amount_cap={AMOUNT_CAP:,}")
