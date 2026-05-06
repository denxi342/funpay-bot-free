from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT
from bs4 import BeautifulSoup

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    print(f"Authorized as: {user} ({is_auth})")
    
    resp = client.session.get("https://funpay.com/chat/")
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    for contact in soup.find_all('a', class_='contact-item'):
        node_id = contact.get('data-id')
        msg_div = contact.find('div', class_='contact-item-message')
        msg_id = contact.get('data-node-msg') or (msg_div.get('data-node-msg') if msg_div else None)
        user_msg_id = contact.get('data-user-msg')
        unread = 'unread' in contact.get('class', [])
        name = contact.find('div', class_='media-user-name').text.strip() if contact.find('div', class_='media-user-name') else "?"
        text = msg_div.text.strip() if msg_div else ""
        print(f"Chat ID: {node_id} | Msg ID: {msg_id} | User Msg ID: {user_msg_id} | Unread: {unread} | Name: {name} | Text: {text}")

if __name__ == "__main__":
    run()
