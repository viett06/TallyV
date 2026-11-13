"""Prepare privacy-filtered case text and HR rules; no inference or I/O."""

import re
import unicodedata
from itertools import groupby

from app.core.attendance import CLASSIFICATION_KEYWORDS, DEFAULT_RULE_DESCRIPTIONS, PUNCH_IN, PUNCH_OUT

_TERMS = frozenset(
    """
    bao bam bat bo buoc ca cai can cap chua cham check-in check-out cho chuyen co cong da dang
    dau den dieu di dien doi dong du duoc duyet ghi gio gui he hien hoac hong hu huy in ket
    khai khong loi luc lai lam mat may man minh mo muon ngay nghi nhan nhung noi nop out phai
    phep phan phat qua quen quet ra sang sau som sai sua su the thi thieu thuc thua thong
    thoat thay them thoi to trinh trong truoc truc trung tu vao ve vang van xac xong
    anh nen goc dia diem benh vien tai khu vuc sanh phong bien cua quay vi tri so trung mau
    approved attendance camera device error failed forgot leave recognized recorded offline online
    system timeout disconnect disconnected
    """.split()
) | frozenset(word for phrases in CLASSIFICATION_KEYWORDS.values() for phrase in phrases for word in phrase.split())
_DIRECT_IDENTIFIER = re.compile(
    r"https?://\S+|www\.\S+|[^\s@]+@[^\s@]+|(?<!\w)\+?\d[\d .()/-]{5,}\d(?!\w)",
    re.IGNORECASE,
)


class UnsafeAssessmentPolicy(ValueError):
    """An HR rule contains case identifiers or direct identifying information."""


class RuleSnapshotChanged(ValueError):
    """The HR rule snapshot changed during visual assessment."""


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    return "".join(
        " " if c.isspace() else c for c in text if c.isspace() or not unicodedata.category(c).startswith(("M", "C"))
    )


def _identity_pattern(data: dict[str, str], *, include_name_parts: bool = False) -> re.Pattern:
    parts = []
    for key in ("name", "employee_id", "code", "department"):
        value = _fold(data.get(key, ""))
        words = re.findall(r"[^\W_]+", value)
        if key in {"employee_id", "code"}:
            words = list("".join(words))
        if words:
            parts.append(r"[\W_]*".join(map(re.escape, words)))
            if key == "name" and include_name_parts:
                parts.extend(map(re.escape, words))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts or [r"(?!)"]) + r")(?!\w)")


def _case_text(value: str, identity: re.Pattern) -> str:
    folded = _DIRECT_IDENTIFIER.sub(" zzredactedzz ", _fold(value[:12000]))
    masked = identity.sub(" zzredactedzz ", folded)
    tokens = re.findall(r"[^\W_]+(?:-[^\W_]+)?", masked)
    parts = []
    for allowed, group in groupby(tokens, key=_TERMS.__contains__):
        parts.append(" ".join(group) if allowed else "[DA_AN]")
    return " ".join(parts)[:1400]


def _policy_text(value: str, identity: re.Pattern) -> str:
    folded = _fold(value)
    if _DIRECT_IDENTIFIER.search(folded) or identity.search(folded):
        raise UnsafeAssessmentPolicy("Identifying data in HR policy")
    return value


def prepare_input(data: dict[str, str], policies: dict[str, dict], image_count: int) -> dict:
    identity = _identity_pattern(data)
    case_identity = _identity_pattern(data, include_name_parts=True)
    rules = []
    for category, policy in {**policies, "UNKNOWN": policies.get("UNKNOWN", {})}.items():
        description = policy.get("description") or DEFAULT_RULE_DESCRIPTIONS.get(category, "")
        rules.append(
            {
                "category": category,
                "description": _policy_text(description, identity),
                "require_evidence": policy.get("require_evidence", True),
                "require_shift": policy.get("require_shift", True),
                "require_punch": policy.get("require_punch", False),
            }
        )
    return {
        "case": {
            "explanation_signals": _case_text(data["explanation"], case_identity),
            "has_shift": bool(data.get("shift")),
            "missing_punch": {PUNCH_IN: "IN", PUNCH_OUT: "OUT"}.get(data.get("punch")),
            "evidence": [{"evidence_ref": index} for index in range(1, image_count + 1)],
        },
        "hr_rules": rules,
    }
