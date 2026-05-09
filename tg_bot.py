import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import time
import json
import os
from colorama import Fore
from datetime import datetime

class TelegramManager:
    def __init__(self, token, admin_id, funpay_client, log_func, ai_responder=None):
        self.bot = telebot.TeleBot(token, parse_mode='HTML')
        self.admin_id = str(admin_id)
        self.client = funpay_client
        self.log = log_func
        self.ai = ai_responder
        
        self.settings_file = 'bot_settings.json'
        self.settings = self.load_settings()
        
        self.templates_file = 'templates.json'
        self.templates = self.load_templates()
        
        self.active_problems = {}
        self.setup_handlers()

    def load_settings(self):
        settings = {
            "auto_bump": True,
            "online_mode": True,
            "auto_respond": True,
            "notifications": True,
            "auto_delivery": False,
            "anti_scam": True,
            "delivery_configs": {},
            "needs_stats": False,
            "needs_chat_list": False,
            "force_bump": False,
            "pending_tasks": []
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    settings.update(loaded)
            except: pass
        
        # Принудительно сбрасываем временные флаги
        settings['needs_stats'] = False
        settings['needs_chat_list'] = False
        settings['force_bump'] = False
        return settings

    def save_settings(self):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=4)

    def load_templates(self):
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return []

    def check_admin(self, user_id):
        return str(user_id) == self.admin_id

    # --- ГЕНЕРАТОРЫ МЕНЮ (UI) ---

    def get_main_menu(self):
        text = (
            "<b>💎 ASHANOV STEALTH CONTROL</b>\n\n"
            "Управление ботом FunPay в реальном времени.\n"
            "Выберите раздел для настройки:"
        )
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton("📦 Автовыдача", callback_data="menu_delivery"),
            InlineKeyboardButton("💬 Чаты", callback_data="menu_chats"),
            InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
            InlineKeyboardButton("🔄 Поднять лоты", callback_data="cmd_bump_now")
        )
        return text, markup

    def get_settings_menu(self):
        text = "<b>⚙️ Настройки FunPay Bot</b>\n\nУправление глобальными переключателями:"
        markup = InlineKeyboardMarkup(row_width=1)
        
        def status(key): return "🟢" if self.settings.get(key) else "🔴"
        
        markup.add(
            InlineKeyboardButton(f"{status('auto_bump')} Автоподнятие", callback_data="toggle_auto_bump"),
            InlineKeyboardButton(f"{status('online_mode')} Вечный онлайн", callback_data="toggle_online_mode"),
            InlineKeyboardButton(f"{status('auto_respond')} ИИ Автоответчик", callback_data="toggle_auto_respond"),
            InlineKeyboardButton(f"{status('notifications')} Уведомления", callback_data="toggle_notifications"),
            InlineKeyboardButton(f"{status('anti_scam')} Anti-Scam (Риски)", callback_data="toggle_anti_scam"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        return text, markup

    def get_delivery_menu(self):
        text = (
            "<b>📦 Управление Автовыдачей</b>\n\n"
            f"Статус системы: {'🟢 Активна' if self.settings['auto_delivery'] else '🔴 Выключена'}\n\n"
            "Здесь вы можете привязать файлы с товарами к ключевым словам в названии лотов."
        )
        markup = InlineKeyboardMarkup(row_width=1)
        status_btn = "🔴 Выключить систему" if self.settings['auto_delivery'] else "🟢 Включить систему"
        markup.add(
            InlineKeyboardButton(status_btn, callback_data="toggle_auto_delivery"),
            InlineKeyboardButton("➕ Добавить товар", callback_data="delivery_add"),
            InlineKeyboardButton("📋 Список товаров", callback_data="delivery_list"),
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")
        )
        return text, markup

    # --- ОБРАБОТЧИКИ ХЕНДЛЕРОВ ---

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def cmd_start(message: Message):
            if not self.check_admin(message.from_user.id): return
            text, markup = self.get_main_menu()
            self.bot.send_message(message.chat.id, text, reply_markup=markup)

        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_query(call: CallbackQuery):
            if not self.check_admin(call.from_user.id): return
            
            data = call.data
            
            # Навигация
            if data == "menu_main":
                text, markup = self.get_main_menu()
                try:
                    self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
                except:
                    # Если это было сообщение с фото (статистика), редактирование текста не сработает
                    self.bot.delete_message(call.message.chat.id, call.message.message_id)
                    self.bot.send_message(call.message.chat.id, text, reply_markup=markup)
            
            elif data == "menu_settings":
                text, markup = self.get_settings_menu()
                self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            
            elif data == "menu_delivery":
                text, markup = self.get_delivery_menu()
                self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            
            # Переключатели (Toggles)
            elif data.startswith("toggle_"):
                key = data.replace("toggle_", "")
                self.settings[key] = not self.settings.get(key, False)
                self.save_settings()
                # Возвращаемся в то же меню для обновления индикатора
                if key in ["auto_bump", "online_mode", "auto_respond", "notifications", "anti_scam"]:
                    text, markup = self.get_settings_menu()
                elif key == "auto_delivery":
                    text, markup = self.get_delivery_menu()
                else:
                    text, markup = self.get_main_menu()
                self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

            elif data == "cmd_bump_now":
                self.bot.answer_callback_query(call.id, "🔄 Задача добавлена в очередь...")
                self.settings['force_bump'] = True
                self.save_settings()

            elif data == "menu_chats":
                self.bot.answer_callback_query(call.id, "🔍 Загружаю список чатов...")
                self.settings['needs_chat_list'] = True
                self.settings['needs_chat_details'] = False # Сбрасываем запрос на конкретный чат
                self.save_settings()

            elif data.startswith("chat_"):
                chat_id = data.replace("chat_", "")
                self.bot.answer_callback_query(call.id, "🔄 Загружаю историю и профиль...")
                self.settings['needs_chat_details'] = chat_id
                self.save_settings()

            elif data == "menu_stats":
                self.bot.answer_callback_query(call.id, "📊 Собираю актуальные данные...")
                self.settings['needs_stats'] = True
                self.save_settings()

            elif data.startswith("refund_"):
                order_id = data.replace("refund_", "")
                self.bot.answer_callback_query(call.id, "💸 Запрос на возврат отправлен...")
                if 'pending_tasks' not in self.settings: self.settings['pending_tasks'] = []
                self.settings['pending_tasks'].append({'type': 'refund', 'id': order_id})
                self.save_settings()

            elif data.startswith("ai_reply_"):
                chat_id = data.replace("ai_reply_", "")
                self.bot.answer_callback_query(call.id, "🤖 ИИ обдумывает ответ...")
                if 'pending_tasks' not in self.settings: self.settings['pending_tasks'] = []
                self.settings['pending_tasks'].append({'type': 'ai_reply', 'id': chat_id})
                self.save_settings()
            
            elif data.startswith("reply_"):
                chat_id = data.replace("reply_", "")
                msg = self.bot.send_message(call.message.chat.id, "📝 Введите ваше сообщение для отправки:")
                self.bot.register_next_step_handler(msg, self.process_manual_reply, chat_id)

    def process_manual_reply(self, message, chat_id):
        if not self.check_admin(message.from_user.id): return
        text = message.text
        if 'pending_tasks' not in self.settings: self.settings['pending_tasks'] = []
        self.settings['pending_tasks'].append({'type': 'manual_reply', 'id': chat_id, 'text': text})
        self.save_settings()
        self.bot.send_message(self.admin_id, f"✅ Сообщение для чата {chat_id} поставлено в очередь на отправку.")

    def notify_new_order(self, order_data):
        def escape(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
        title = escape(order_data['title'])
        buyer = escape(order_data['buyer'])
        price = escape(order_data['price'])
        
        text = (
            f"🔔 <b>[ОПОВЕЩЕНИЕ О ЗАКАЗЕ]</b>\n"
            f"————————————————\n"
            f"💰 <b>Сумма:</b> <code>{price}</code>\n"
            f"📦 <b>Товар:</b> <code>{title}</code>\n"
            f"👤 <b>Покупатель:</b> <code>{buyer}</code>\n"
            f"🆔 <b>Заказ:</b> <code>#{order_data['order_id']}</code>\n"
        )
        
        u_info = order_data.get('user_info')
        if u_info:
            reg_date = escape(u_info['reg_date'])
            text += f"\n📊 <b>Профиль:</b> {reg_date}, ⭐️ {u_info['reviews']}\n"
            if u_info['is_new']:
                text += "⚠️ <b>ВНИМАНИЕ: НОВОРЕГ БЕЗ ОТЗЫВОВ!</b>\n"
        
        text += (
            f"————————————————\n"
            f"🔗 <a href='{order_data['url']}'>Открыть страницу заказа</a>"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("⚠️ Сделать возврат", callback_data=f"refund_{order_data['order_id']}"),
            InlineKeyboardButton("💬 Перейти в чат", url=f"https://funpay.com/chat/?node={order_data['order_id']}") # Обычно ChatID совпадает с OrderID для новых заказов
        )
        try:
            self.bot.send_message(self.admin_id, text, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            self.log(f"Ошибка отправки уведомления о заказе: {e}", level="ERROR")

    def notify_new_message(self, msg_data):
        def escape(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        user = escape(msg_data['user'])
        text_content = escape(msg_data['text'])
        
        text = (
            f"📩 <b>[НОВОЕ СООБЩЕНИЕ]</b>\n"
            f"————————————————\n"
            f"👤 <b>От:</b> <code>{user}</code>\n"
            f"📝 <b>Текст:</b>\n<blockquote><i>{text_content}</i></blockquote>\n"
        )
        
        u_info = msg_data.get('user_info')
        if u_info:
            reg_date = escape(u_info['reg_date'])
            text += f"\n📊 <b>Профиль:</b> {reg_date}, ⭐️ {u_info['reviews']}\n"
            if u_info['is_new']:
                text += "⚠️ <b>ВНИМАНИЕ: НОВОРЕГ БЕЗ ОТЗЫВОВ!</b>\n"

        text += (
            "————————————————\n"
            f"🆔 <code>ChatID: {msg_data['chat_id']}</code>"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✍️ Ответить", callback_data=f"reply_{msg_data['chat_id']}"),
            InlineKeyboardButton("🤖 AI-Ответ", callback_data=f"ai_reply_{msg_data['chat_id']}")
        )
        try:
            self.bot.send_message(self.admin_id, text, reply_markup=markup)
        except Exception as e:
            self.log(f"Ошибка отправки уведомления о сообщении: {e}", level="ERROR")

    def notify_new_review(self, review_data):
        def escape(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
        author = escape(review_data['author'])
        text_content = escape(review_data['text'])
        rating = review_data['rating']
        
        stars_str = "⭐️" * rating + "🌑" * (5 - rating)
        
        text = (
            f"🌟 <b>[НОВЫЙ ОТЗЫВ]</b>\n"
            f"————————————————\n"
            f"👤 <b>Покупатель:</b> <code>{author}</code>\n"
            f"📊 <b>Оценка:</b> {stars_str}\n"
            f"📝 <b>Комментарий:</b>\n<blockquote><i>{text_content}</i></blockquote>\n"
            f"————————————————"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔗 Мой профиль", url=f"https://funpay.com/users/{self.client.user_id}/")
        )
        try:
            self.bot.send_message(self.admin_id, text, reply_markup=markup)
        except Exception as e:
            self.log(f"Ошибка отправки уведомления об отзыве: {e}", level="ERROR")

    def send_startup_message(self, username, stats):
        text = (
            f"🚀 <b>[СИСТЕМА ЗАПУЩЕНА]</b>\n"
            f"————————————————\n"
            f"👤 <b>Продавец:</b> <code>{username}</code>\n"
            f"💰 <b>Баланс:</b> <code>{stats['balance']}</code>\n"
            f"📦 <b>Продаж:</b> <code>{stats['active_sales']}</code>\n"
            f"————————————————\n"
            f"✨ <b>By Ashanov Engine</b> ✨"
        )
        text_menu, markup = self.get_main_menu()
        self.bot.send_message(self.admin_id, text + "\n\n" + text_menu, reply_markup=markup)

    def send_chat_list(self, chats):
        def escape(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        if not chats:
            self.bot.send_message(self.admin_id, "⚠️ Не удалось загрузить список чатов или он пуст.")
            return

        text = "<b>💬 Менеджер диалогов</b>\n\nЗдесь собраны ваши последние переписки. Выберите чат, чтобы прочитать историю или ответить."
        markup = InlineKeyboardMarkup(row_width=1)
        
        for chat in chats:
            unread = "🔴 " if chat['unread'] else "⚪️ "
            # Обрезаем сообщение и экранируем
            name = escape(chat['name'])
            msg_raw = chat['last_msg'] if chat['last_msg'] else "..."
            msg = escape(msg_raw[:30] + ".." if len(msg_raw) > 30 else msg_raw)
            btn_text = f"{unread}{name}: {msg}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"chat_{chat['id']}"))
        
        markup.add(InlineKeyboardButton("⬅️ Назад в меню", callback_data="menu_main"))
        try:
            self.bot.send_message(self.admin_id, text, reply_markup=markup)
        except Exception as e:
            self.log(f"Ошибка отправки списка чатов: {e}", level="ERROR")

    def send_chat_details(self, chat_id, details):
        def escape(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        if "error" in details:
            self.bot.send_message(self.admin_id, f"❌ Ошибка загрузки чата: {details['error']}")
            return

        # Инфо о пользователе
        u = details.get('user_info')
        user_header = ""
        if u:
            risk_icon = "⚠️" if u['is_new'] else "✅"
            user_header = f"👤 <b>Профиль:</b> {escape(u['reg_date'])}\n⭐️ <b>Отзывы:</b> {u['reviews']} | {risk_icon} <b>Риск:</b> {'Высокий' if u['is_new'] else 'Низкий'}\n\n"

        # История сообщений
        history = "📜 <b>История сообщений:</b>\n"
        if not details['messages']:
            history += "<i>(История пуста)</i>\n"
        else:
            for m in details['messages']:
                prefix = "➡️" if m['is_our'] else "⬅️"
                author = "Вы" if m['is_our'] else escape(m['user'])
                msg_text = escape(m['text'])
                history += f"<b>{prefix} {author}:</b> {msg_text}\n"
        
        full_text = (
            f"💬 <b>Чат #{chat_id}</b>\n"
            f"————————————————\n"
            f"{user_header}"
            f"{history}"
            f"————————————————"
        )
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✍️ Ответить", callback_data=f"reply_{chat_id}"),
            InlineKeyboardButton("🤖 AI-Ответ", callback_data=f"ai_reply_{chat_id}"),
            InlineKeyboardButton("⬅️ К списку", callback_data="menu_chats"),
            InlineKeyboardButton("🔄 Обновить", callback_data=f"chat_{chat_id}")
        )
        self.bot.send_message(self.admin_id, full_text, reply_markup=markup)

    def send_stats_menu(self, stats):
        text = (
            "<b>📊 ТЕКУЩАЯ СТАТИСТИКА</b>\n"
            f"————————————————\n"
            f"💰 <b>Баланс:</b> <code>{stats['balance']}</code>\n"
            f"🛒 <b>Продаж:</b> <code>{stats['active_sales']}</code>\n"
            f"💬 <b>Непрочитанных:</b> <code>{stats['unread_chats']}</code>\n"
            f"————————————————\n"
            f"🕒 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="menu_main"))
        self.bot.send_message(self.admin_id, text, reply_markup=markup)

    def send_advanced_stats(self, photo_path, metrics):
        """Отправляет отрендеренный дашборд с подписью."""
        caption = (
            f"📊 <b>ADVANCED ANALYTICS</b>\n"
            f"————————————————\n"
            f"💰 <b>Выручка 24ч:</b> <code>{metrics['revenue_24h']} ₽</code>\n"
            f"📈 <b>Выручка 7д:</b> <code>{metrics['revenue_7d']} ₽</code>\n"
            f"🏆 <b>Топ товар:</b> <code>{metrics['top_item']}</code>\n"
            f"👤 <b>Топ покупатель:</b> <code>{metrics['top_buyer']}</code>\n"
            f"————————————————"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="menu_main"))
        try:
            with open(photo_path, 'rb') as photo:
                self.bot.send_photo(self.admin_id, photo, caption=caption, reply_markup=markup)
        except Exception as e:
            self.bot.send_message(self.admin_id, f"❌ Ошибка отправки графиков: {e}\n\n{caption}", reply_markup=markup)

    def run_polling(self):
        self.log("Telegram UI (Advanced Mode) запущен!", level="SUCCESS")
        # Увеличиваем таймауты для стабильности соединения
        self.bot.infinity_polling(timeout=90, long_polling_timeout=20)
