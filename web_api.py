import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import time

app = FastAPI(title="Ashanov FunPay TWA API")

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные ссылки на объекты из main
bot_client = None
bot_tg_manager = None
bot_stats_manager = None
public_url = None

class SettingsUpdate(BaseModel):
    auto_bump: bool
    online_mode: bool
    auto_respond: bool
    notifications: bool
    anti_scam: bool
    auto_delivery: bool

@app.get("/api/stats")
def get_stats():
    try:
        stats = bot_client.get_stats() if bot_client else {"balance": "0 ₽", "active_sales": 0, "unread_chats": 0}
        
        # Расширенная статистика, если есть StatsManager
        metrics = {}
        if bot_stats_manager:
            try:
                data = bot_stats_manager.get_aggregated_data()
                if data and 'metrics' in data:
                    metrics = data['metrics']
            except:
                pass
                
        return {"status": "ok", "stats": stats, "metrics": metrics}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/settings")
def get_settings():
    if not bot_tg_manager:
        return {"status": "error", "error": "TG Manager not initialized"}
    
    s = bot_tg_manager.settings
    return {
        "status": "ok",
        "settings": {
            "auto_bump": s.get("auto_bump", False),
            "online_mode": s.get("online_mode", False),
            "auto_respond": s.get("auto_respond", False),
            "notifications": s.get("notifications", False),
            "anti_scam": s.get("anti_scam", False),
            "auto_delivery": s.get("auto_delivery", False)
        }
    }

@app.post("/api/settings")
def update_settings(new_settings: SettingsUpdate):
    if not bot_tg_manager:
        return {"status": "error", "error": "TG Manager not initialized"}
    
    bot_tg_manager.settings["auto_bump"] = new_settings.auto_bump
    bot_tg_manager.settings["online_mode"] = new_settings.online_mode
    bot_tg_manager.settings["auto_respond"] = new_settings.auto_respond
    bot_tg_manager.settings["notifications"] = new_settings.notifications
    bot_tg_manager.settings["anti_scam"] = new_settings.anti_scam
    bot_tg_manager.settings["auto_delivery"] = new_settings.auto_delivery
    bot_tg_manager.save_settings()
    
    return {"status": "ok"}

def run_server(client, tg_manager, stats_manager):
    global bot_client, bot_tg_manager, bot_stats_manager, public_url
    bot_client = client
    bot_tg_manager = tg_manager
    bot_stats_manager = stats_manager
    
    # Создаем папку webapp если ее нет
    if not os.path.exists("webapp"):
        os.makedirs("webapp")
    
    # Пытаемся подключить статику, если есть index.html
    if os.path.exists(os.path.join("webapp", "index.html")):
        app.mount("/", StaticFiles(directory="webapp", html=True), name="static")
    
    def start_uvicorn():
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")
        
    threading.Thread(target=start_uvicorn, daemon=True).start()
    
    try:
        import subprocess
        import re
        
        # Запускаем ssh туннель
        process = subprocess.Popen(
            ['ssh', '-o', 'StrictHostKeyChecking=no', '-R', '80:localhost:8000', 'nokey@localhost.run'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Ждем и читаем URL из вывода
        for _ in range(30): # Читаем первые 30 строк
            line = process.stdout.readline()
            match = re.search(r'(https://[a-zA-Z0-9.-]+\.lhr\.life)', line)
            if match:
                public_url = match.group(1)
                print(f"\n[SUCCESS] WebApp запущен (без ngrok)! URL: {public_url}\n")
                break
                
    except Exception as e:
        print(f"\n[WARNING] Ошибка запуска ssh туннеля: {e}")
        public_url = None

def get_public_url():
    return public_url
