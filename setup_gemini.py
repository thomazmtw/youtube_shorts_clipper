#!/usr/bin/env python3
"""Interactive setup helper for Google Gemini API connection."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gemini_client


def main():
    print("=" * 65)
    print("  GOOGLE GEMINI API CONNECTION SETUP")
    print("=" * 65)
    print("\nGoogle Gemini provides optional cloud visual analysis for:")
    print(" - Detecting speakers and action framing in videos")
    print(" - Emotional reaction and facial expression analysis")
    print(" - Visual hook moments and punch-in recommendations")
    print("\n💡 Get your FREE Gemini API key from:")
    print("   👉 https://aistudio.google.com/app/apikey")
    print("=" * 65)

    current_key = gemini_client.get_api_key()
    if current_key:
        masked = current_key[:6] + "..." + current_key[-4:] if len(current_key) > 10 else "***"
        print(f"\nCurrent configured key: {masked}")
        choice = input("Do you want to test the current key (T), update it (U), or clear it (C)? [T/u/c]: ").strip().lower()
        if choice in ("c", "clear"):
            gemini_client.clear_api_key()
            print("✅ Gemini API key cleared.")
            return
        elif choice not in ("u", "update"):
            print("\nTesting current Gemini connection...")
            ok, msg = gemini_client.test_connection()
            if ok:
                print(f"🎉 SUCCESS: {msg}")
            else:
                print(f"❌ FAILED: {msg}")
            return

    # Prompt for new key
    if len(sys.argv) > 1 and sys.argv[1].strip():
        new_key = sys.argv[1].strip()
    else:
        new_key = input("\nEnter your Gemini API key (e.g. AIzaSy...): ").strip()

    if not new_key:
        print("⚠️ No key entered. Aborting setup.")
        return

    print("\nTesting connection with Google Gemini (gemini-2.0-flash)...")
    ok, msg = gemini_client.test_connection(api_key=new_key, model="gemini-2.0-flash")
    if not ok:
        # Fallback test with gemini-1.5-flash
        ok_fb, msg_fb = gemini_client.test_connection(api_key=new_key, model="gemini-1.5-flash")
        if ok_fb:
            ok, msg = ok_fb, msg_fb

    if ok:
        print(f"🎉 CONNECTION VERIFIED: {msg}")
        gemini_client.save_api_key(new_key)
        print("💾 Saved key to .gemini_config.json")

        # Windows User environment variable option
        if sys.platform.startswith("win"):
            try:
                import subprocess
                cmd = f'[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "{new_key}", "User")'
                subprocess.run(["powershell", "-Command", cmd], capture_output=True)
                print("🔒 Also saved to Windows User Environment (GEMINI_API_KEY).")
            except Exception:
                pass

        print("\n✅ Setup complete! You can now use 'Hybrid (Ollama + Gemini)' or 'Gemini Only' mode.")
    else:
        print(f"\n❌ Connection failed: {msg}")
        save_anyway = input("Save key anyway? [y/N]: ").strip().lower()
        if save_anyway == "y":
            gemini_client.save_api_key(new_key)
            print("💾 Saved key to .gemini_config.json")


if __name__ == "__main__":
    main()
