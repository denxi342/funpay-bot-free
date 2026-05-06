import sys
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT
from bs4 import BeautifulSoup

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    cat_url = "https://funpay.com/lots/1230/trade"
    resp = client.session.get(cat_url)
    
    with open("cat_trade_1230.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    btn = soup.find('button', class_='js-lot-raise')
    if btn:
        print(f"Found button! game: {btn.get('data-game')}, node: {btn.get('data-node')}")
    else:
        print("Button not found! Looking for other buttons...")
        for b in soup.find_all('button'):
            if 'поднять' in b.text.lower():
                print(f"Possible button: {b}")

if __name__ == "__main__":
    run()
