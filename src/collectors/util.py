"""Shared helpers for collectors: HTML stripping and lenient date parsing."""
from __future__ import annotations

import html as html_module
import math
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser


def strip_html(text: str) -> str:
    if not text:
        return ""
    unescaped = html_module.unescape(text)
    try:
        soup = BeautifulSoup(unescaped, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return unescaped


def parse_date(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return dateutil_parser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        return None


def clean_number(value):
    """NaN/None-safe passthrough for numeric fields coming from pandas rows."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
