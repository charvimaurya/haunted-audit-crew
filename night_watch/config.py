"""Read and clean the Haunted Audit API address for Night Watch.

The address comes from the environment variable HA_API_URL. No secrets
and no real data live in this file.
"""

import os

# Used when HA_API_URL is not set or is blank.
DEFAULT_API_URL = "http://127.0.0.1:8000"

# The only address styles we accept.
_ALLOWED_PREFIXES = ("http://", "https://")


class ConfigError(ValueError):
    """Raised when HA_API_URL is set to something we cannot use."""


def normalize_api_url(raw: str | None) -> str:
    """Return a clean API address.

    - None, empty or whitespace-only text gives the default address.
    - Whitespace around the text and any trailing slashes are removed,
      so request URLs never contain a double slash after the host.
    - Anything not starting with http:// or https:// raises ConfigError.
    """
    if raw is None:
        return DEFAULT_API_URL

    text = raw.strip()
    if not text:
        return DEFAULT_API_URL

    # Remove trailing slashes and any whitespace mixed in with them,
    # for example "http://host /  /".
    previous = None
    while text != previous:
        previous = text
        text = text.rstrip("/").rstrip()

    if not text.startswith(_ALLOWED_PREFIXES):
        raise ConfigError(
            "HA_API_URL is invalid: it must begin with http:// or https://"
        )
    return text


def read_api_url(environ=os.environ) -> str:
    """Read HA_API_URL from the environment and clean it."""
    return normalize_api_url(environ.get("HA_API_URL"))
