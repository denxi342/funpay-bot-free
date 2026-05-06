from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup
import json
import time
import random
import os

class FunPayClient:
    def __init__(self, golden_key, user_agent, proxies=None, offline=False):
        self.golden_key = golden_key
        self.user_agent = user_agent
        self.proxies = proxies
        self.offline = offline
        self.base_url = "https://funpay.com"
        
        self.playwright = None
        self.browser = None
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

    def start_browser(self):
        """Запускает скрытый браузер с защитой от детекции."""
        if self.offline:
            self.csrf_token = "offline_token"
            self.user_id = "1234567"
            return

        self.playwright = sync_playwright().start()
        
        # Настройка прокси для Playwright
        launch_kwargs = {"headless": True} # Скрытый режим
        if self.proxies:
            # Формат: {'server': 'http://ip:port', 'username': 'user', 'password': 'pwd'}
            # Если у тебя строка "http://user:pass@ip:port", ее надо распарсить
            if isinstance(self.proxies, dict) and 'http' in self.proxies:
                proxy_str = self.proxies['http']
                if '@' in proxy_str:
                    auth, server = proxy_str.replace('http://', '').split('@')
                    user, pwd = auth.split(':')
                    launch_kwargs["proxy"] = {"server": f"http://{server}", "username": user, "password": pwd}
                else:
                    launch_kwargs["proxy"] = {"server": proxy_str}

        self.browser = self.playwright.chromium.launch(**launch_kwargs)
        
        # Создаем контекст с нужным User-Agent
        self.context = self.browser.new_context(
            user_agent=self.user_agent,
            viewport={'width': 1920, 'height': 1080}
        )
        
        # Добавляем куки
        self.context.add_cookies([{
            "name": "golden_key",
            "value": self.golden_key,
            "domain": "funpay.com",
            "path": "/"
        }])
        
        self.page = self.context.new_page()
        # Применяем Stealth (маскировку)
        stealth_sync(self.page)

    def close(self):
        """Закрывает браузер."""
        if self.page: self.page.close()
        if self.browser: self.browser.close()
        if self.playwright: self.playwright.stop()

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
        hours = re.search(r'(\d+)\s*(час|часа|часов)', msg)
        minutes = re.search(r'(\d+)\s*(минут|минуту|минуты)', msg)
        seconds = re.search(r'(\d+)\s*(секунд|секунду|секунды|сек)', msg)
        h = int(hours.group(1)) if hours else 0
        m = int(minutes.group(1)) if minutes else 0
        s = int(seconds.group(1)) if seconds else 0
        return h * 3600 + m * 60 + s

    def check_authorization(self):
        if self.offline: return True, "Offline_User"
        try:
            self.page.goto(self.base_url, wait_until="networkidle", timeout=60000)
            
            # Извлекаем CSRF
            app_data_raw = self.page.evaluate("() => document.body.getAttribute('data-app-data')")
            if app_data_raw:
                try:
                    app_data = json.loads(app_data_raw)
                    self.csrf_token = app_data.get('csrf-token')
                except: pass
            
            # Ищем юзернейм
            user_link = self.page.query_selector('.user-link-name')
            if user_link:
                name = user_link.inner_text().strip()
                # Извлекаем ID из ссылки
                href = self.page.evaluate("() => document.querySelector('.user-link-name').parentElement.getAttribute('href')")
                if href:
                    self.user_id = href.strip('/').split('/')[-1]
                return True, name
            return False, "Не удалось найти имя пользователя. Проверьте golden_key."
        except Exception as e:
            return False, f"Ошибка браузера: {e}"

    def get_stats(self):
        if self.offline: return {"balance": "100.00 ₽", "unread_chats": "0", "active_sales": "0"}
        try:
            self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
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

    def get_categories_to_bump(self):
        if self.offline: return True, 0
        if not self.user_id: return False, "User ID не найден"
        try:
            self.page.goto(f"{self.base_url}/users/{self.user_id}/", wait_until="networkidle")
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
                self.page.goto(trade_url, wait_until="domcontentloaded")
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

    def smart_bump_category(self, cat):
        if self.offline: return True, "Успешно (Offline)"
        try:
            node_id = str(cat['node_id'])
            game_id = cat['game_id']
            now = time.time()
            
            if node_id not in self.bump_state:
                self.bump_state[node_id] = {"next_up_time": 0}
            
            # В Playwright мы будем использовать POST через page.evaluate для имитации JS на странице
            # Это САМЫЙ беспалевный способ, так как запрос летит от имени открытого браузера со всеми куками.
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
                if wait_seconds > 0:
                    self.bump_state[node_id]["next_up_time"] = now + wait_seconds + random.randint(30, 90)
                    self.save_bump_state()
                    return False, f"Рано. Ждать {wait_seconds}с"
                return False, f"Ошибка: {msg}"
            
            # Если пришла модалка (второй шаг поднятия)
            if 'modal' in data:
                # В современных реалиях мы просто имитируем нажатие "Поднять всё" в модалке
                # Чтобы не усложнять, отправим второй запрос с node_ids
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(data['modal'], 'html.parser')
                nodes = [inp.get('value') for inp in soup.find_all('input', {'type': 'checkbox'}) if inp.get('value')]
                
                if nodes:
                    nodes_payload = "&".join([f"node_ids%5B%5D={n}" for n in nodes])
                    js_step2 = f"""
                    fetch('/lots/raise', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: 'game_id={game_id}&node_id={node_id}&csrf_token={self.csrf_token}&{nodes_payload}'
                    }}).then(r => r.json())
                    """
                    data2 = self.page.evaluate(js_step2)
                    if data2.get('error'):
                        return False, data2.get('msg', 'Ошибка 2 шага')
                
            self.bump_state[node_id]["next_up_time"] = now + 14400 + random.randint(60, 300)
            self.save_bump_state()
            return True, "Успешно поднято!"
        except Exception as e:
            return False, f"Сбой браузера: {e}"

    def get_new_messages(self):
        if self.offline: return []
        try:
            self.page.goto(f"{self.base_url}/chat/", wait_until="domcontentloaded")
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
                    self.last_seen_messages[node_id] = msg_id
            return new_msgs
        except: return []

    def send_message(self, chat_id, text):
        if self.offline: return True, "Отправлено (Offline)"
        try:
            # Имитируем отправку через внутренний API страницы
            payload = json.dumps({"action": "chat_message", "data": {"node": chat_id, "content": text}})
            js_send = f"""
            fetch('/runner/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' }},
                body: 'request={payload}&csrf_token={self.csrf_token}'
            }}).then(r => r.json())
            """
            resp = self.page.evaluate(js_send)
            if resp.get('response', {}).get('error'):
                return False, str(resp['response']['error'])
            return True, "Отправлено"
        except Exception as e:
            return False, str(e)

    def get_active_orders(self):
        if self.offline: return []
        try:
            self.page.goto(f"{self.base_url}/orders/trade", wait_until="domcontentloaded")
            soup = BeautifulSoup(self.page.content(), 'html.parser')
            orders = []
            for item in soup.find_all('a', class_='tc-item'):
                status = item.find('div', class_='tc-status').text.strip()
                if "Оплачен" in status:
                    order_id = item.find('div', class_='tc-order').text.strip().replace('#', '')
                    title = item.find('div', class_='order-desc').find('div').text.strip()
                    buyer = item.find('div', class_='media-user-name').text.strip()
                    price = item.find('div', class_='tc-price').text.strip()
                    orders.append({'order_id': order_id, 'buyer': buyer, 'title': title, 'price': price, 'url': item.get('href')})
            return orders
        except: return []

    def get_new_orders(self):
        # Аналогично get_active_orders, но с проверкой seen_orders
        all_active = self.get_active_orders()
        new = []
        for o in all_active:
            if o['order_id'] not in self.seen_orders:
                self.seen_orders.add(o['order_id'])
                new.append(o)
        return new

    def mark_chat_read(self, chat_id):
        if self.offline: return True
        try:
            self.page.goto(f"{self.base_url}/chat/?node={chat_id}", wait_until="domcontentloaded")
            return True
        except: return False

    def refund_order(self, order_id):
        if self.offline: return True, "Refunded (Offline)"
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
