import time
import random
import os
import threading
from datetime import datetime
from colorama import init, Fore, Style
from config import GOLDEN_KEY, USER_AGENT, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, GEMINI_API_KEY, PROXY
from funpay import FunPayClient
try:
    from tg_bot import TelegramManager
except ImportError:
    TelegramManager = None
try:
    from ai_responder import AIResponder
except ImportError:
    AIResponder = None

# Инициализация colorama
init(autoreset=True)

VERSION = "v0.1.0"
AUTHOR = "By Ashanov"

ASCII_LOGO = f"""
{Fore.WHITE}███████╗██╗   ██╗███╗   ██╗██████╗  █████╗ ██╗   ██╗
{Fore.WHITE}██╔════╝██║   ██║████╗  ██║██╔══██╗██╔══██╗╚██╗ ██╔╝
{Fore.WHITE}█████╗  ██║   ██║██╔██╗ ██║██████╔╝███████║ ╚████╔╝ 
{Fore.WHITE}██╔══╝  ██║   ██║██║╚██╗██║██╔═══╝ ██╔══██║  ╚██╔╝  
{Fore.WHITE}██║     ╚██████╔╝██║ ╚████║██║     ██║  ██║   ██║   
{Fore.WHITE}╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝   ╚═╝   
{Fore.CYAN}A S H A N O V

{Fore.CYAN}{VERSION}
{Fore.MAGENTA}{AUTHOR}
"""

