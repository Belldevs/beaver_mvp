"""Run this to test your AI keys:   python check_ai.py
Tests Gemini and the backup provider separately, shows the exact error, and lists the model names your keys can use."""
import os
from dotenv import load_dotenv

load_dotenv()
import httpx
import ai

SYSTEM = 'Reply with JSON only.'
USER = 'Return {"ok": true}'


def try_provider(label, fn, key_name):
    print(f"\n--- {label} ---")
    if not os.getenv(key_name):
        print(f"SKIPPED: {key_name} is empty or missing in .env")
        return False
    try:
        print("WORKING. Reply was:", fn(SYSTEM, USER).strip()[:120])
        return True
    except ai.AIUnavailable as e:
        print("FAILED:", e)
    except Exception as e:
        print("FAILED (network?):", repr(e))
    return False


def list_gemini_models():
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                  headers={"x-goog-api-key": os.getenv("GEMINI_API_KEY", "")}, timeout=30)
    if r.status_code != 200:
        print("  could not list models:", r.status_code, r.text[:200])
        return
    names = sorted(m["name"].split("/")[-1] for m in r.json().get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
                   and not any(x in m["name"] for x in ("image", "tts", "live", "audio", "robotics", "omni")))
    print("  Gemini models your key can use (put one in GEMINI_MODEL):")
    for n in names:
        print("   ", n)


def list_backup_models():
    base = os.getenv("BACKUP_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {os.getenv('BACKUP_API_KEY', '')}"}, timeout=30)
    if r.status_code != 200:
        print("  could not list models:", r.status_code, r.text[:200])
        return
    print("  Backup models your key can use (put one in BACKUP_MODEL):")
    for n in sorted(m["id"] for m in r.json().get("data", [])):
        print("   ", n)


print("Gemini model:", os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
if os.getenv("GEMINI_API_KEY") and not try_provider("Gemini", ai._gemini, "GEMINI_API_KEY"):
    list_gemini_models()
elif not os.getenv("GEMINI_API_KEY"):
    try_provider("Gemini", ai._gemini, "GEMINI_API_KEY")

print("\nBackup base URL:", os.getenv("BACKUP_BASE_URL", "https://api.groq.com/openai/v1"))
print("Backup model:", os.getenv("BACKUP_MODEL", "llama-3.1-8b-instant"))
if os.getenv("BACKUP_API_KEY") and not try_provider("Backup (Groq)", ai._backup, "BACKUP_API_KEY"):
    list_backup_models()
elif not os.getenv("BACKUP_API_KEY"):
    try_provider("Backup (Groq)", ai._backup, "BACKUP_API_KEY")
