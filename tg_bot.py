import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
import time
import json
import os
from colorama import Fore

class TelegramManager:
    def __init__(self, token, admin_id, funpay_client, log_func, ai_responder=None):
        self.bot = telebot.TeleBot(token)
        self.admin_id = str(admin_id)
        self.client = funpay_client
        self.log = log_func
        self.ai = ai_responder
        self.is_running = False
        self.templates_file = 'templates.json'
        self.templates = self.load_templates()
        self.sales_file = 'sales.json'
        self.sales = self.load_sales()
        self.user_states = {} # Хранит состояния пользователей
        self.active_problems = {} # Хранит активные проблемы: {chat_id: {'msg_id': id, 'text': text}}
        
        self.setup_handlers()

    def load_templates(self):
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return []

    def save_templates(self):
        with open(self.templates_file, 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=4)

    def load_sales(self):
        if os.path.exists(self.sales_file):
            try:
                with open(self.sales_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return []

    def save_sales(self):
        with open(self.sales_file, 'w', encoding='utf-8') as f:
            json.dump(self.sales, f, ensure_ascii=False, indent=4)

    def parse_price(self, price_str):
        import re
        clean_str = re.sub(r'[^\d.,]', '', price_str)
        clean_str = clean_str.replace(',', '.')
        try:
            return float(clean_str)
        except:
            return 0.0

    def add_sale(self, order_data):
        sale = {
            'order_id': order_data.get('order_id'),
            'title': order_data.get('title'),
            'buyer': order_data.get('buyer'),
            'price': self.parse_price(order_data.get('price', '0')),
            'timestamp': time.time()
        }
        self.sales.append(sale)
        self.save_sales()

    def log_problem_action(self, chat_id, user, user_msg, action_type, response_msg):
        """Логирует проблемы в текстовый файл для аналитики."""
        try:
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{now}] User: {user} (ChatID: {chat_id})\nПроблема: {user_msg}\nРешение ({action_type}): {response_msg}\n{'-'*50}\n"
            with open("problems_log.txt", "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            self.log(f"Ошибка записи в лог проблем: {e}", color=Fore.RED)

    def check_admin(self, user_id):
        return str(user_id) == self.admin_id

    def get_main_keyboard(self):
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            KeyboardButton("🟢 Статус"),
            KeyboardButton("🔄 Поднять лоты"),
            KeyboardButton("📋 Актуальные заказы"),
            KeyboardButton("💬 Шаблоны ответов")
        )
        
        ai_btn = "🤖 ИИ: ВКЛ" if (self.ai and self.ai.is_active) else "🤖 ИИ: ВЫКЛ"
        markup.add(KeyboardButton("📊 Статистика"), KeyboardButton(ai_btn))
        return markup

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def send_start(message: Message):
            if not self.check_admin(message.from_user.id): return
            self.bot.reply_to(message, "Добро пожаловать в панель управления ASHANOV! Выберите действие ниже:", reply_markup=self.get_main_keyboard())

        @self.bot.message_handler(func=lambda msg: msg.text in ["🤖 ИИ: ВКЛ", "🤖 ИИ: ВЫКЛ"])
        def toggle_ai(message: Message):
            if not self.check_admin(message.from_user.id): return
            if not self.ai:
                self.bot.reply_to(message, "❌ Модуль ИИ не подключен (проверьте GEMINI_API_KEY в config.py).")
                return
                
            self.ai.is_active = not self.ai.is_active
            status = "ВКЛЮЧЕН" if self.ai.is_active else "ВЫКЛЮЧЕН"
            self.bot.reply_to(message, f"🤖 Умный ИИ-Автоответчик теперь **{status}**.", parse_mode='Markdown', reply_markup=self.get_main_keyboard())

        @self.bot.message_handler(func=lambda msg: msg.text in ["🟢 Статус", "/status"])
        def send_status(message: Message):
            if not self.check_admin(message.from_user.id): return
            text = (
                "🟢 *Бот ASHANOV Активен*\n\n"
                f"👤 Пользователь: {self.client.user_id}\n"
                f"📦 Категорий загружено: {len(self.client.categories_to_bump)}"
            )
            self.bot.reply_to(message, text, parse_mode='Markdown', reply_markup=self.get_main_keyboard())

        @self.bot.message_handler(func=lambda msg: msg.text in ["📋 Актуальные заказы", "/orders"])
        def list_orders(message: Message):
            if not self.check_admin(message.from_user.id): return
            self.bot.reply_to(message, "🔄 Получаю список активных заказов...", reply_markup=self.get_main_keyboard())
            orders = self.client.get_active_orders()
            if not orders:
                self.bot.send_message(message.chat.id, "🛒 Нет активных неоплаченных заказов.")
                return
            
            self.bot.send_message(message.chat.id, f"📋 *Актуальные заказы ({len(orders)} шт.):*", parse_mode='Markdown')
            for o in orders:
                text = (
                    f"🛍 *Товар:* {o['title']}\n"
                    f"👤 *Покупатель:* {o['buyer']}\n"
                    f"💰 *Сумма:* {o['price']}\n"
                    f"🆔 *Заказ:* #{o['order_id']}\n\n"
                    f"🔗 [Перейти к заказу]({o['url']})"
                )
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text="⚠️ Вернуть деньги", callback_data=f"refund_{o['order_id']}"))
                self.bot.send_message(message.chat.id, text, parse_mode='Markdown', disable_web_page_preview=True, reply_markup=markup)

        @self.bot.message_handler(func=lambda msg: msg.text in ["🔄 Поднять лоты", "/bump"])
        def force_bump(message: Message):
            if not self.check_admin(message.from_user.id): return
            self.bot.reply_to(message, "🔄 Начинаю принудительное поднятие лотов...")
            success, results = self.client.bump_all()
            if success:
                self.bot.send_message(message.chat.id, "✅ Поднятие завершено. Проверьте консоль для деталей.")
            else:
                self.bot.send_message(message.chat.id, f"❌ Ошибка поднятия: {results}")

        @self.bot.message_handler(func=lambda msg: msg.text in ["📊 Статистика", "/stats"])
        def send_stats(message: Message):
            if not self.check_admin(message.from_user.id): return
            
            total_sales = len(self.sales)
            total_earned = sum(s['price'] for s in self.sales)
            
            now = time.time()
            today_sales = [s for s in self.sales if now - s['timestamp'] < 86400]
            today_count = len(today_sales)
            today_earned = sum(s['price'] for s in today_sales)
            
            from collections import Counter
            titles = [s['title'] for s in self.sales]
            top_title = Counter(titles).most_common(1)[0][0] if titles else "Нет продаж"
            
            text = (
                "📊 *Статистика продаж*\n\n"
                f"💵 *Заработано всего:* {total_earned:.2f} ₽\n"
                f"📈 *Всего продаж:* {total_sales} шт.\n\n"
                f"📅 *Продажи за 24 часа:*\n"
                f"— Количество: {today_count} шт.\n"
                f"— Сумма: {today_earned:.2f} ₽\n\n"
                f"🏆 *Топ товар:* {top_title}\n\n"
                f"💡 _Чтобы загрузить прошлые продажи с последней страницы FunPay, напишите_ `/sync`"
            )
            self.bot.reply_to(message, text, parse_mode='Markdown', reply_markup=self.get_main_keyboard())

        @self.bot.message_handler(commands=['sync'])
        def sync_stats(message: Message):
            if not self.check_admin(message.from_user.id): return
            self.bot.reply_to(message, "🔄 Синхронизирую последние завершенные заказы с FunPay...")
            history = self.client.get_historical_orders()
            
            existing_ids = {s['order_id'] for s in self.sales}
            added = 0
            for order in history:
                if order['order_id'] not in existing_ids:
                    # При добавлении старых заказов они запишутся с текущим временем (попадут в 24 часа)
                    # Но зато они вообще появятся в базе.
                    self.add_sale(order)
                    existing_ids.add(order['order_id'])
                    added += 1
            
            if added > 0:
                self.bot.send_message(message.chat.id, f"✅ Добавлено {added} прошлых заказов! Нажмите 📊 Статистика.")
            else:
                self.bot.send_message(message.chat.id, "✅ Новых прошлых заказов не найдено.")

        @self.bot.message_handler(func=lambda msg: msg.text in ["💬 Шаблоны ответов", "/templates"])
        def list_templates(message: Message):
            if not self.check_admin(message.from_user.id): return
            self.user_states[message.from_user.id] = None # Сброс состояния
            
            text = "📋 *Управление шаблонами*\n\n"
            if not self.templates:
                text += "📭 У вас пока нет заготовленных шаблонов."
            else:
                for i, t in enumerate(self.templates):
                    text += f"*{i+1}.* {t}\n"
                    
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("➕ Добавить", callback_data="cmd_add_tpl"),
                InlineKeyboardButton("➖ Удалить", callback_data="cmd_del_tpl")
            )
            self.bot.reply_to(message, text, parse_mode='Markdown', reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cmd_add_tpl")
        def add_tpl_start(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            self.user_states[call.from_user.id] = "adding_template"
            self.bot.edit_message_text("✍️ *Режим добавления*\n\nНапишите текст нового шаблона следующим сообщением:", call.message.chat.id, call.message.message_id, parse_mode='Markdown')

        @self.bot.callback_query_handler(func=lambda call: call.data == "cmd_del_tpl")
        def del_tpl_start(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            if not self.templates:
                self.bot.answer_callback_query(call.id, "Шаблонов нет!", show_alert=True)
                return
            
            markup = InlineKeyboardMarkup()
            for i, t in enumerate(self.templates):
                btn_text = f"❌ {t[:25]}..." if len(t) > 25 else f"❌ {t}"
                markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"del_{i}"))
            markup.add(InlineKeyboardButton(text="Отмена", callback_data="cancel_tpl"))
            
            self.bot.edit_message_text("🗑 *Режим удаления*\n\nНажмите на шаблон, который хотите удалить:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
        def del_tpl_confirm(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            try:
                idx = int(call.data.split('_')[1])
                del self.templates[idx]
                self.save_templates()
                self.bot.answer_callback_query(call.id, "✅ Шаблон удален")
                self.bot.edit_message_text("✅ Шаблон успешно удален.", call.message.chat.id, call.message.message_id)
            except Exception as e:
                self.bot.answer_callback_query(call.id, f"Ошибка: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data == "show_templates")
        def show_templates_callback(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            if not self.templates:
                self.bot.answer_callback_query(call.id, "Шаблонов нет! Добавьте в меню.", show_alert=True)
                return
            
            markup = InlineKeyboardMarkup()
            for i, t in enumerate(self.templates):
                btn_text = (t[:30] + '...') if len(t) > 30 else t
                markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"tpl_{i}"))
            markup.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_tpl"))
            
            self.bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("refund_"))
        def refund_start(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            order_id = call.data.split('_')[1]
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("❌ ДА, ВЕРНУТЬ", callback_data=f"confirmrefund_{order_id}"),
                InlineKeyboardButton("ОТМЕНА", callback_data="cancel_refund")
            )
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_refund")
        def cancel_refund(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            # Возвращаем обычную кнопку или просто удаляем клавиатуру подтверждения. 
            # Поскольку мы не сохраняли order_id в стейт, проще просто сбросить клавиатуру.
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirmrefund_"))
        def refund_confirm(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            order_id = call.data.split('_')[1]
            self.bot.answer_callback_query(call.id, "Отправляю запрос...")
            success, msg = self.client.refund_order(order_id)
            if success:
                self.bot.edit_message_text(call.message.text + f"\n\n✅ **ДЕНЬГИ ВЕРНУТЫ ПОКУПАТЕЛЮ**", call.message.chat.id, call.message.message_id)
            else:
                self.bot.answer_callback_query(call.id, f"Ошибка: {msg}", show_alert=True)
                # Возвращаем обычную кнопку
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text="⚠️ Вернуть деньги", callback_data=f"refund_{order_id}"))
                self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data == "cancel_tpl")
        def cancel_tpl_callback(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="💬 Готовые ответы", callback_data="show_templates"))
            self.bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_"))
        def send_template_callback(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            try:
                idx = int(call.data.split('_')[1])
                tpl_text = self.templates[idx]
                
                text = call.message.text
                if "ChatID:" in text:
                    chat_id = text.split("ChatID:")[1].strip().split()[0]
                    self.bot.answer_callback_query(call.id, "Отправляю на FunPay...")
                    success, result = self.client.send_message(chat_id, tpl_text)
                    if success:
                        self.bot.edit_message_text(f"{text}\n\n✅ *Вы ответили:* {tpl_text}", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
                    else:
                        self.bot.answer_callback_query(call.id, f"Ошибка: {result}", show_alert=True)
                else:
                    self.bot.answer_callback_query(call.id, "ChatID не найден в сообщении", show_alert=True)
            except Exception as e:
                self.bot.answer_callback_query(call.id, f"Ошибка: {e}")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("ai_resolve_"))
        def ai_resolve_callback(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            chat_id = call.data.split('_')[2]
            
            # Извлекаем текст из сообщения и пользователя (формат: Входящее сообщение от [User]: Text)
            text_lines = call.message.text.split('\n')
            user_line = [l for l in text_lines if "Входящее сообщение от" in l]
            if not user_line or not self.ai:
                self.bot.answer_callback_query(call.id, "Не удалось извлечь текст или ИИ отключен.", show_alert=True)
                return
                
            # Парсинг имени и текста
            user_name = user_line[0].split('[')[1].split(']')[0]
            # Текст проблемы обычно после двоеточия
            problem_text = user_line[0].split(']:', 1)[1].strip()
            
            self.bot.answer_callback_query(call.id, "ИИ думает...")
            
            # Генерируем ответ
            active_orders = self.client.get_active_orders()
            answer = self.ai.generate_troubleshooting_response(chat_id, user_name, problem_text, active_orders)
            
            if answer:
                success, result = self.client.send_message(chat_id, answer)
                if success:
                    self.client.mark_chat_read(chat_id)
                    new_text = call.message.text + f"\n\n🤖 *ИИ спросил:* {answer}"
                    self.bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
                    self.log_problem_action(chat_id, user_name, problem_text, "ИИ ТП", answer)
                    # Закрываем кейс, чтобы новые сообщения создавали новое уведомление (опционально, пока оставим открытым)
                    if chat_id in self.active_problems:
                        self.active_problems[chat_id]['text'] = new_text
                else:
                    self.bot.answer_callback_query(call.id, f"Ошибка отправки: {result}", show_alert=True)
            else:
                self.bot.answer_callback_query(call.id, "ИИ не смог сгенерировать ответ", show_alert=True)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("reply_"))
        def reply_callback(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            chat_id = call.data.split('_')[1]
            
            msg = self.bot.send_message(call.message.chat.id, "Напишите ответ для покупателя (текст будет отправлен на FunPay):")
            self.bot.register_next_step_handler(msg, self.process_manual_reply, chat_id, call.message)

        # Универсальный обработчик текста (должен быть последним)
        @self.bot.message_handler(func=lambda message: True)
        def handle_all_messages(message: Message):
            if not self.check_admin(message.from_user.id): return
            
            # Проверяем состояние пользователя
            state = self.user_states.get(message.from_user.id)
            if state == "adding_template":
                text = message.text.strip()
                # Сброс, если нажали кнопку из нижнего меню вместо ввода текста
                if text in ["🟢 Статус", "🔄 Поднять лоты", "📋 Актуальные заказы", "💬 Шаблоны ответов"]:
                    self.user_states[message.from_user.id] = None
                    self.bot.reply_to(message, "Действие отменено.")
                    return
                
                self.templates.append(text)
                self.save_templates()
                self.user_states[message.from_user.id] = None
                self.bot.reply_to(message, "✅ Шаблон успешно сохранен!")
                return
            
            # Логика ручного ответа (Reply) на сообщение FunPay
            if message.reply_to_message and message.reply_to_message.text:
                text = message.reply_to_message.text
                if "ChatID:" in text:
                    try:
                        chat_id = text.split("ChatID:")[1].strip().split()[0]
                        self.log(f"Отправляем ответ в чат {chat_id} через Telegram...", color=Fore.CYAN)
                        
                        success, result = self.client.send_message(chat_id, message.text)
                        if success:
                            self.bot.reply_to(message, "✅ Сообщение отправлено на FunPay!")
                        else:
                            self.bot.reply_to(message, f"❌ Ошибка отправки: {result}")
                    except Exception as e:
                        self.bot.reply_to(message, f"❌ Не удалось распознать ChatID: {e}")

    def notify_ai_reply(self, chat_id, user, text, answer):
        msg = (
            f"🤖 *ИИ ответил пользователю {user}*\n\n"
            f"👤: {text}\n"
            f"🤖: {answer}\n\n"
            f"`ChatID: {chat_id}`"
        )
        try:
            self.bot.send_message(self.admin_id, msg, parse_mode='Markdown')
        except Exception as e:
            self.log(f"Ошибка отправки в Telegram: {e}", color=Fore.RED)

    def notify_new_message(self, msg_data):
        try:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="💬 Готовые ответы", callback_data="show_templates"))
            text = f"📨 *Входящее сообщение от [{msg_data['user']}]*\n\n{msg_data['text']}\n\n`ChatID: {msg_data['chat_id']}`"
            self.bot.send_message(self.admin_id, text, parse_mode='Markdown', reply_markup=markup)
        except Exception as e:
            self.log(f"Ошибка отправки уведомления в TG: {e}", color=Fore.RED)

    def process_manual_reply(self, message: Message, chat_id, original_call_message):
        text = message.text
        self.bot.send_message(message.chat.id, "Отправляю...")
        success, result = self.client.send_message(chat_id, text)
        if success:
            self.client.mark_chat_read(chat_id)
            self.bot.send_message(message.chat.id, "✅ Ответ успешно доставлен!")
            try:
                new_text = original_call_message.text + f"\n\n✅ *Вы ответили:* {text}"
                self.bot.edit_message_text(new_text, original_call_message.chat.id, original_call_message.message_id, parse_mode='Markdown')
                
                # Логируем
                # Пытаемся извлечь оригинальную проблему из текста
                problem_text = "Неизвестно"
                for line in original_call_message.text.split('\n'):
                    if "Входящее сообщение от" in line:
                        parts = line.split(']:')
                        if len(parts) > 1:
                            problem_text = parts[1].strip()
                self.log_problem_action(chat_id, "Unknown", problem_text, "Ручной Ответ", text)
                
                # Закрываем кейс
                if chat_id in self.active_problems:
                    del self.active_problems[chat_id]
            except: pass
        else:
            self.bot.send_message(message.chat.id, f"❌ Ошибка отправки: {result}")

    def notify_problem(self, chat_id, user, text_msg, severity):
        # Обновление открытого кейса
        if chat_id in self.active_problems:
            try:
                case = self.active_problems[chat_id]
                new_text = case['text'] + f"\n\n📨 *Новое сообщение:*\n{text_msg}"
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text="🤖 ИИ: Уточнить детали", callback_data=f"ai_resolve_{chat_id}"))
                markup.add(InlineKeyboardButton(text="💬 Ответить самому", callback_data=f"reply_{chat_id}"))
                
                self.bot.edit_message_text(new_text, self.admin_id, case['msg_id'], parse_mode='Markdown', reply_markup=markup)
                self.active_problems[chat_id]['text'] = new_text
                return
            except Exception as e:
                # Если сообщение удалено или старое, создадим новое
                pass
        
        try:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(text="🤖 ИИ: Уточнить детали", callback_data=f"ai_resolve_{chat_id}")
            )
            markup.add(
                InlineKeyboardButton(text="💬 Ответить самому", callback_data=f"reply_{chat_id}")
            )
            
            header = "🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА" if severity == "critical" else "🆘 ПРОБЛЕМА"
            text = f"{header}\n\n📨 *Входящее сообщение от [{user}]*\n\n{text_msg}\n\n`ChatID: {chat_id}`"
            msg = self.bot.send_message(self.admin_id, text, parse_mode='Markdown', reply_markup=markup)
            
            # Сохраняем кейс
            self.active_problems[chat_id] = {'msg_id': msg.message_id, 'text': text}
            
        except Exception as e:
            self.log(f"Ошибка отправки проблемного уведомления в TG: {e}", color=Fore.RED)

    def notify_new_order(self, order_data):
        self.add_sale(order_data)
        text = (
            f"💸 *НОВЫЙ ЗАКАЗ ОПЛАЧЕН!* 💸\n\n"
            f"🛍 *Товар:* {order_data['title']}\n"
            f"👤 *Покупатель:* {order_data['buyer']}\n"
            f"💰 *Сумма:* {order_data['price']}\n"
            f"🆔 *Заказ:* #{order_data['order_id']}\n\n"
            f"🔗 [Перейти к заказу]({order_data['url']})"
        )
        try:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="⚠️ Вернуть деньги", callback_data=f"refund_{order_data['order_id']}"))
            self.bot.send_message(self.admin_id, text, parse_mode='Markdown', reply_markup=markup)
        except Exception as e:
            self.log(f"Ошибка отправки в Telegram: {e}", color=Fore.RED)

    def run_polling(self):
        self.is_running = True
        self.log("Telegram-бот успешно запущен!", color=Fore.GREEN)
        while self.is_running:
            try:
                self.bot.polling(none_stop=True, interval=1, timeout=20)
            except Exception as e:
                time.sleep(5)

    def send_startup_message(self, username, stats):
        text = (
            f"🚀 *Бот ASHANOV успешно запущен!*\n\n"
            f"👤 *Продавец:* {username}\n"
            f"💰 *Баланс:* {stats['balance']}\n"
            f"🛒 *Активные заказы:* {stats['active_sales']} шт.\n"
            f"💬 *Непрочитанные сообщения:* {stats['unread_chats']} шт.\n\n"
            f"🟢 *Модули:*\n"
            f"— Умное автоподнятие лотов (Работает)\n"
            f"— Вечный онлайн (Работает)\n"
            f"— Уведомления о заказах/чатах (Работает)"
        )
        try:
            self.bot.send_message(self.admin_id, text, parse_mode='Markdown', reply_markup=self.get_main_keyboard())
        except Exception as e:
            self.log(f"Ошибка отправки стартового сообщения: {e}", color=Fore.RED)
