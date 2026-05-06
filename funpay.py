import requests
from bs4 import BeautifulSoup
import json
import time

class FunPayClient:
    def __init__(self, golden_key, user_agent):
        self.session = requests.Session()
        
        # Настраиваем авто-повтор при сбоях сети (Таймауты, разрывы)
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.session.cookies.set("golden_key", golden_key, domain=".funpay.com")
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://funpay.com/"
        })
        self.base_url = "https://funpay.com"
        self.csrf_token = None
        self.user_id = None
        self.categories_to_bump = [] # Список dict'ов: {'game_id': x, 'node_id': y, 'name': z}
        self.last_seen_messages = {} # node_id -> last_node_msg_id
        self.seen_orders = set() # Множество order_id, о которых уже уведомили
        self.bump_state_file = 'bump_state.json'
        self.bump_state = self.load_bump_state()

    def load_bump_state(self):
        import os
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
        """Проверяет токен, получает CSRF и User ID."""
        try:
            response = self.session.get(self.base_url, timeout=20)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. Извлекаем CSRF токен из data-app-data
            body_tag = soup.find('body')
            if body_tag and body_tag.has_attr('data-app-data'):
                try:
                    app_data = json.loads(body_tag['data-app-data'])
                    self.csrf_token = app_data.get('csrf-token')
                except json.JSONDecodeError:
                    pass
            
            # 2. Ищем элемент с именем пользователя
            user_link = soup.find('div', class_='user-link-name')
            if user_link:
                # Извлекаем User ID из ссылки на профиль
                parent_a = user_link.find_parent('a')
                if parent_a and 'href' in parent_a.attrs:
                    href = parent_a['href']
                    parts = [p for p in href.split('/') if p]
                    if parts:
                        self.user_id = parts[-1]
                
                return True, user_link.text.strip()
            else:
                return False, "Не удалось найти имя пользователя. Возможно, golden_key недействителен."

        except Exception as e:
            return False, "Не удалось получить CSRF токен или ID пользователя"

    def get_stats(self):
        """Парсит баланс, непрочитанные сообщения и активные заказы с главной страницы."""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=20)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Баланс
            balance_elem = soup.select_one('.badge-balance')
            balance = balance_elem.text.strip() if balance_elem else "0"
            
            # Непрочитанные сообщения
            chat_elem = soup.select_one('.badge-chat')
            unread_chats = chat_elem.text.strip() if chat_elem and 'hidden' not in chat_elem.get('class', []) else "0"
            
            # Активные продажи
            trade_elem = soup.select_one('.badge-trade')
            active_sales = trade_elem.text.strip() if trade_elem and 'hidden' not in trade_elem.get('class', []) else "0"
            
            return {
                "balance": balance,
                "unread_chats": unread_chats,
                "active_sales": active_sales
            }
        except Exception as e:
            print(f"DEBUG GET_STATS EXCEPTION: {e}")
            return {"balance": "?", "unread_chats": "?", "active_sales": "?"}

    def get_categories_to_bump(self):
        """Сканирует профиль пользователя и находит все категории для поднятия."""
        if not self.user_id:
            return False, "User ID не найден. Сначала пройдите авторизацию."
        
        try:
            import re
            profile_url = f"{self.base_url}/users/{self.user_id}/"
            response = self.session.get(profile_url, timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Собираем все уникальные ссылки на категории из профиля
            category_urls = set()
            for a_tag in soup.find_all('a'):
                href = a_tag.get('href', '')
                if not href: continue
                
                # Ищем ссылки вида /lots/123/, /chips/456/, /accounts/789/
                if re.search(r'/[a-zA-Z\-]+/\d+/?$', href):
                    if not any(x in href for x in ['/users/', '/trade/', '/orders/', '/chat/']):
                        url = href if href.startswith('http') else self.base_url + href
                        cat_name = a_tag.text.strip() or "Категория"
                        category_urls.add((url, cat_name))
            
            nodes_found = set()
            self.categories_to_bump = []
            
            for cat_url, cat_name in category_urls:
                # Кнопка поднятия теперь находится на странице редактирования лотов (/trade)
                trade_url = cat_url
                if not trade_url.endswith('/'):
                    trade_url += '/'
                if not trade_url.endswith('/trade') and not trade_url.endswith('/trade/'):
                    trade_url += 'trade'
                    
                cat_response = self.session.get(trade_url, timeout=20)
                cat_soup = BeautifulSoup(cat_response.text, 'html.parser')
                
                # Кнопка "Поднять предложения" имеет класс js-lot-raise
                raise_btn = cat_soup.find('button', class_='js-lot-raise')
                if raise_btn and raise_btn.has_attr('data-game') and raise_btn.has_attr('data-node'):
                    game_id = raise_btn['data-game']
                    node_id = raise_btn['data-node']
                    
                    if node_id not in nodes_found:
                        nodes_found.add(node_id)
                        self.categories_to_bump.append({
                            'game_id': game_id,
                            'node_id': node_id,
                            'name': cat_name
                        })
                time.sleep(0.5) # Небольшая задержка
                
            return True, len(self.categories_to_bump)
            
        except Exception as e:
            return False, str(e)

    def bump_all(self):
        """Поднимает все найденные категории."""
        if not self.csrf_token:
            return False, "Отсутствует CSRF токен"
            
        if not self.categories_to_bump:
            return False, "Нет категорий для поднятия"

        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        
        results = []
        for cat in self.categories_to_bump:
            payload = {
                "game_id": cat['game_id'],
                "node_id": cat['node_id'],
                "csrf_token": self.csrf_token
            }
            try:
                # Отправляем POST запрос на поднятие
                response = self.session.post(f"{self.base_url}/lots/raise", data=payload, headers=headers, timeout=20)
                data = response.json()
                
                if data.get('error'):
                    results.append(f"Ошибка ({cat['name']}): {data.get('msg', 'Неизвестная ошибка')}")
                else:
                    results.append(f"Успех ({cat['name']})")
                    
            except Exception as e:
                results.append(f"Сбой сети ({cat['name']}): {str(e)}")
            
            time.sleep(1) # Пауза между поднятиями разных категорий
            
        return True, results

    def smart_bump_category(self, cat):
        import time
        import random
        
        if not self.csrf_token:
            return False, "Отсутствует CSRF токен"
            
        node_id = str(cat['node_id'])
        game_id = cat['game_id']
        name = cat['name']
        
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        
        now = time.time()
        
        if node_id not in self.bump_state:
            self.bump_state[node_id] = {"next_up_time": 0, "last_known_cooldown": None}
            
        try:
            # Шаг 1: Получаем модалку с чекбоксами
            step1_payload = {
                "game_id": game_id,
                "node_id": node_id,
                "csrf_token": self.csrf_token
            }
            response = self.session.post(f"{self.base_url}/lots/raise", data=step1_payload, headers=headers, timeout=20)
            data = response.json()
            
            if not isinstance(data, dict):
                self.bump_state[node_id]["next_up_time"] = now + 15 * 60
                self.save_bump_state()
                return False, "Неизвестный ответ сервера"

            # Если сразу пришла ошибка (кулдаун ещё не истёк)
            if data.get('error'):
                msg = data.get('msg', '') or data.get('message', '')
                wait_seconds = self.parse_wait_time(msg)
                if wait_seconds > 0:
                    self.bump_state[node_id]["last_known_cooldown"] = wait_seconds
                    buffer = random.randint(30, 120)
                    self.bump_state[node_id]["next_up_time"] = now + wait_seconds + buffer
                    self.save_bump_state()
                    return False, f"Рано. Ожидание: {wait_seconds} сек"
                else:
                    self.bump_state[node_id]["next_up_time"] = now + 15 * 60
                    self.save_bump_state()
                    return False, f"Ошибка: {msg}"

            # Если пришла модалка — парсим и отправляем шаг 2
            if 'modal' in data:
                modal_html = data['modal']
                modal_soup = BeautifulSoup(modal_html, 'html.parser')
                
                # Получаем game_id и node_id из raise-box
                raise_box = modal_soup.find('div', class_='raise-box')
                rb_game = raise_box.get('data-game', game_id) if raise_box else game_id
                rb_node = raise_box.get('data-node', node_id) if raise_box else node_id
                
                # Собираем все node_id из чекбоксов (берём ВСЕ, как при нажатии "Поднять предложения")
                all_checkbox_nodes = []
                for inp in modal_soup.find_all('input', {'type': 'checkbox'}):
                    val = inp.get('value')
                    if val:
                        all_checkbox_nodes.append(val)
                
                if not all_checkbox_nodes:
                    self.bump_state[node_id]["next_up_time"] = now + 15 * 60
                    self.save_bump_state()
                    return False, "Не найдены категории в модалке"
                
                # Шаг 2: Фактическое поднятие
                # FunPay JS: Lots.raiseOffers(game_id, node_id, node_ids_array)
                # Отправляет: {game_id: X, node_id: Y, node_ids: [A, B, ...]}
                # jQuery сериализует массив как node_ids[]=A&node_ids[]=B
                step2_parts = [
                    f"game_id={rb_game}",
                    f"node_id={rb_node}",
                    f"csrf_token={self.csrf_token}"
                ]
                for nid in all_checkbox_nodes:
                    step2_parts.append(f"node_ids%5B%5D={nid}")
                
                step2_data = "&".join(step2_parts)
                
                raise_response = self.session.post(
                    f"{self.base_url}/lots/raise",
                    data=step2_data,
                    headers=headers,
                    timeout=20
                )
                raise_result = raise_response.json()
                
                # Проверяем результат
                if isinstance(raise_result, dict):
                    if raise_result.get('error'):
                        msg = raise_result.get('msg', '') or raise_result.get('message', '')
                        wait_seconds = self.parse_wait_time(msg)
                        if wait_seconds > 0:
                            self.bump_state[node_id]["last_known_cooldown"] = wait_seconds
                            buffer = random.randint(30, 120)
                            self.bump_state[node_id]["next_up_time"] = now + wait_seconds + buffer
                            self.save_bump_state()
                            return False, f"Рано. Ожидание: {wait_seconds} сек"
                        else:
                            self.bump_state[node_id]["next_up_time"] = now + 15 * 60
                            self.save_bump_state()
                            return False, f"Ошибка поднятия: {msg}"
                    
                    if 'modal' in raise_result:
                        # Получили модалку снова — что-то пошло не так
                        self.bump_state[node_id]["next_up_time"] = now + 15 * 60
                        self.save_bump_state()
                        return False, "Ошибка: сервер вернул модалку повторно"
                
                # Успешно подняли!
                cooldown = 4 * 3600
                buffer = random.randint(30, 120)
                self.bump_state[node_id]["next_up_time"] = now + cooldown + buffer
                self.bump_state[node_id]["last_known_cooldown"] = cooldown
                self.save_bump_state()
                nodes_str = ", ".join(all_checkbox_nodes)
                return True, f"Поднято ({nodes_str})! Следующий через ~4ч."

            # Без модалки и без ошибки — значит сразу подняли
            cooldown = 4 * 3600
            buffer = random.randint(30, 120)
            self.bump_state[node_id]["next_up_time"] = now + cooldown + buffer
            self.bump_state[node_id]["last_known_cooldown"] = cooldown
            self.save_bump_state()
            return True, "Успешно поднято! Следующий подъем через 4 часа."
                
        except Exception as e:
            self.bump_state[node_id]["next_up_time"] = now + 5 * 60
            self.save_bump_state()
            return False, f"Сбой: {e}"
    def get_historical_orders(self):
        """Возвращает последние заказы (Оплачен и Закрыт) со страницы продаж."""
        if not self.csrf_token: return []
        try:
            response = self.session.get(f"{self.base_url}/orders/trade", timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            orders = []
            for item in soup.find_all('a', class_='tc-item'):
                status_div = item.find('div', class_='tc-status')
                if not status_div: continue
                status = status_div.text.strip()
                if "Оплачен" in status or "Закрыт" in status:
                    order_div = item.find('div', class_='tc-order')
                    order_id = order_div.text.strip().replace('#', '') if order_div else "?"
                    desc_div = item.find('div', class_='order-desc')
                    title = desc_div.find('div').text.strip() if desc_div and desc_div.find('div') else "Неизвестный товар"
                    user_div = item.find('div', class_='media-user-name')
                    buyer = user_div.text.strip() if user_div else "Неизвестный"
                    price_div = item.find('div', class_='tc-price')
                    price = price_div.text.strip() if price_div else "?"
                    orders.append({
                        'order_id': order_id,
                        'buyer': buyer,
                        'title': title,
                        'price': price,
                        'url': item.get('href', f"{self.base_url}/orders/{order_id}/")
                    })
            return orders
        except Exception as e:
            print(f"Ошибка получения исторических заказов: {e}")
            return []


    def get_active_orders(self):
        """Возвращает все текущие оплаченные заказы (для списка команд)."""
        if not self.csrf_token: return []
        try:
            response = self.session.get(f"{self.base_url}/orders/trade", timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            orders = []
            for item in soup.find_all('a', class_='tc-item'):
                status_div = item.find('div', class_='tc-status')
                if not status_div: continue
                if "Оплачен" in status_div.text.strip():
                    order_div = item.find('div', class_='tc-order')
                    order_id = order_div.text.strip().replace('#', '') if order_div else "?"
                    desc_div = item.find('div', class_='order-desc')
                    title = desc_div.find('div').text.strip() if desc_div and desc_div.find('div') else "Неизвестный товар"
                    user_div = item.find('div', class_='media-user-name')
                    buyer = user_div.text.strip() if user_div else "Неизвестный"
                    price_div = item.find('div', class_='tc-price')
                    price = price_div.text.strip() if price_div else "?"
                    orders.append({
                        'order_id': order_id,
                        'buyer': buyer,
                        'title': title,
                        'price': price,
                        'url': item.get('href', f"{self.base_url}/orders/{order_id}/")
                    })
            return orders
        except Exception as e:
            print(f"Ошибка получения актуальных заказов: {e}")
            return []

    def get_new_orders(self):
        """Проверяет новые оплаченные заказы."""
        if not self.csrf_token:
            return []
            
        try:
            response = self.session.get(f"{self.base_url}/orders/trade", timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            new_orders = []
            order_items = soup.find_all('a', class_='tc-item')
            
            for item in order_items:
                # Извлекаем ID заказа
                order_div = item.find('div', class_='tc-order')
                if not order_div: continue
                order_id = order_div.text.strip().replace('#', '')
                
                # Проверяем статус
                status_div = item.find('div', class_='tc-status')
                if not status_div: continue
                status = status_div.text.strip()
                
                # Нас интересуют только оплаченные заказы
                if "Оплачен" in status and order_id not in self.seen_orders:
                    self.seen_orders.add(order_id)
                    
                    # Извлекаем название товара
                    desc_div = item.find('div', class_='order-desc')
                    title = desc_div.find('div').text.strip() if desc_div and desc_div.find('div') else "Неизвестный товар"
                    
                    # Извлекаем покупателя
                    user_div = item.find('div', class_='media-user-name')
                    buyer = user_div.text.strip() if user_div else "Неизвестный"
                    
                    # Извлекаем цену
                    price_div = item.find('div', class_='tc-price')
                    price = price_div.text.strip() if price_div else "?"
                    
                    new_orders.append({
                        'order_id': order_id,
                        'buyer': buyer,
                        'title': title,
                        'price': price,
                        'url': item.get('href', f"{self.base_url}/orders/{order_id}/")
                    })
                    
            return new_orders
        except Exception as e:
            print(f"Ошибка получения заказов: {e}")
            return []

    def get_new_messages(self):
        """Проверяет новые сообщения на странице чатов."""
        if not self.csrf_token:
            return []
            
        try:
            response = self.session.get(f"{self.base_url}/chat/", timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            new_msgs = []
            is_first_run = len(self.last_seen_messages) == 0
            
            for contact in soup.find_all('a', class_='contact-item'):
                node_id = contact.get('data-id')
                msg_div = contact.find('div', class_='contact-item-message')
                if not node_id or not msg_div:
                    continue
                    
                msg_id = contact.get('data-node-msg') or msg_div.get('data-node-msg')
                user_msg_id = contact.get('data-user-msg')
                
                # Проверяем, прочитан ли чат. Новые сообщения от покупателей всегда делают чат непрочитанным.
                # Если чат не имеет класса unread, то либо мы его прочитали, либо это наше сообщение.
                classes = contact.get('class', [])
                is_unread = 'unread' in classes
                
                # Дополнительно проверим префиксы "Вы:", "You:", "Ви:"
                text = msg_div.text.strip()
                text_lower = text.lower()
                is_our_msg = any(text_lower.startswith(prefix) for prefix in ["вы:", "you:", "ви:"])
                
                # Если это наше сообщение или чат уже прочитан - мы его не обрабатываем
                if not is_unread or is_our_msg:
                    self.last_seen_messages[node_id] = msg_id
                    continue
                
                if node_id not in self.last_seen_messages or self.last_seen_messages[node_id] != msg_id:
                    if not is_first_run:
                        user = contact.find('div', class_='media-user-name')
                        user_name = user.text.strip() if user else "Неизвестный"
                        
                        new_msgs.append({
                            'chat_id': node_id,
                            'msg_id': msg_id,
                            'user': user_name,
                            'text': text
                        })
                    
                    self.last_seen_messages[node_id] = msg_id
                    
            return new_msgs
            
        except Exception as e:
            print(f"Ошибка получения сообщений: {e}")
            return []

    def mark_chat_read(self, chat_id):
        """Отмечает чат как прочитанный, загружая его страницу."""
        try:
            self.session.get(f"{self.base_url}/chat/?node={chat_id}", timeout=20)
            return True
        except:
            return False

    def send_message(self, chat_id, text):
        """Отправляет сообщение через POST-запрос."""
        if not self.csrf_token:
            return False, "CSRF token not found"
            
        try:
            headers = {
                "x-requested-with": "XMLHttpRequest",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            
            # Формируем JSON-запрос для runner
            payload = {
                "request": json.dumps({
                    "action": "chat_message",
                    "data": {
                        "node": chat_id,
                        "content": text
                    }
                }),
                "csrf_token": self.csrf_token
            }
            
            response = self.session.post(f"{self.base_url}/runner/", data=payload, headers=headers, timeout=20)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    error_msg = resp_json.get("response", {}).get("error")
                    if error_msg is not None:
                        # FunPay иногда возвращает error: null при успехе
                        return False, str(error_msg)
                    return True, "Отправлено"
                except:
                    return True, "Отправлено (ошибка парсинга)"
            return False, f"HTTP {response.status_code}"
            
        except Exception as e:
            return False, str(e)

    def refund_order(self, order_id):
        if not self.csrf_token:
            return False, "Отсутствует CSRF токен"
            
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        payload = {
            "id": order_id,
            "csrf_token": self.csrf_token
        }
        try:
            response = self.session.post(f"{self.base_url}/orders/refund", data=payload, headers=headers, timeout=20)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get("error"):
                    return False, str(resp_json.get("msg", "Неизвестная ошибка"))
                return True, "Успешно"
            return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, f"Ошибка соединения: {e}"