def log(message, color=Fore.WHITE, prefix_color=Fore.YELLOW):
    """Кастомная функция для красивых логов."""
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M:%S")
    prefix = f"{prefix_color}>{Style.RESET_ALL} {Fore.CYAN}[{date_str}] [{time_str}]:{Style.RESET_ALL}"
    print(f"{prefix} {color}{message}{Style.RESET_ALL}")

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(ASCII_LOGO)
    
    if GOLDEN_KEY == "СЮДА_ВСТАВИТЬ_ВАШ_GOLDEN_KEY" or not GOLDEN_KEY:
        log("Ошибка: Пожалуйста, укажите ваш 'golden_key' в файле config.py", color=Fore.RED)
        return

    # Настраиваем прокси для curl_cffi
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    client = FunPayClient(GOLDEN_KEY, USER_AGENT, proxies=proxies)
    
    log("Получаем данные пользователя...", color=Fore.CYAN)
    is_authorized, result = client.check_authorization()
    
    if is_authorized:
        log(f"Привет, {result}! (ID: {client.user_id})", color=Fore.MAGENTA)
    else:
        log(f"Ошибка авторизации: {result}", color=Fore.RED)
        return

    log("Сканируем профиль в поисках ваших категорий для автоподнятия...", color=Fore.CYAN)
    success, cats_count = client.get_categories_to_bump()
    
    if success:
        log(f"Список категорий обновлён. Найдено для поднятия: {cats_count} шт.", color=Fore.GREEN)
        for c in client.categories_to_bump:
            log(f" - {c['name']} (Game: {c['game_id']}, Node: {c['node_id']})", color=Fore.WHITE)
    else:
        log(f"Ошибка при поиске категорий: {cats_count}", color=Fore.RED)
        # Не делаем return, так как чаты всё равно могут работать
        
    log("Проверяем активные заказы...", color=Fore.CYAN)
    active_orders = client.get_active_orders()
    if active_orders:
        log(f"У вас есть актуальные заказы ({len(active_orders)} шт.):", color=Fore.GREEN)
        for o in active_orders:
            log(f" - [{o['order_id']}] {o['title']} от {o['buyer']} ({o['price']})", color=Fore.YELLOW)
            # Отмечаем, чтобы сразу не дублировать их в Telegram как новые
            client.seen_orders.add(o['order_id'])
    else:
        log("Нет активных неоплаченных заказов.", color=Fore.WHITE)
    
    # Инициализация ИИ
    ai = AIResponder(GEMINI_API_KEY, log) if AIResponder else None

    # Инициализация Telegram бота
    tg_manager = None
    if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID and TelegramManager:
        log("Запуск интеграции с Telegram...", color=Fore.CYAN)
        tg_manager = TelegramManager(TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, client, log, ai_responder=ai)
        threading.Thread(target=tg_manager.run_polling, daemon=True).start()
        
        # Отправляем приветственное сообщение
        log("Собираем статистику аккаунта...", color=Fore.CYAN)
        stats = client.get_stats()
        tg_manager.send_startup_message(result, stats)
        
        # Кэш для отправленных ИИ сообщений, чтобы не отвечать на них же
        RECENT_BOT_MESSAGES = set()
        
        # Запускаем поток для проверки новых сообщений и заказов
        def poll_updates():
            while True:
                try:
                    # Проверка сообщений
                    messages = client.get_new_messages()
                    if messages:
                        active_orders_context = client.get_active_orders()
                        for msg in messages:
                            # Игнорируем сообщения от самого продавца по нику
                            if msg['user'].lower() == result.lower():
                                continue
                                
                            # Игнорируем собственные сообщения ИИ (по точному тексту)
                            if msg['text'].strip() in RECENT_BOT_MESSAGES:
                                continue
                                
                            # Проверка на проблемное сообщение
                            problem_severity = ai.detect_problem(msg['text']) if ai else None
                            
                            if problem_severity:
                                log(f"Входящее ПРОБЛЕМНОЕ сообщение от [{msg['user']}]: {msg['text']}", color=Fore.RED, prefix_color=Fore.MAGENTA)
                                tg_manager.notify_problem(msg['chat_id'], msg['user'], msg['text'], problem_severity)
                                
                                # Автоматический ответ "заглушка"
                                temp_reply = "Понял, сейчас проверю и отвечу в ближайшее время."
                                success, _ = client.send_message(msg['chat_id'], temp_reply)
                                if success:
                                    RECENT_BOT_MESSAGES.add(temp_reply)
                                    client.mark_chat_read(msg['chat_id'])
                                    
                                continue # Пропускаем стандартный автоответ
                                
                            log(f"Входящее сообщение от [{msg['user']}]: {msg['text']}", color=Fore.YELLOW, prefix_color=Fore.MAGENTA)
                            
                            ai_answer = ai.process_message(msg, active_orders_context) if ai else None
                            
                            if ai_answer:
                                success, send_result = client.send_message(msg['chat_id'], ai_answer)
                                if success:
                                    RECENT_BOT_MESSAGES.add(ai_answer.strip())
                                    client.mark_chat_read(msg['chat_id']) # Снимаем статус "unread"
                                    log(f"ИИ ответил: {ai_answer}", color=Fore.GREEN)
                                    tg_manager.notify_ai_reply(msg['chat_id'], msg['user'], msg['text'], ai_answer)
                                else:
                                    log(f"Ошибка отправки ИИ: {send_result}", color=Fore.RED)
                                    tg_manager.notify_new_message(msg)
                            else:
                                tg_manager.notify_new_message(msg)
                    
                    # Проверка заказов
                    orders = client.get_new_orders()
                    for order in orders:
                        log(f"НОВЫЙ ЗАКАЗ: {order['title']} от {order['buyer']} ({order['price']})", color=Fore.GREEN, prefix_color=Fore.MAGENTA)
                        tg_manager.notify_new_order(order)
                except Exception as e:
                    log(f"Ошибка в poll_updates: {e}", color=Fore.RED)
                    
                # Максимально безопасный интервал (1-3 минуты), чтобы имитировать человека
                time.sleep(random.randint(60, 180)) 
                
        threading.Thread(target=poll_updates, daemon=True).start()
    else:
        log("Telegram-бот отключен (не указан токен или ID в config.py).", color=Fore.YELLOW)

    log(f"Автоподнятие запущено, загружено {cats_count} категория(ий).", color=Fore.WHITE)
    
    # Модуль вечного онлайна в отдельном потоке
    def keep_online():
        while True:
            try:
                # Отправляем запрос на главную страницу через браузер
                client.page.goto(f"{client.base_url}/", wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            # Рандом 3-7 минут
            time.sleep(random.randint(180, 420)) 
            
    threading.Thread(target=keep_online, daemon=True).start()
    log("Модуль 'Вечный онлайн' активирован 🟢", color=Fore.GREEN)
    
    try:
        log("Умный бампер запущен. Проверка кулдаунов каждые 30-60 секунд.", color=Fore.CYAN)
        while True:
            now = time.time()
            # Группируем категории по game_id, чтобы не дублировать поднятие
            bumped_games = set()
            for cat in client.categories_to_bump:
                game_id = str(cat['game_id'])
                node_id = str(cat['node_id'])
                
                # Если уже подняли эту игру в этом цикле — пропускаем
                if game_id in bumped_games:
                    continue
                    
                state = client.bump_state.get(node_id, {})
                next_up = state.get('next_up_time', 0)
                
                if now >= next_up:
                    success, msg = client.smart_bump_category(cat)
                    bumped_games.add(game_id)
                    if success:
                        log(f"[BUMPER] {cat['name']} | ✅ {msg}", color=Fore.GREEN)
                    else:
                        if "Рано" in msg:
                            log(f"[BUMPER] {cat['name']} | ⏳ {msg}", color=Fore.YELLOW)
                        else:
                            log(f"[BUMPER] {cat['name']} | ❌ {msg}", color=Fore.RED)
            
            # Интервал между проверками (каждые 2-5 минут)
            time.sleep(random.randint(120, 300))

    except KeyboardInterrupt:
        print("\n")
        log("Бот остановлен пользователем. Закрываем браузер...", color=Fore.RED)
        client.close()

if __name__ == "__main__":
    if os.name == 'nt':
        os.system('title FunPay Bot')
    main()
