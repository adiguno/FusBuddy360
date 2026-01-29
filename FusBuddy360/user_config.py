import json
import os
from typing import Any, Dict


def _base_dir() -> str:
    """
    Returns a per-user config directory for FusBuddy360, outside the repo.
    """
    # Prefer OS-specific app data if available, otherwise fall back to home.
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.getenv("APPDATA", home)
        return os.path.join(base, "FusBuddy360")
    # macOS / Linux
    return os.path.join(home, "Library", "Application Support", "FusBuddy360")


def _config_path() -> str:
    return os.path.join(_base_dir(), "config.json")


def load_config() -> Dict[str, Any]:
    """
    Load config JSON. Returns {} if missing or invalid.
    """
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """
    Save config JSON, creating the directory if needed.
    """
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_openai_api_key() -> str | None:
    """
    Read OpenAI API key from config (user-level).
    """
    cfg = load_config()
    key = cfg.get("openai_api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def set_openai_api_key(key: str) -> None:
    """
    Store OpenAI API key in the user config file.
    """
    cfg = load_config()
    cfg["openai_api_key"] = key.strip()
    save_config(cfg)


def get_gemini_api_key() -> str | None:
    """
    Read Google Gemini API key from config (user-level).
    """
    cfg = load_config()
    key = cfg.get("gemini_api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def set_gemini_api_key(key: str) -> None:
    """
    Store Google Gemini API key in the user config file.
    """
    cfg = load_config()
    cfg["gemini_api_key"] = key.strip()
    save_config(cfg)


def get_llm_provider() -> str:
    """
    Get preferred LLM provider from config. Returns 'openai', 'gemini', or 'auto'.
    Defaults to 'gemini' which tries Gemini first, then OpenAI.
    """
    cfg = load_config()
    provider = cfg.get("llm_provider", "gemini")
    if provider in ["openai", "gemini", "auto"]:
        return provider
    return "gemini"


