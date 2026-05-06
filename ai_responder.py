import time
import re
import requests
import json
from colorama import Fore

class AIResponder:
    def __init__(self, api_key, log_func):
        self.log = log_func
        self.is_active = True
        self.api_key = api_key
        
        self.users_state = {}  # chat_id -> {'count': 0, 'last_time': 0, 'burst': []}
        self.cache = {}        # normalized_question -> answer
        
        if self.api_key:
            self.log("[+] Модуль ИИ-Автоответчика загружен (OpenRouter)", color=Fore.GREEN)
        else:
            self.log("[-] ИИ-Автоответчик отключен (нет API ключа)", color=Fore.YELLOW)
            
        self.critical_triggers = ['возврат', 'бан', 'обман', 'манибэк', 'скам', 'мошенник']
        self.normal_triggers = ['не работает', 'ошибка', 'пароль не подходит', 'не могу зайти', 'не пускает', 'проблема', 'замени', 'неверный', 'не получается']

    def detect_problem(self, text):
        norm = text.lower()
        for t in self.critical_triggers:
            if t in norm:
                return "critical"
        for t in self.normal_triggers:
            if t in norm:
                return "normal"
        return None

    def normalize_text(self, text):
        # Удаляем знаки препинания, переводим в нижний регистр
        text = text.lower()
        return re.sub(r'[^\w\s]', '', text).strip()

    def should_trigger(self, text):
        norm = self.normalize_text(text)
        words = norm.split()
        
        # Осмысленные вопросы (длинные)
        if len(words) > 3:
            return True
            
        # Короткие сообщения с ключевыми словами
        keywords = ['где', 'когда', 'как', 'выдал', 'пароль', 'вопрос', 'тут', 'ау', 'здравствуйте', 'привет']
        for kw in keywords:
            if kw in words:
                return True
                
        return False

    def check_spam(self, chat_id):
        now = time.time()
        if chat_id not in self.users_state:
            self.users_state[chat_id] = {'count': 0, 'last_time': now, 'burst': [now]}
            return False, False # is_spam, should_ignore
            
        state = self.users_state[chat_id]
        
        # Сброс счетчика при простое 15 минут
        if now - state['last_time'] > 15 * 60:
            state['count'] = 0
            state['burst'] = []
            
        state['last_time'] = now
        
        # Проверка Burst (много сообщений за короткое время)
        state['burst'].append(now)
        # Оставляем только те, что были за последние 15 секунд
        state['burst'] = [t for t in state['burst'] if now - t <= 15]
        
        if len(state['burst']) >= 3:
             # Спамер. Возвращаем is_spam=True
             return True, False
             
        # Проверка лимита ответов (адаптивно)
        # Базово 3, максимум 5
        max_replies = 5
        
        if state['count'] >= max_replies:
             return True, True # is_spam=True, should_ignore=True (уже перевели на оператора)

        return False, False

    def build_context(self, chat_id, user_name, active_orders):
        # Проверяем, есть ли пользователь в активных заказах
        user_orders = [o for o in active_orders if o['buyer'].lower() == user_name.lower()]
        if user_orders:
            titles = ", ".join([o['title'] for o in user_orders])
            return f"Этот покупатель УЖЕ ОПЛАТИЛ товар '{titles}'. Успокой его, скажи, что продавец скоро все выдаст (обычно это занимает 5-15 минут)."
        else:
            return "Это потенциальный покупатель, он еще ничего не купил. Отвечай вежливо и предложи задать вопросы по товару."

    def process_message(self, msg_data, active_orders):
        if not self.is_active or not self.api_key:
            return None
            
        chat_id = msg_data['chat_id']
        user = msg_data['user']
        text = msg_data['text']
        
        if not self.should_trigger(text):
            return None
            
        is_spam, should_ignore = self.check_spam(chat_id)
        
        if should_ignore:
            return None # Мы уже сказали, что переводим на оператора
            
        state = self.users_state.get(chat_id)
        if is_spam:
            # Отправляем сообщение о переводе на оператора
            state['count'] = 999 # блокируем дальнейшие ответы
            return "Я вижу много сообщений, поэтому временно перевел диалог на живого продавца. Пожалуйста, ожидайте, он скоро ответит!"
            
        norm_text = self.normalize_text(text)
        
        if norm_text in self.cache:
            state['count'] += 1
            return self.cache[norm_text]
            
        # Запрос к OpenRouter
        context = self.build_context(chat_id, user, active_orders)
        system_prompt = f"""
Ты — живой продавец-геймер на площадке FunPay. 
Контекст: {context}

Правила ответа:
1. Отвечай коротко: максимум 1-2 предложения.
2. Не используй воду, сложные списки или формальные фразы вроде "Чем могу помочь?".
3. Пиши как живой человек (можно использовать простые смайлы).
4. Не придумывай информацию, которой нет в контексте. Если спрашивают пароль или ссылку — отвечай, что продавец скинет их в ближайшее время.
"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://funpaybot.local",
                "X-Title": "FunPayBot"
            }
            data = {
                "model": "openrouter/free",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            }
            
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            answer = res_json['choices'][0]['message']['content'].strip()
            
            # Убираем кавычки если ИИ их добавил
            if answer.startswith('"') and answer.endswith('"'):
                answer = answer[1:-1]
                
            self.cache[norm_text] = answer
            state['count'] += 1
            return answer
        except requests.exceptions.RequestException as e:
            err_text = e.response.text if (e.response is not None) else str(e)
            self.log(f"Ошибка OpenRouter API (Сеть): {e} | Детали: {err_text}", color=Fore.RED)
            return None
        except Exception as e:
            self.log(f"Ошибка OpenRouter API (Внутренняя): {e}", color=Fore.RED)
            return None

    def generate_troubleshooting_response(self, chat_id, user, text, active_orders):
        if not self.is_active or not self.api_key:
            return None
            
        context = self.build_context(chat_id, user, active_orders)
        system_prompt = f"""
Ты — первая линия технической поддержки магазина на FunPay.
Контекст: {context}

Твоя задача — ТОЛЬКО уточнить детали проблемы у покупателя.
ЖЕСТКИЕ ПРАВИЛА:
1. НИКОГДА не обещай возврат средств (манибэк) или замену товара.
2. Не давай никаких гарантий решения проблемы.
3. Не признавай вину магазина (не пиши "наш косяк", "извините за нерабочий товар").
4. Не пиши лишних извинений. Максимум одно "сожалею о трудностях".
5. Задавай наводящие вопросы, чтобы понять суть (например: 'Какая именно ошибка появляется?', 'Вы пробовали зайти через другой браузер?', 'Пришлите скриншот ошибки').
6. Общайся вежливо, профессионально и коротко (1-2 предложения).
"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://funpaybot.local",
                "X-Title": "FunPayBot"
            }
            data = {
                "model": "openrouter/free",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            }
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            answer = res_json['choices'][0]['message']['content'].strip()
            
            if answer.startswith('"') and answer.endswith('"'):
                answer = answer[1:-1]
            return answer
        except Exception as e:
            self.log(f"Ошибка генерации ответа ТП: {e}", color=Fore.RED)
            return None
