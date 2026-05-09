import time
import random
import threading
import os
import json
from datetime import datetime
from colorama import init, Fore, Back, Style
from config import GOLDEN_KEY, USER_AGENT, TG_TOKEN, ADMIN_ID, GEMINI_API_KEY, PROXY, WORK_START_HOUR, WORK_END_HOUR, OFFLINE_MODE
from funpay import FunPayClient
try:
    from ai_responder import AIResponder
except ImportError:
    AIResponder = None

try:
    from tg_bot import TelegramManager
except ImportError:
    TelegramManager = None

try:
    from stats_manager import StatsManager
except ImportError:
    StatsManager = None

# Инициализация colorama
init(autoreset=True)

AUTHOR = "✨ By Ashanov Engine ✨"
VERSION = "3.3.0 Stable (Single-Thread)"

BANNER = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════╗
{Fore.CYAN}║ {Fore.WHITE}ASHANOV STEALTH BOT {Fore.CYAN}║ {Fore.YELLOW}v{VERSION} {Fore.CYAN}║ {Fore.GREEN}STATUS: STEALTH {Fore.CYAN}║
{Fore.CYAN}╚═══════════════════════════════════════════════════════════════╝
{Fore.MAGENTA}{AUTHOR}
"""

def log(message, level="INFO"):
    """Красивое логирование с тегами и цветами."""
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    
    levels = {
        "INFO": (Fore.CYAN, "[INFO]"),
        "SUCCESS": (Fore.GREEN, "[SUCCESS]"),
        "ERROR": (Fore.RED, "[ERROR]"),
        "WARNING": (Fore.YELLOW, "[WARNING]"),
        "CHAOS": (Fore.BLACK + Back.WHITE, "[CHAOS]"),
        "BOT": (Fore.MAGENTA, "[BOT]"),
        "TG": (Fore.BLUE, "[TELEGRAM]")
    }
    
    color, tag = levels.get(level, (Fore.WHITE, "[LOG]"))
    prefix = f"{Fore.CYAN}[{time_str}]{Style.RESET_ALL} {color}{tag}{Style.RESET_ALL}"
    print(f"{prefix} {message}")

def is_work_time():
    hour = datetime.now().hour
    if WORK_START_HOUR <= WORK_END_HOUR:
        return WORK_START_HOUR <= hour < WORK_END_HOUR
    else: # Переход через полночь
        return hour >= WORK_START_HOUR or hour < WORK_END_HOUR

def save_sale(order):
    """Сохраняет данные о продаже в sales.json."""
    filename = 'sales.json'
    sales = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                sales = json.load(f)
        except: pass
    
    # Очистка цены от символа валюты и пробелов
    price_str = order['price'].replace('₽', '').replace(' ', '').replace('$', '').replace('€', '').strip()
    try:
        price_val = float(price_str)
    except:
        price_val = 0.0
        
    sale_data = {
        "order_id": order['order_id'],
        "title": order['title'],
        "buyer": order['buyer'],
        "price": price_val,
        "timestamp": time.time()
    }
    
    # Проверка на дубликаты
    if not any(s['order_id'] == order['order_id'] for s in sales):
        sales.append(sale_data)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(sales, f, ensure_ascii=False, indent=4)
        return True
    return False

# Кеш для информации о пользователях (чтобы не чекать профиль каждый раз)
USER_INFO_CACHE = {}

# Глобальный список для исключения дубликатов ответов ИИ
RECENT_BOT_MESSAGES = set()

def main():
    print(BANNER)
    log("Инициализация системы...", level="INFO")
    
    if not GOLDEN_KEY and not OFFLINE_MODE:
        log("GOLDEN_KEY не найден в config.py!", level="ERROR")
        return

    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    client = FunPayClient(GOLDEN_KEY, USER_AGENT, proxies=proxies, offline=OFFLINE_MODE)
    
    log("Получаем данные пользователя...", level="INFO")
    is_authorized, result = client.check_authorization()
    
    if is_authorized:
        log(f"Привет, {result}! (ID: {client.user_id})", level="BOT")
    else:
        log(f"Ошибка авторизации: {result}", level="ERROR")
        return

    # Задержка перед началом работы ("прогрев")
    startup_delay = random.randint(15, 60)
    log(f"⏳ Режим 'прогрева' активен... Начинаем через {startup_delay}с", level="INFO")
    time.sleep(startup_delay)

    log("Сканируем профиль в поисках ваших категорий для автоподнятия...", level="INFO")
    success, cats_count = client.get_categories_to_bump()
    
    if success:
        log(f"Список категорий обновлён. Найдено для поднятия: {cats_count} шт.", level="SUCCESS")
    else:
        log(f"Ошибка при поиске категорий: {cats_count}", level="WARNING")
        
    log("Проверяем активные заказы...", level="INFO")
    active_orders = client.get_active_orders()
    if active_orders:
        log(f"У вас есть актуальные заказы ({len(active_orders)} шт.):", level="SUCCESS")
        for o in active_orders:
            log(f" - [{o['order_id']}] {o['title']} от {o['buyer']} ({o['price']})", level="INFO")
            client.seen_orders.add(o['order_id'])
    else:
        log("Нет активных неоплаченных заказов.", level="INFO")
    
    ai = AIResponder(GEMINI_API_KEY, log) if (AIResponder and GEMINI_API_KEY) else None
    tg_manager = None
    
    if TG_TOKEN and ADMIN_ID and TelegramManager:
        log("Запуск Telegram-интерфейса...", level="INFO")
        tg_manager = TelegramManager(TG_TOKEN, ADMIN_ID, client, log, ai_responder=ai)
        # ТГ-бот - единственный поток, который НЕ трогает браузер напрямую. Он только меняет настройки.
        threading.Thread(target=tg_manager.run_polling, daemon=True).start()
        
        log("Собираем статистику для Telegram...", level="INFO")
        stats = client.get_stats()
        tg_manager.send_startup_message(result, stats)
    else:
        log("Telegram-бот не запущен (проверьте config.py).", level="WARNING")

    stats_manager_instance = StatsManager() if StatsManager else None
    log("Основной цикл мониторинга и автоподнятия запущен.", level="SUCCESS")
    
    NEXT_BREAK_TIME = time.time() + random.randint(7200, 14400)
    LAST_POLL_TIME = 0
    
    def smart_sleep(seconds):
        """Спит указанное время, но каждые 1с проверяет наличие флагов из ТГ."""
        stop_at = time.time() + seconds
        while time.time() < stop_at:
            # Если появились срочные задачи из ТГ - прерываем сон
            if tg_manager:
                if tg_manager.settings.get('needs_chat_list') or tg_manager.settings.get('force_bump') or \
                   tg_manager.settings.get('needs_stats') or tg_manager.settings.get('pending_tasks') or \
                   tg_manager.settings.get('needs_chat_details'):
                    return True # Сигнал, что нужно проснуться
            time.sleep(1)
        return False

    if tg_manager:
        log("Очистка старых запросов из Telegram...", level="INFO")
        tg_manager.settings['needs_chat_list'] = False
        tg_manager.settings['needs_chat_details'] = False
        tg_manager.settings['needs_stats'] = False
        tg_manager.settings['force_bump'] = False
        tg_manager.save_settings()

    while True:
        try:
            now = time.time()
            
            # 1. Проверка времени работы и перерывов
            if not is_work_time():
                log("Ночной режим. Бот спит...", level="INFO")
                smart_sleep(600)
                continue
                
            if now >= NEXT_BREAK_TIME:
                break_dur = random.randint(600, 2400)
                log(f"Ухожу на перерыв на {break_dur // 60} мин...", level="INFO")
                smart_sleep(break_dur)
                NEXT_BREAK_TIME = time.time() + random.randint(7200, 18000)
                log("Вернулся с перерыва.", level="SUCCESS")
                continue

            if tg_manager:
                # Проверка флагов
                if tg_manager.settings.get('needs_chat_list'):
                    try:
                        log("Получен запрос на список чатов из ТГ...", level="INFO")
                        chats = client.get_chat_list()
                        tg_manager.send_chat_list(chats)
                    except Exception as e:
                        log(f"Ошибка при обработке списка чатов: {e}", level="ERROR")
                    finally:
                        tg_manager.settings['needs_chat_list'] = False
                
                if tg_manager.settings.get('needs_chat_details'):
                    try:
                        chat_id = tg_manager.settings.get('needs_chat_details')
                        log(f"Получен запрос на подробности чата {chat_id}...", level="INFO")
                        details = client.get_chat_details(chat_id)
                        log(f"Отправляю подробности чата {chat_id} в ТГ...", level="INFO")
                        tg_manager.send_chat_details(chat_id, details)
                    except Exception as e:
                        log(f"Ошибка при загрузке деталей чата: {e}", level="ERROR")
                    finally:
                        tg_manager.settings['needs_chat_details'] = False
                        tg_manager.save_settings()
                
                if tg_manager.settings.get('needs_stats'):
                    try:
                        log("Получен запрос на расширенную статистику...", level="INFO")
                        stats_base = client.get_stats()
                        if stats_manager_instance:
                            data = stats_manager_instance.get_aggregated_data()
                            if data:
                                html = stats_manager_instance.generate_html(data)
                                photo_path = client.render_dashboard(html)
                                if photo_path:
                                    tg_manager.send_advanced_stats(photo_path, data['metrics'])
                                else:
                                    tg_manager.send_stats_menu(stats_base)
                            else:
                                tg_manager.send_stats_menu(stats_base)
                        else:
                            tg_manager.send_stats_menu(stats_base)
                    except Exception as e:
                        log(f"Ошибка при сборе статистики: {e}", level="ERROR")
                    finally:
                        tg_manager.settings['needs_stats'] = False

                # Обработка очереди задач (Возвраты, Ответы и т.д.)
                tasks = tg_manager.settings.get('pending_tasks', [])
                if tasks:
                    tg_manager.settings['pending_tasks'] = [] # Очищаем очередь сразу
                    for task in tasks:
                        t_type = task['type']
                        t_id = task['id']
                        if t_type == 'refund':
                            log(f"Выполняю ВОЗВРАТ по заказу #{t_id}...", level="WARNING")
                            ok, res = client.refund_order(t_id)
                            msg = f"✅ Возврат #{t_id} выполнен!" if ok else f"❌ Ошибка возврата #{t_id}: {res}"
                            tg_manager.bot.send_message(tg_manager.admin_id, msg)
                        elif t_type == 'manual_reply':
                            log(f"Отправляю ручной ответ в чат {t_id}...", level="INFO")
                            ok, res = client.send_message(t_id, task['text'])
                            msg_text = f"✅ Сообщение в чат #{t_id} отправлено!" if ok else f"❌ Ошибка отправки в чат #{t_id}: {res}"
                            tg_manager.bot.send_message(tg_manager.admin_id, msg_text)
                        elif t_type == 'ai_reply':
                            log(f"Генерирую ИИ ответ для чата {t_id}...", level="INFO")
                            if ai:
                                details = client.get_chat_details(t_id)
                                if "error" not in details and details['messages']:
                                    last_msg = None
                                    for m in reversed(details['messages']):
                                        if not m['is_our']:
                                            last_msg = m
                                            break
                                    if last_msg:
                                        msg_data = {'chat_id': t_id, 'user': last_msg['user'], 'text': last_msg['text']}
                                        ai_answer = ai.process_message(msg_data, client.get_active_orders())
                                        if ai_answer:
                                            ok, res = client.send_message(t_id, ai_answer)
                                            msg_text = f"✅ ИИ ответил в чат #{t_id}!" if ok else f"❌ Ошибка ИИ-ответа #{t_id}: {res}"
                                            tg_manager.bot.send_message(tg_manager.admin_id, msg_text)
                                        else:
                                            tg_manager.bot.send_message(tg_manager.admin_id, f"⚠️ ИИ не смог сгенерировать ответ для чата #{t_id}")
                                    else:
                                        tg_manager.bot.send_message(tg_manager.admin_id, f"⚠️ Нет сообщений от покупателя в чате #{t_id}")
                                else:
                                    tg_manager.bot.send_message(tg_manager.admin_id, f"❌ Ошибка загрузки чата #{t_id} для ИИ")
                            else:
                                tg_manager.bot.send_message(tg_manager.admin_id, "❌ ИИ модуль не настроен (проверьте API ключ)")
                    tg_manager.save_settings()

            # 2. Мониторинг (Сообщения и Заказы) - Каждые 60-120 сек
            if now - LAST_POLL_TIME > random.randint(60, 120):
                # Проверка сообщений
                messages = client.get_new_messages()
                if messages:
                    active_orders_context = client.get_active_orders()
                    for msg in messages:
                        if msg['user'].lower() == result.lower(): continue
                        if msg['text'].strip() in RECENT_BOT_MESSAGES: continue
                        
                        log(f"Новое сообщение от {msg['user']}: {msg['text'][:50]}...", level="BOT")
                        
                        # Оценка рисков (Anti-Scam)
                        user_info = None
                        if tg_manager and tg_manager.settings.get('anti_scam', True):
                            if msg['user'] not in USER_INFO_CACHE:
                                user_info = client.get_user_info(chat_id=msg['chat_id'])
                                if user_info:
                                    USER_INFO_CACHE[msg['user']] = user_info
                            else:
                                user_info = USER_INFO_CACHE[msg['user']]
                        
                        msg['user_info'] = user_info # Добавляем в объект сообщения для уведомления
                        
                        # AI Ответ
                        if tg_manager and tg_manager.settings.get('auto_respond') and ai:
                            ai_answer = ai.process_message(msg, active_orders_context)
                            if ai_answer:
                                s_ok, s_err = client.send_message(msg['chat_id'], ai_answer)
                                if s_ok:
                                    RECENT_BOT_MESSAGES.add(ai_answer.strip())
                                    client.mark_chat_read(msg['chat_id'])
                                    log(f"ИИ ответил пользователю {msg['user']}", level="SUCCESS")
                                    continue
                        
                        if tg_manager and tg_manager.settings.get('notifications'):
                            tg_manager.notify_new_message(msg)
                        
                        client.last_seen_messages[msg['chat_id']] = msg['msg_id']
                
                # Проверка новых заказов
                orders = client.get_new_orders()
                for order in orders:
                    log(f"Новый заказ #{order['order_id']} от {order['buyer']}!", level="SUCCESS")
                    save_sale(order)
                    
                    # Оценка рисков для заказа
                    # (Для заказа сложнее получить chat_id сразу, но мы можем использовать buyer name)
                    user_info = None
                    if tg_manager and tg_manager.settings.get('anti_scam', True):
                        user_info = USER_INFO_CACHE.get(order['buyer'])
                    # Если в кеше нет, пока пропускаем детальную проверку (или можно добавить позже)
                    order['user_info'] = user_info
                    
                    if tg_manager and tg_manager.settings.get('notifications'):
                        tg_manager.notify_new_order(order)
                    
                    client.seen_orders.add(order['order_id'])

                # Проверка новых отзывов
                reviews = client.get_new_reviews()
                for review in reviews:
                    log(f"Новый отзыв {review['rating']} звезд от {review['author']}!", level="SUCCESS")
                    if tg_manager and tg_manager.settings.get('notifications'):
                        tg_manager.notify_new_review(review)

                LAST_POLL_TIME = time.time()


            # 3. Автоподнятие лотов
            force_bump = tg_manager.settings.get('force_bump') if tg_manager else False
            if (tg_manager and tg_manager.settings.get('auto_bump')) or force_bump:
                if force_bump:
                    log("Выполняю ПРИНУДИТЕЛЬНОЕ поднятие лотов (команда из ТГ)...", level="INFO")
                    tg_manager.settings['force_bump'] = False
                    tg_manager.save_settings()
                    # Сбрасываем кулдауны для форсированного поднятия
                    for node_id in client.bump_state:
                        client.bump_state[node_id]['next_up_time'] = 0
                
                if random.random() < 0.01 and not force_bump: # Сёрфинг только при обычном поднятии
                    log("Имитация активности: серфинг главной страницы...", level="CHAOS")
                    try: client.page.goto(f"{client.base_url}/", wait_until="domcontentloaded")
                    except: pass
                    time.sleep(random.randint(3, 8))
                
                bumped_games = set()
                for cat in client.categories_to_bump:
                    game_id = str(cat['game_id'])
                    if game_id in bumped_games: continue
                    state = client.bump_state.get(str(cat['node_id']), {})
                    if now >= state.get('next_up_time', 0):
                        # Хаос: 2% шанс "забыть" поднять в этом цикле
                        if random.random() < 0.02:
                            log(f"Имитация: пропустил поднятие {cat['name']} (отвлекся)", level="CHAOS")
                            continue
                            
                        success, bump_msg = client.smart_bump_category(cat)
                        bumped_games.add(game_id)
                        if success: log(f"Поднято: {cat['name']}", level="SUCCESS")
                        else: log(f"Кулдаун: {cat['name']} ({bump_msg})", level="WARNING")

            # 4. Небольшая пауза между итерациями основного цикла
            smart_sleep(random.randint(20, 45))

        except Exception as e:
            log(f"Ошибка в основном цикле: {e}", level="ERROR")
            smart_sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Бот остановлен пользователем.", level="INFO")
    except Exception as e:
        log(f"Фатальная ошибка: {e}", level="ERROR")
