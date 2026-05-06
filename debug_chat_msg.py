import sys
from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    
    chat_id = "257449748"
    text = "test message 2"
    
    headers = {
        "x-requested-with": "XMLHttpRequest",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    payload = {
        "node": chat_id,
        "content": text,
        "csrf_token": client.csrf_token
    }
    
    response = client.session.post(f"{client.base_url}/chat/message", data=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")

if __name__ == "__main__":
    run()
