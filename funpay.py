from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import json
import time
import random
import os
import threading
from functools import wraps

def browser_action(func):
    """Декоратор для обеспечения потокобезопасности при работе с браузером."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.playwright or not self.context or not self.page:
            self.start_browser()
        
        # Проверка, не закрыта ли страница
        try:
            if self.page.is_closed():
                self.start_browser()
        except:
            self.start_browser()

        if self.offline: return func(self, *args, **kwargs)
        with self.browser_lock:
            return func(self, *args, **kwargs)
    return wrapper

class FunPayClient:
    def __init__(self, golden_key, user_agent, proxies=None, offline=False):
        self.golden_key = golden_key
        self.user_agent = user_agent
        self.proxies = proxies
        self.offline = offline
        self.base_url = "https://funpay.com"
        self.browser_lock = threading.RLock() # Замок для многопоточности (RLock позволяет рекурсивные вызовы)
        
        self.playwright = None
        self.context = None
        self.page = None
        
        self.csrf_token = None
        self.user_id = None
        self.categories_to_bump = []
        self.last_seen_messages = {}
        self.seen_orders = set()
        self.bump_state_file = 'bump_state.json'
        self.bump_state = self.load_bump_state()
        
        # Запускаем браузер сразу
        self.start_browser()

    def chaos_delay(self, action_type="normal"):
        """Движок хаоса для генерации нелинейных задержек."""
        chance = random.random()
        
        if action_type == "message":
            if chance < 0.1: return time.sleep(random.uniform(1, 3))     # Очень быстро
            if chance < 0.2: return time.sleep(random.uniform(30, 90))   # Ушел за чаем
            return time.sleep(random.uniform(5, 15))                     # Нормально
            
        if action_type == "click":
            if chance < 0.1: return time.sleep(random.uniform(0.5, 1.5)) # Молниеносно
            if chance < 0.15: return time.sleep(random.uniform(10, 25))  # Затупил
            return time.sleep(random.uniform(2, 5))                      # Обычный клик
            
        # Дефолтная задержка
        time.sleep(random.uniform(2, 8))

    def start_browser(self):
        """Запускает браузер с сохранением сессии в user_data."""
        if self.offline:
            self.csrf_token = "offline_token"
            self.user_id = "1234567"
            return

        self.playwright = sync_playwright().start()
        
        # Папка для сессии
        user_data_dir = os.path.join(os.getcwd(), "user_data")
        
        launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        proxy_settings = None
        
        if self.proxies:
            # Парсинг прокси
            if isinstance(self.proxies, str):
                if "@" in self.proxies:
                    auth, server = self.proxies.replace("http://", "").split("@")
                    user, pwd = auth.split(":")
                    proxy_settings = {"server": f"http://{server}", "username": user, "password": pwd}
                else:
                    proxy_settings = {"server": self.proxies}

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            user_agent=self.user_agent,
            viewport={'width': 1920, 'height': 1080},
            args=launch_args,
            proxy=proxy_settings
        )
        
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        
        # Прокидываем golden_key (на случай если сессия истекла)
        self.context.add_cookies([{
            'name': 'golden_key', 'value': self.golden_key,
            'domain': '.funpay.com', 'path': '/'
        }])
        
        # Применяем Stealth
        Stealth().apply_stealth_sync(self.page)

    def close(self):
        """Закрывает браузер и сохраняет сессию."""
        if self.offline: return
        try:
            if self.context: self.context.close()
            if self.playwright: self.playwright.stop()
        except: pass

    def load_bump_state(self):
        if os.path.exists(self.bump_state_file):
            try:
                with open(self.bump_state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def save_bump_state(self):
        with open(self.bump_state_file, 'w', encoding='utf-8') as f:
            json.dump(self.bump_state, f, ensure_ascii=False, indent=4)

    def parse_wait_time(self, msg):
        import re
        msg_low = msg.lower()
        
        # Специальные случаи без цифр
        if "час" in msg_low and not re.search(r'\d+\s*час', msg_low):
            return 3600
        if "минут" in msg_low and not re.search(r'\d+\s*минут', msg_low):
            return 60
            
        hours = re.search(r'(\d+)\s*(час|часа|часов)', msg_low)
        minutes = re.search(r'(\d+)\s*(минут|минуту|минуты)', msg_low)
        seconds = re.search(r'(\d+)\s*(секунд|секунду|секунды|сек)', msg_low)
        
        h = int(hours.group(1)) if hours else 0
        m = int(minutes.group(1)) if minutes else 0
        s = int(seconds.group(1)) if seconds else 0
        
        return h * 3600 + m * 60 + s

    @browser_action
    def check_authorization(self):
        """Проверяет авторизацию и извлекает базовые данные."""
        if self.offline: return True, "Offline_User"
        try:
            self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=60000)
            
            # Ждем немного дольше и мягче
            try:
                self.page.wait_for_selector(".user-link-name, .login-link", timeout=30000, state="attached")
            except: pass # Если не дождались, попробуем проверить что есть
            
            # Сначала проверяем на наличие ника (успех)
            user_link = self.page.query_selector('.user-link-name')
            if user_link:
                name = user_link.inner_text().strip()
                # Извлекаем CSRF
                app_data_raw = self.page.evaluate("() => document.body.getAttribute('data-app-data')")
                if app_data_raw:
                    try:
                        app_data = json.loads(app_data_raw)
                        self.csrf_token = app_data.get('csrf-token')
                    except: pass
                
                # Извлекаем ID
                href = self.page.evaluate("() => { const el = document.querySelector('.user-link-name'); return el ? el.parentElement.getAttribute('href') : null; }")
                if href:
                    self.user_id = href.strip('/').split('/')[-1]
                return True, name
                
            # Если ника нет, проверяем кнопку входа
            if self.page.query_selector(".login-link"):
                return False, "Не авторизован (проверьте GOLDEN_KEY)"
                
            return False, "Не удалось определить статус авторизации."
        except Exception as e:
            return False, f"Ошибка браузера: {e}"

    @browser_action
    def get_stats(self):
        if self.offline: return {"balance": "100.00 ₽", "unread_chats": "0", "active_sales": "0"}
        try:
            self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=60000)
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            balance_elem = soup.select_one('.badge-balance')
            balance = balance_elem.text.strip() if balance_elem else "0"
            
            chat_elem = soup.select_one('.badge-chat')
            unread_chats = chat_elem.text.strip() if chat_elem and 'hidden' not in chat_elem.get('class', []) else "0"
            
            trade_elem = soup.select_one('.badge-trade')
            active_sales = trade_elem.text.strip() if trade_elem and 'hidden' not in trade_elem.get('class', []) else "0"
            
            return {"balance": balance, "unread_chats": unread_chats, "active_sales": active_sales}
        except:
            return {"balance": "?", "unread_chats": "?", "active_sales": "?"}

    @browser_action
    def get_categories_to_bump(self):
        """Парсит категории, которые можно поднимать."""
        if self.offline: return True, 0
        if not self.user_id: return False, "User ID не найден"
        try:
            self.page.goto(f"{self.base_url}/users/{self.user_id}/", wait_until="networkidle", timeout=60000)
            links = self.page.query_selector_all('a')
            category_urls = set()
            import re
            for link in links:
                href = link.get_attribute('href')
                if href and re.search(r'/[a-zA-Z\-]+/\d+/?$', href):
                    if not any(x in href for x in ['/users/', '/trade/', '/orders/', '/chat/']):
                        url = href if href.startswith('http') else self.base_url + href
                        name = link.inner_text().strip() or "Категория"
                        category_urls.add((url, name))
            
            nodes_found = set()
            self.categories_to_bump = []
            
            for url, name in category_urls:
                trade_url = url.rstrip('/') + '/trade'
                self.page.goto(trade_url, wait_until="domcontentloaded", timeout=60000)
                btn = self.page.query_selector('button.js-lot-raise')
                if btn:
                    game_id = btn.get_attribute('data-game')
                    node_id = btn.get_attribute('data-node')
                    if node_id not in nodes_found:
                        nodes_found.add(node_id)
                        self.categories_to_bump.append({'game_id': game_id, 'node_id': node_id, 'name': name})
                time.sleep(random.uniform(1, 2))
            return True, len(self.categories_to_bump)
        except Exception as e:
            return False, str(e)

    def bump_all(self):
        """Ручное поднятие всех категорий (для вызова из ТГ)."""
        if not self.categories_to_bump:
            return False, "Список категорий пуст. Сначала выполните сканирование."
        
        success_count = 0
        errors = []
        
        for cat in self.categories_to_bump:
            success, msg = self.smart_bump_category(cat)
            if success:
                success_count += 1
            else:
                if "Рано" not in msg:
                    errors.append(f"{cat['name']}: {msg}")
            time.sleep(random.uniform(2, 5))
            
        if success_count > 0:
            return True, f"Поднято категорий: {success_count}. Ошибок: {len(errors)}"
        return False, f"Ничего не поднято. Ошибки: {', '.join(errors[:2])}"

    @browser_action
    def smart_bump_category(self, cat):
        if self.offline: return True, "Успешно (Offline)"
        self.chaos_delay("click") 
        try:
            node_id = str(cat['node_id'])
            game_id = cat['game_id']
            now = time.time()
            
            if node_id not in self.bump_state:
                self.bump_state[node_id] = {"next_up_time": 0}
            
            js_script = f"""
            fetch('/lots/raise', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                }},
                body: 'game_id={game_id}&node_id={node_id}&csrf_token={self.csrf_token}'
            }}).then(r => r.json())
            """
            data = self.page.evaluate(js_script)
            
            if data.get('error'):
                msg = data.get('msg', '')
                wait_seconds = self.parse_wait_time(msg)
                
                # Если время не распарсилось, но ошибка есть - ставим дефолтный кулдаун 10 минут, чтобы не спамить
                if wait_seconds <= 0:
                    wait_seconds = 600
                
                self.bump_state[node_id]["next_up_time"] = now + wait_seconds + random.randint(30, 90)
                self.save_bump_state()
                return False, f"Рано. Ждать {wait_seconds}с" if "Рано" in msg or wait_seconds > 600 else f"Ошибка: {msg}"
            
            # Вторая фаза (модалка)
            if 'modal' in data:
                soup = BeautifulSoup(data['modal'], 'html.parser')
                nodes = [inp.get('value') for inp in soup.find_all('input', {'type': 'checkbox'}) if inp.get('value')]
                if nodes:
                    nodes_payload = "&".join([f"node_ids%5B%5D={n}" for n in nodes])
                    js_step2 = f"""
                    fetch('/lots/raise', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' }},
                        body: 'game_id={game_id}&node_id={node_id}&csrf_token={self.csrf_token}&{nodes_payload}'
                    }}).then(r => r.json())
                    """
                    data2 = self.page.evaluate(js_step2)
                    if data2.get('error'): return False, data2.get('msg', 'Ошибка 2 шага')
                
            self.bump_state[node_id]["next_up_time"] = now + 14400 + random.randint(60, 300)
            self.save_bump_state()
            return True, "Успешно поднято!"
        except Exception as e:
            return False, f"Сбой браузера: {e}"

    @browser_action
    def get_chat_list(self, limit=10):
        """Парсит список последних чатов."""
        if self.offline: return []
        try:
            self.page.goto(f"{self.base_url}/chat/", wait_until="domcontentloaded", timeout=60000)
            # Пытаемся подождать список, но не падаем если его нет
            try:
                self.page.wait_for_selector(".contact-item", timeout=5000)
            except:
                pass
            
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            chats = []
            
            items = soup.find_all('a', class_='contact-item')
            if not items:
                return []

            for contact in items[:limit]:
                node_id = contact.get('data-id')
                user_name = contact.find('div', class_='media-user-name').text.strip()
                msg_div = contact.find('div', class_='contact-item-message')
                last_msg = msg_div.text.strip() if msg_div else "..."
                unread = 'unread' in contact.get('class', [])
                
                chats.append({
                    'id': node_id,
                    'name': user_name,
                    'last_msg': last_msg,
                    'unread': unread
                })
            return chats
        except Exception:
            return []

    @browser_action
    def get_new_messages(self):
        if self.offline: return []
        try:
            self.page.goto(f"{self.base_url}/chat/", wait_until="domcontentloaded", timeout=60000)
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            new_msgs = []
            is_first_run = len(self.last_seen_messages) == 0
            
            for contact in soup.find_all('a', class_='contact-item'):
                node_id = contact.get('data-id')
                msg_div = contact.find('div', class_='contact-item-message')
                if not node_id or not msg_div: continue
                
                msg_id = contact.get('data-node-msg')
                is_unread = 'unread' in contact.get('class', [])
                text = msg_div.text.strip()
                is_our_msg = any(text.lower().startswith(p) for p in ["вы:", "you:", "ви:"])
                
                if not is_unread or is_our_msg:
                    self.last_seen_messages[node_id] = msg_id
                    continue
                
                if node_id not in self.last_seen_messages or self.last_seen_messages[node_id] != msg_id:
                    if not is_first_run:
                        user = contact.find('div', class_='media-user-name').text.strip()
                        new_msgs.append({'chat_id': node_id, 'msg_id': msg_id, 'user': user, 'text': text})
            return new_msgs
        except: return []

    @browser_action
    def send_message(self, chat_id, text):
        if self.offline: return True, "Отправлено (Offline)"
        self.chaos_delay("message") 
        try:
            payload = json.dumps({"action": "chat_message", "data": {"node": chat_id, "content": text}})
            js_send = f"""
            fetch('/runner/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' }},
                body: 'request={payload}&csrf_token={self.csrf_token}'
            }}).then(r => r.json())
            """
            resp = self.page.evaluate(js_send)
            if resp.get('response', {}).get('error'): return False, str(resp['response']['error'])
            return True, "Отправлено"
        except Exception as e: return False, str(e)

    def get_active_orders(self):
        if self.offline: return []
        try:
            self.page.goto(f"{self.base_url}/orders/trade", wait_until="domcontentloaded", timeout=60000)
            soup = BeautifulSoup(self.page.content(), 'html.parser')
            orders = []
            for item in soup.find_all('a', class_='tc-item'):
                try:
                    status_elem = item.find('div', class_='tc-status')
                    if not status_elem: continue
                    status = status_elem.text.strip()
                    
                    if "Оплачен" in status or "Paid" in status:
                        order_id = item.find('div', class_='tc-order').text.strip().replace('#', '')
                        desc_div = item.find('div', class_='order-desc')
                        title = desc_div.find('div').text.strip() if desc_div and desc_div.find('div') else "Unknown Title"
                        
                        buyer_elem = item.find('div', class_='media-user-name')
                        buyer = buyer_elem.text.strip() if buyer_elem else "Unknown Buyer"
                        
                        price_elem = item.find('div', class_='tc-price')
                        price = price_elem.text.strip() if price_elem else "0"
                        
                        order_url = item.get('href')
                        if order_url and not order_url.startswith('http'):
                            order_url = self.base_url + order_url
                            
                        orders.append({'order_id': order_id, 'buyer': buyer, 'title': title, 'price': price, 'url': order_url})
                except Exception as e:
                    pass
            return orders
        except Exception as e:
            return []

    @browser_action
    def get_new_orders(self):
        all_active = self.get_active_orders()
        new = []
        for o in all_active:
            if o['order_id'] not in self.seen_orders:
                new.append(o)
        return new

    @browser_action
    def get_new_reviews(self):
        if self.offline or not self.user_id: return []
        try:
            self.page.goto(f"{self.base_url}/users/{self.user_id}/", wait_until="domcontentloaded", timeout=60000)
            soup = BeautifulSoup(self.page.content(), 'html.parser')
            
            reviews = []
            
            # На FunPay отзывы лежат в .review-item (или review-item-row)
            review_items = soup.find_all('div', class_='review-item')
            if not review_items:
                review_items = soup.find_all('div', class_='review-item-row')
                
            for item in review_items:
                try:
                    review_id = item.get('data-id') or str(hash(item.text))
                    
                    author_elem = item.find('div', class_='media-user-name') or item.find('div', class_='review-item-author')
                    author = author_elem.text.strip() if author_elem else "Unknown"
                    
                    text_elem = item.find('div', class_='review-item-text') or item.find('div', class_='review-text')
                    text = text_elem.text.strip() if text_elem else "Без текста"
                    
                    stars = item.find_all('i', class_='fas fa-star')
                    rating = len(stars) if stars else 5
                    
                    reviews.append({
                        'id': review_id,
                        'author': author,
                        'text': text,
                        'rating': rating
                    })
                except Exception:
                    pass
            
            new_reviews = []
            if not hasattr(self, 'seen_reviews'):
                self.seen_reviews = set()
                # Первый запуск — просто запоминаем существующие отзывы
                for r in reviews:
                    self.seen_reviews.add(r['id'])
                return []
                
            for r in reviews:
                if r['id'] not in self.seen_reviews:
                    new_reviews.append(r)
                    self.seen_reviews.add(r['id'])
                    
            return new_reviews
        except Exception as e:
            return []

    def mark_chat_read(self, chat_id):
        if self.offline: return True
        try:
            self.page.goto(f"{self.base_url}/chat/?node={chat_id}", wait_until="domcontentloaded", timeout=60000)
            return True
        except: return False

    @browser_action
    def get_chat_details(self, chat_id):
        """Парсит подробности чата: историю и инфо о юзере."""
        if self.offline: return {"messages": [{"user": "System", "text": "Offline Mode"}], "user_info": None}
        try:
            self.page.goto(f"{self.base_url}/chat/?node={chat_id}", wait_until="domcontentloaded", timeout=60000)
            # Ждем появления сообщений, но не падаем если их нет (пустой чат)
            try:
                self.page.wait_for_selector(".chat-msg-item", timeout=3000)
            except:
                pass
            
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            messages = []
            msg_elements = soup.select(".chat-msg-item")
            last_user = "Unknown"
            last_is_our = False

            if msg_elements:
                for msg_div in msg_elements:
                    text_div = msg_div.select_one(".chat-msg-text")
                    if not text_div: continue
                    
                    author_link = msg_div.select_one(".chat-msg-author-link")
                    if author_link:
                        last_user = author_link.text.strip()
                        last_is_our = f"/{self.user_id}/" in author_link.get("href", "")
                    else:
                        user_div = msg_div.select_one(".media-user-name")
                        if user_div:
                            last_user = "".join([t for t in user_div.find_all(string=True, recursive=False)]).strip()
                            last_is_our = False
                            
                    messages.append({
                        "user": last_user,
                        "text": text_div.text.strip(),
                        "is_our": last_is_our
                    })
                messages = messages[-10:]
            
            # Получаем инфо о пользователе
            user_info = self.get_user_info(chat_id=chat_id)
            
            return {"messages": messages, "user_info": user_info}
        except Exception as e:
            return {"error": str(e)}

    @browser_action
    def get_user_info(self, chat_id=None, user_id=None):
        """Парсит информацию о пользователе для оценки рисков."""
        if self.offline: return {"reg_date": "01.01.2000", "reviews": 999, "is_new": False}
        
        try:
            # Если дан chat_id, сначала заходим в чат, чтобы найти user_id
            if chat_id and not user_id:
                self.page.goto(f"{self.base_url}/chat/?node={chat_id}", wait_until="domcontentloaded")
                # Ищем ссылку на профиль в заголовке чата
                user_link = self.page.query_selector("a[href*='/users/']")
                if user_link:
                    href = user_link.get_attribute("href")
                    user_id = href.split('/')[-2]
            
            if not user_id: return None
            
            self.page.goto(f"{self.base_url}/users/{user_id}/", wait_until="domcontentloaded")
            soup = BeautifulSoup(self.page.content(), 'html.parser')
            
            # Парсинг даты регистрации
            reg_date_text = "Неизвестно"
            param_items = soup.find_all('div', class_='param-item')
            for item in param_items:
                h5 = item.find('h5')
                if h5 and "Дата регистрации" in h5.text:
                    reg_date_text = item.find('div', class_='text-nowrap').text.strip()
                    break
            
            # Парсинг отзывов
            reviews_count = 0
            review_link = soup.find('a', href=lambda x: x and '/reviews' in x)
            if review_link:
                import re
                match = re.search(r'(\d+)', review_link.text)
                if match:
                    reviews_count = int(match.group(1))
            
            # Определение "новорега"
            # Если зарегистрирован сегодня/вчера или менее 3 дней назад и 0 отзывов
            is_new = False
            low_reg = reg_date_text.lower()
            if "сегодня" in low_reg or "вчера" in low_reg:
                is_new = True
            elif "дня" in low_reg or "дн." in low_reg:
                try:
                    days = int(re.search(r'(\d+)', low_reg).group(1))
                    if days <= 3: is_new = True
                except: pass
            
            return {
                "id": user_id,
                "reg_date": reg_date_text.split('\n')[0].strip(),
                "reviews": reviews_count,
                "is_new": is_new and reviews_count == 0
            }
        except Exception as e:
            return None

    def refund_order(self, order_id):
        if self.offline: return True, "Refunded (Offline)"
        self.chaos_delay("click") 
        try:
            js_refund = f"""
            fetch('/orders/refund', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' }},
                body: 'id={order_id}&csrf_token={self.csrf_token}'
            }}).then(r => r.json())
            """
            resp = self.page.evaluate(js_refund)
            if resp.get('error'): return False, resp.get('msg', 'Ошибка возврата')
            return True, "Успешно"
        except Exception as e: return False, str(e)

    @browser_action
    def render_dashboard(self, html_content):
        """Рендерит HTML-дашборд и делает скриншот."""
        if self.offline: return None
        try:
            # Создаем временный файл
            temp_path = os.path.abspath("temp_stats.html")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            # Создаем новую вкладку, чтобы не портить основную страницу FunPay
            page = self.context.new_page()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(f"file://{temp_path}", wait_until="networkidle")
            
            # Ждем готовности (маркер .loaded ставится в JS после рендера графиков)
            try:
                page.wait_for_selector(".loaded", timeout=5000)
            except:
                pass
            
            # Делаем скриншот только контейнера
            container = page.query_selector("#dashboard")
            output_path = os.path.abspath("stats_render.png")
            if container:
                container.screenshot(path=output_path)
            else:
                page.screenshot(path=output_path)
                
            page.close()
            # os.remove(temp_path) # Можно оставить для отладки или удалять
            return output_path
        except Exception as e:
            print(f"Error rendering stats: {e}")
            return None
