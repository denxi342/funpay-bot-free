import sys
from bs4 import BeautifulSoup
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    order_id = "SUDGDTVP"
    response = client.session.get(f"{client.base_url}/orders/{order_id}/")
    
    with open("order_debug.html", "w", encoding="utf-8") as f:
        f.write(response.text)
        
    print("Order HTML saved to order_debug.html")

if __name__ == "__main__":
    run()
