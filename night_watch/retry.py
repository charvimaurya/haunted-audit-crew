"""Reads the Retry-After header from a 429 (rate limit) reply."""

# The longest wait we are willing to honour, in seconds.
MAX_RETRY_AFTER_SECONDS = 120


def parse_retry_after(value: str | None) -> int | None:
    """Return the wait in seconds, or None if the value cannot be trusted.

    Only plain ASCII digits are accepted, and the number must be 0 to 120.
    Missing, empty, negative, decimal, padded, non-ASCII and too-large
    values all give None.
    """
    # A missing header or a non-text value is unusable.
    if not isinstance(value, str):
        return None

    # Digits 0-9 only. str.isdigit() is too loose (it accepts "²" and
    # other Unicode digits), so check each character directly.
    if value == "" or any(ch not in "0123456789" for ch in value):
        return None

    # Skip leading zeros first, so a very long string of zeros is still
    # handled safely and a huge number is rejected without being converted.
    trimmed = value.lstrip("0")
    if len(trimmed) > 3:
        return None

    seconds = int(trimmed) if trimmed else 0
    if seconds > MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds
