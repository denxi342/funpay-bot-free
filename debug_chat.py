import sys
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT
from bs4 import BeautifulSoup

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    resp = client.session.get("https://funpay.com/chat/")
    
    with open("chat.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    for item in soup.find_all('a', class_='contact-item'):
        print(item.get('data-id'), item.find('div', class_='contact-item-name').text.strip())

if __name__ == "__main__":
    run()
