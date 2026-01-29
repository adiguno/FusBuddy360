import json
import os
from typing import Any, Dict

from . import user_config
try:
    # Fusion add-in logging utility (shows in Fusion Text Commands when DEBUG is enabled)
    from .lib import fusionAddInUtils as futil  # type: ignore[import]
except Exception:
    futil = None  # type: ignore[assignment]

# Try to import requests (common in Python environments), fall back to urllib
try:
    import requests  # type: ignore[import]
    HTTP_LIB = "requests"
except Exception:
    try:
        import urllib.request
        import urllib.parse
        HTTP_LIB = "urllib"
    except Exception:
        HTTP_LIB = None
        if futil:
            futil.log("[FusBuddy360] Neither requests nor urllib available for HTTP calls")


def _summarise_selection(selection: Dict[str, Any]) -> str:
    count = selection.get("count", 0)
    types = selection.get("types", {}) or {}
    if not count:
        return "You don’t have anything selected yet."

    parts = [f"You have {count} item(s) selected."]
    if types:
        type_bits = [f"{v}× {k.split('::')[-1]}" for k, v in types.items()]
        parts.append("Types: " + ", ".join(type_bits))
    return " ".join(parts)


def _build_structured_text(user_text: str, ctx: Dict[str, Any]) -> str:
    """
    Fallback, non-LLM coach output that still follows the desired structure:
    - what we’re going to do
    - numbered steps
    - tips / common mistakes
    - selection fallback
    """
    doc_name = (ctx.get("document") or {}).get("name") or "your current design"
    ws_name = (ctx.get("workspace") or {}).get("name") or "your current workspace"
    sel_summary = _summarise_selection(ctx.get("selection") or {})

    lines = []
    lines.append(f"**Goal (from you):** {user_text}")
    lines.append("")
    lines.append(f"**Where we are:** Working in {ws_name} on *{doc_name}*.")
    lines.append(sel_summary)
    lines.append("")
    lines.append("**What we’re going to do next (generic template):**")
    lines.append("1. Identify which geometry or feature this question refers to (use the selection to be explicit).")
    lines.append("2. Locate the appropriate tool in Fusion’s UI (toolbar panel or right‑click menu).")
    lines.append("3. Adjust the key inputs (distance/angle/feature count/etc.) while watching the preview.")
    lines.append("4. Confirm the operation and inspect the result from a few camera angles.")
    lines.append("")
    lines.append("**Tips / common mistakes:**")
    lines.append("- Make sure you are in the correct workspace for the tool you expect (e.g. Solid vs Surface).")
    lines.append("- Select only the edges/faces you actually want to affect before running modify commands.")
    lines.append("- If a command is greyed out, check that the right type of object is active (body vs component vs sketch).")
    lines.append("")
    lines.append("If this doesn’t match what you’re trying to do, try re‑asking with a bit more detail about the feature or share what you currently have selected.")
    return "\n".join(lines)


def _detect_api_provider() -> tuple[str | None, str]:
    """
    Detect which API provider to use based on available keys and config.
    Returns: (api_key, provider_name) where provider_name is 'openai' or 'gemini'
    Defaults to Gemini if both are available.
    """
    # Check config for preferred provider
    provider_pref = user_config.get_llm_provider()
    
    # Try Gemini first if auto or explicit (Gemini is now the default)
    if provider_pref in ["auto", "gemini"]:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("FUSBUDDY360_GEMINI_API_KEY")
        if not api_key:
            api_key = user_config.get_gemini_api_key()
        if api_key:
            return (api_key, "gemini")
    
    # Try OpenAI if auto or explicit
    if provider_pref in ["auto", "openai"]:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FUSBUDDY360_OPENAI_API_KEY")
        if not api_key:
            api_key = user_config.get_openai_api_key()
        if api_key:
            return (api_key, "openai")
    
    return (None, "none")


