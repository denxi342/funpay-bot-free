import sys
import json
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    chat_id = "257449748"  # from chat.html
    text = "test message from debug script"
    
    headers = {
        "x-requested-with": "XMLHttpRequest",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    payload = {
        "request": json.dumps({
            "action": "chat_message",
            "data": {
                "node": chat_id,
                "text": text
            }
        }),
        "csrf_token": client.csrf_token
    }
    
    response = client.session.post(f"{client.base_url}/runner/", data=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")

if __name__ == "__main__":
    run()
