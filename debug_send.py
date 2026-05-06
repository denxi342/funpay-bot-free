import sys
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT
import time

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    # Сначала получим чаты, чтобы найти chat_id для теста
    msgs = client.get_new_messages()
    if msgs:
        chat_id = msgs[0]['chat_id']
        print(f"Testing send to chat {chat_id}")
        success, res = client.send_message(chat_id, "test bot message")
        print(f"Success: {success}, Res: {res}")
    else:
        print("No active chats to test.")

if __name__ == "__main__":
    run()
