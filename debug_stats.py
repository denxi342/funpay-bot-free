from funpay import FunPayClient
from config import GOLDEN_KEY, USER_AGENT

def run():
    client = FunPayClient(GOLDEN_KEY, USER_AGENT)
    is_auth, user = client.check_authorization()
    print(f"Auth: {is_auth}")
    stats = client.get_stats()
    print(f"Stats: {stats}")

if __name__ == "__main__":
    run()