def _call_openai(api_key: str, system_msg: str, user_content: Any, screenshot_b64: str | None) -> str | None:
    """Call OpenAI API (supports vision with gpt-4o-mini)."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # Choose model based on whether we have a screenshot
    model = "gpt-4o-mini" if screenshot_b64 else "gpt-4o-mini"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
    }
    
    try:
        if HTTP_LIB == "requests":
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
        else:  # urllib
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        
        if result.get("choices") and len(result["choices"]) > 0:
            content = result["choices"][0].get("message", {}).get("content", "")
            if content:
                if futil:
                    futil.log(f"[FusBuddy360] OpenAI API call succeeded, got {len(content)} chars")
                return content
        return None
    except Exception as e:
        if futil:
            futil.log(f"[FusBuddy360] OpenAI API call failed: {e}")
        return None


def _call_gemini(api_key: str, system_msg: str, user_text: str, screenshot_b64: str | None) -> str | None:
    """Call Google Gemini API using gemini-3-flash-preview."""
    model = "gemini-3-flash-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    headers = {
        "Content-Type": "application/json",
    }
    
    # Build contents array for Gemini
    contents = []
    
    # System instruction goes in the first user message
    full_user_text = f"{system_msg}\n\n{user_text}"
    
    if screenshot_b64:
        # Gemini uses inline_data for images
        parts = [
            {"text": full_user_text},
            {
                "inline_data": {
                    "mime_type": "image/png",
                    "data": screenshot_b64,
                }
            }
        ]
    else:
        parts = [{"text": full_user_text}]
    
    contents.append({"parts": parts})
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
        }
    }
    
    try:
        if HTTP_LIB == "requests":
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
        else:  # urllib
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        
        # Extract content from Gemini response
        if result.get("candidates") and len(result["candidates"]) > 0:
            candidate = result["candidates"][0]
            if candidate.get("content") and candidate["content"].get("parts"):
                text_parts = [p.get("text", "") for p in candidate["content"]["parts"] if p.get("text")]
                content = "".join(text_parts)
                if content:
                    if futil:
                        futil.log(f"[FusBuddy360] Gemini API call succeeded, got {len(content)} chars")
                    return content
        return None
    except Exception as e:
        if futil:
            futil.log(f"[FusBuddy360] Gemini API call failed: {e}")
        return None


def _call_llm(user_text: str, ctx: Dict[str, Any]) -> str | None:
    """
    Optional: call an LLM (OpenAI or Gemini) if HTTP library is available and an API key is configured.
    Returns None if not available or if anything fails, so the caller can fall back.
    """
    if HTTP_LIB is None:
        if futil:
            futil.log("[FusBuddy360] No HTTP library available (needs requests or urllib)")
        return None

    # Detect which API provider to use
    api_key, provider = _detect_api_provider()
    if not api_key:
        if futil:
            futil.log("[FusBuddy360] No API key found (checked OpenAI and Gemini)")
        return None

    # Never log the full key. Log a masked preview to confirm it was found.
    if futil:
        preview = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 11 else "***"
        futil.log(f"[FusBuddy360] Using {provider.upper()} API key: {preview}")

    # Keep the context small in the prompt.
    compact_ctx = {
        "document": ctx.get("document"),
        "workspace": ctx.get("workspace"),
        "selection": ctx.get("selection"),
        "design": ctx.get("design"),
    }

    # If a screenshot is present, we'll attach it as an image to the user message.
    screenshot = (ctx.get("screenshot") or {}) if isinstance(ctx, dict) else {}
    screenshot_b64 = screenshot.get("base64")

    system_msg = (
        "You are FusBuddy360, a friendly and helpful Fusion 360 learning coach. "
        # "You always respond with:\n"
        # "1) A short paragraph titled 'What we're going to do'\n"
        # "2) A numbered list of clear steps in Fusion UI terms\n"
        # "3) A short 'Common mistakes / tips' section\n"
        # "4) If the selection looks empty or irrelevant, explicitly ask the user to select the right geometry first.\n"
        # "5) When an image of the viewport is provided, use it as visual context to better understand geometry, orientation, and possible tools, "
        # "but never guess about dimensions that are not visible.\n"
        "Provide a concise summary of the user's request.\n"
        "And provide a numbered list of clear steps in Fusion UI terms to help the user.\n"
        "When an image of the viewport is provided, use it as visual context to better understand user intent, geometry, and orientation.\n"
    )

    user_prompt_text = (
        "User question:\n"
        f"{user_text}\n\n"
        "Current context (JSON):\n"
        f"{json.dumps(compact_ctx, indent=2)}"
    )

    # Call the appropriate API
    if provider == "openai":
        # Build user content for OpenAI; if we have a screenshot, send text + image parts.
        if screenshot_b64:
            user_content = [
                {"type": "text", "text": user_prompt_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                    },
                },
            ]
        else:
            user_content = user_prompt_text
        return _call_openai(api_key, system_msg, user_content, screenshot_b64)
    
    elif provider == "gemini":
        return _call_gemini(api_key, system_msg, user_prompt_text, screenshot_b64)
    
    return None


def generate_response(user_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Public API used by the palette code.
    Returns a dict with at least: { 'text': '...' }.
    """
    # Try LLM first if available.
    llm_text = _call_llm(user_text, ctx)
    if llm_text:
        return {"text": llm_text}

    # Fallback to structured template.
    return {"text": "rip"}


