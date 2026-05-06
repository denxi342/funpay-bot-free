import sys
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT
from bs4 import BeautifulSoup

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    if not is_auth:
        print("Not authorized")
        return
        
    resp = client.session.get("https://funpay.com/orders/trade")
    
    with open("orders.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
        
    print("Orders HTML saved.")

if __name__ == "__main__":
    run()
