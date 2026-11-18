"""Ollama Local AI Client for Hybrid Video Clipper.

Handles communication with a local Ollama server:
- Server availability check & model discovery.
- Vision capability detection.
- Structured JSON output with automatic retries and JSON repair.
- Offline resilience and clear setup guidance.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ollama_client")

DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Vision-capable model identifiers
VISION_KEYWORDS = {
    "vision", "llava", "moondream", "bakllava", "minicpm-v", "cogvlm",
    "llama3.2-vision", "qwen2-vl", "internvl",
}

# Recommended models in order of preference
RECOMMENDED_MODELS = [
    "llama3.2:latest",
    "llama3.2",
    "llama3.1",
    "mistral",
    "qwen2.5:3b",
    "qwen2.5:7b",
    "phi3",
    "gemma2",
]


def is_ollama_installed() -> bool:
    """Return True if the ollama CLI binary exists or Ollama service is reachable."""
    if shutil.which("ollama"):
        return True
    return is_ollama_running()


def is_ollama_running(host: str = DEFAULT_OLLAMA_HOST, timeout: float = 2.0) -> bool:
    """Ping Ollama API to see if service is alive and listening."""
    url = f"{host.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShortsClipper/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_local_models(host: str = DEFAULT_OLLAMA_HOST, timeout: float = 3.0) -> List[str]:
    """Return list of locally downloaded model names from Ollama."""
    url = f"{host.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShortsClipper/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            names = [m.get("name") for m in models if m.get("name")]
            return names
    except Exception as e:
        logger.debug("Failed to list Ollama models: %s", e)
        return []


def is_vision_model(model_name: str) -> bool:
    """Check if model name indicates multimodal / visual capability."""
    name_lower = model_name.lower()
    return any(k in name_lower for k in VISION_KEYWORDS)


def get_best_available_model(host: str = DEFAULT_OLLAMA_HOST) -> Optional[str]:
    """Find the best installed model for video directing."""
    models = list_local_models(host)
    if not models:
        return None

    # Check against recommended models
    for rec in RECOMMENDED_MODELS:
        for m in models:
            if m == rec or m.startswith(rec + ":") or m.startswith(rec.split(":")[0]):
                return m

    # Fallback to the first available model
    return models[0]


def repair_json(text: str) -> Optional[dict]:
    """Extract and repair JSON from potentially noisy LLM response."""
    if not text:
        return None

    # 1. Direct parse attempt
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip Markdown code fences e.g. ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find outer-most curly braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        cand = text[start:end + 1]
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            # Try cleaning trailing commas: ,] -> ] and ,} -> }
            cleaned = re.sub(r",\s*([\]}])", r"\1", cand)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    return None


def generate_chat_json(
    model: str,
    messages: List[Dict[str, str]],
    schema: Optional[Dict[str, Any]] = None,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = 0.2,
    max_retries: int = 2,
    timeout: float = 90.0,
) -> Tuple[Optional[dict], Optional[str]]:
    """Send chat messages to Ollama requesting structured JSON.

    Returns (parsed_json_dict, error_message).
    """
    url = f"{host.rstrip('/')}/api/chat"

    # Instruct model to respond with JSON only
    sys_content = (
        "You are an expert AI Video Editor and Director. "
        "You MUST respond ONLY with a valid, parseable JSON object matching the requested schema. "
        "Do not include any introductory remarks, markdown prose or conversational text."
    )

    enriched_messages = [{"role": "system", "content": sys_content}]
    for m in messages:
        enriched_messages.append(m)

    payload = {
        "model": model,
        "messages": enriched_messages,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ShortsClipper/2.0",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))

            content = resp_data.get("message", {}).get("content", "")
            parsed = repair_json(content)

            if parsed and isinstance(parsed, dict):
                # Verify basic schema requirement if specified
                if schema and "required" in schema:
                    missing = [k for k in schema["required"] if k not in parsed]
                    if missing:
                        msg = f"Response missing required keys: {missing}"
                        logger.warning(msg)
                        if attempt < max_retries:
                            payload["messages"].append({
                                "role": "user",
                                "content": f"ERROR: The JSON was missing required fields: {missing}. Provide the complete JSON strictly conforming to schema."
                            })
                            continue
                return parsed, None

            # If JSON parsing failed, ask model to correct it
            last_error = f"Model returned invalid JSON: {content[:150]}"
            if attempt < max_retries:
                payload["messages"].append({
                    "role": "user",
                    "content": "ERROR: Your output was not valid JSON. Return ONLY the valid JSON object with matching brackets and no surrounding markdown."
                })
        except urllib.error.URLError as e:
            return None, f"Ollama connection error ({host}): {e.reason}"
        except Exception as e:
            last_error = f"Ollama request error: {e}"

    return None, last_error


def get_installation_instructions() -> str:
    """Return friendly markdown instructions for installing Ollama and recommended models."""
    return (
        "### How to Install and Run Ollama for AI Video Editing\n\n"
        "Ollama allows you to run high-speed local AI models on your own machine without "
        "any subscriptions or API keys.\n\n"
        "1. **Download & Install Ollama**:\n"
        "   - Visit: https://ollama.com/download\n"
        "   - Run the Windows installer.\n\n"
        "2. **Download a Recommended Model**:\n"
        "   Open PowerShell or Command Prompt and run:\n"
        "   ```bash\n"
        "   ollama pull llama3.2\n"
        "   ```\n"
        "   *(3B parameters — fast, lightweight, and excels at structured JSON video directing)*\n\n"
        "   *Alternative models:*\n"
        "   - `ollama pull mistral` (7B — powerful storytelling & narrative understanding)\n"
        "   - `ollama pull qwen2.5` (7B — top-tier structured planning)\n\n"
        "3. **Ensure Ollama is Running**:\n"
        "   Make sure the Ollama icon is visible in your Windows System Tray, or run `ollama serve`.\n"
        "   Then click **'Refresh Models'** in the Shorts Clipper app.\n"
    )
