"""
BrowserMind — Native Authentication Portal
=============================================
Instead of launching a Playwright browser which triggers Google's ML bot detection,
this script simply launches your actual Google Chrome in an isolated "Persistent Profile".
You log in manually through normal Chrome, and then BrowserMind uses that exact profile.
"""
import os
import sys
import subprocess
from pathlib import Path

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"C:\Users\mg\.browsermind\chrome_profile"

def run_auth_portal():
    print("=" * 55)
    print("  BrowserMind — Native Authentication Portal")
    print("=" * 55)
    print("\n[INFO] Launching your REAL Google Chrome.")
    print("[INFO] This isolated profile will store your login session securely.")
    print("[INFO] Please log into your Google, LinkedIn, Twitter, etc.")
    print("[INFO] Close ALL Chrome windows when you are finished to save the state.\n")

    # Create directory if it doesn't exist
    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    # Launch native Chrome in a subprocess and wait for it to close
    print("[ACTIVE] Waiting for you to finish your logins and close Chrome...")
    try:
        process = subprocess.Popen(
            [CHROME_PATH, f"--user-data-dir={PROFILE_DIR}", "--no-first-run", "--start-maximized", "https://accounts.google.com"]
        )
        process.wait()
    except KeyboardInterrupt:
        print("\n[INFO] User interrupted.")
    except Exception as e:
        print(f"[ERROR] Failed to launch Chrome: {e}")

    print("\n[SUCCESS] Profile saved. You can now start the Expert Marathon.")

if __name__ == "__main__":
    run_auth_portal()
