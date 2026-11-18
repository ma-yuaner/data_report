"""Cabin input normalization; ERP reference text must not use this parser."""
import re


def cabin_values(value) -> list[str]:
    return list(dict.fromkeys(item.strip().upper() for item in re.split(r"[,，/／|;；]+", str(value or "")) if item.strip()))
