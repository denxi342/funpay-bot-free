import sys
import os
import time

def check():
    print("--- STARTING SYSTEM CHECK ---")
    
    try:
        from config import GOLDEN_KEY, WORK_START_HOUR, WORK_END_HOUR
        print("[+] Config: OK")
    except Exception as e:
        print(f"[-] Config Error: {e}")
        return

    try:
        from funpay import FunPayClient
        from playwright_stealth import Stealth
        print("[+] Imports (Playwright/Stealth): OK")
    except Exception as e:
        print(f"[-] Imports Error: {e}")
        return

    try:
        client = FunPayClient("OFFLINE", "UA", offline=True)
        print("[+] FunPayClient Init: OK")
        
        auth, name = client.check_authorization()
        if auth:
            print(f"[+] Offline Auth: OK ({name})")
        else:
            print(f"[-] Offline Auth Failed: {name}")
            
        stats = client.get_stats()
        if stats.get('balance'):
            print("[+] Stats Parsing: OK")
            
        client.close()
        print("[+] Client Shutdown: OK")
    except Exception as e:
        print(f"[-] Client Engine Error: {e}")
        return

    try:
        from main import is_work_time
        res = is_work_time()
        print(f"[+] Work Hours Logic: OK (Current status: {res})")
    except Exception as e:
        print(f"[-] Work Hours Error: {e}")
        return

    print("\n[SUCCESS] The bot is technically sound and ready for operation.")

if __name__ == "__main__":
    check()
