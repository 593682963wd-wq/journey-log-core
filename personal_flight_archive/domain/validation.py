from __future__ import annotations

import re
from datetime import datetime
from typing import Any


FORBIDDEN_FIELD_MARKERS = (
    "身份证",
    "护照",
    "passport",
    "id_card",
    "身份证号",
    "ticket_number",
    "票号",
    "银行卡",
    "bank_card",
    "payment",
    "支付",
    "验证码",
    "verification_code",
    "登机牌条码",
    "boarding_pass_barcode",
    "二维码",
    "qrcode",
    "api_key",
    "apikey",
    "cookie",
    "password",
    "手机号",
    "手机号码",
    "email",
    "邮箱",
    "联系方式",
)

FORBIDDEN_TEXT_MARKERS = FORBIDDEN_FIELD_MARKERS


class ValidationError(ValueError):
    pass


class DuplicateFlightError(ValidationError):
    pass


class AmbiguousAirportError(ValidationError):
    def __init__(self, field: str, query: str, candidates: list[dict[str, Any]]):
        super().__init__(f"{field} 机场“{query}”存在多个候选，请选择 ICAO")
        self.field = field
        self.query = query
        self.candidates = candidates


class UnknownAirportError(ValidationError):
    def __init__(self, field: str, query: str):
        super().__init__(f"{field} 机场“{query}”未能解析，请使用 ICAO 或先同步机场目录")
        self.field = field
        self.query = query


def reject_forbidden_field_names(payload: dict[str, Any]) -> None:
    for key in payload:
        normalized = str(key).strip().lower()
        if any(marker.lower() in normalized for marker in FORBIDDEN_FIELD_MARKERS):
            raise ValidationError(f"不允许保存敏感字段：{key}")


def reject_forbidden_text(value: object, *, field: str) -> None:
    text = str(value or "")
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_TEXT_MARKERS):
        raise ValidationError(f"{field} 可能包含禁止保存的敏感信息")


def normalize_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError("飞行日期不能为空")
    text = text.replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValidationError("飞行日期必须是 YYYY-MM-DD")


def normalize_local_datetime(value: object, *, fallback_date: str | None = None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(timespec="minutes")
    text = str(value).strip().replace("/", "-")
    if len(text) == 5 and ":" in text and fallback_date:
        text = f"{fallback_date}T{text}"
    text = text.replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%H:%M":
                if not fallback_date:
                    return None
                return f"{fallback_date}T{parsed.strftime('%H:%M')}"
            if fmt == "%Y-%m-%d":
                return parsed.date().isoformat() + "T00:00"
            return parsed.replace(tzinfo=None).isoformat(timespec="minutes")
        except ValueError:
            continue
    raise ValidationError("时间必须是 YYYY-MM-DDTHH:MM 或 HH:MM")


def normalize_tags(value: object) -> list[str]:
    if value in (None, ""):
        return []
    values = value if isinstance(value, list) else re.split(r"[,，;；\s]+", str(value))
    result = []
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        reject_forbidden_text(text, field="标签")
        if len(text) > 40:
            raise ValidationError("单个标签不能超过 40 个字符")
        result.append(text)
    return list(dict.fromkeys(result))[:20]


def normalize_flight_number(value: object) -> str | None:
    if value in (None, ""):
        return None
    result = re.sub(r"\s+", "", str(value).strip().upper())
    if not re.fullmatch(r"[A-Z0-9-]{2,12}", result):
        raise ValidationError("航班号格式不正确")
    return result
