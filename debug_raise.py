"""
Тест правильного поднятия с node_ids.
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

from bs4 import BeautifulSoup
from config import GOLDEN_KEY, USER_AGENT
from funpay import FunPayClient

client = FunPayClient(GOLDEN_KEY, USER_AGENT)
ok, name = client.check_authorization()
print(f"Auth: {name} (CSRF: {client.csrf_token})")

ok2, count = client.get_categories_to_bump()
cat = client.categories_to_bump[0]

headers = {
    "x-requested-with": "XMLHttpRequest",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8"
}

# Шаг 1
print("\n[1] Получаем модалку...")
r1 = client.session.post("https://funpay.com/lots/raise", data={
    "game_id": cat['game_id'],
    "node_id": cat['node_id'],
    "csrf_token": client.csrf_token
}, headers=headers)
d1 = r1.json()

if 'modal' not in d1:
    print(f"Нет модалки: {json.dumps(d1, ensure_ascii=False)[:500]}")
    exit()

soup = BeautifulSoup(d1['modal'], 'html.parser')
raise_box = soup.find('div', class_='raise-box')
rb_game = raise_box.get('data-game')
rb_node = raise_box.get('data-node')

all_nodes = [cb.get('value') for cb in soup.find_all('input', {'type': 'checkbox'})]
print(f"raise-box: game={rb_game}, node={rb_node}")
print(f"Все node_ids: {all_nodes}")

# Шаг 2 — правильный формат: game_id + node_id + node_ids[] + csrf_token
print("\n[2] Отправляем поднятие с node_ids[]...")
parts = [
    f"game_id={rb_game}",
    f"node_id={rb_node}",
    f"csrf_token={client.csrf_token}"
]
for nid in all_nodes:
    parts.append(f"node_ids%5B%5D={nid}")

data_str = "&".join(parts)
print(f"Data: {data_str}")

r2 = client.session.post("https://funpay.com/lots/raise", data=data_str, headers=headers)
print(f"Status: {r2.status_code}")
result = r2.json()
print(f"Response: {json.dumps(result, ensure_ascii=False, indent=2)[:1000]}")

if 'modal' in result:
    print("\n!!! ПРОВАЛ: Снова получили модалку !!!")
elif result.get('error'):
    print(f"\nОшибка: {result.get('msg', result.get('message', '?'))}")
else:
    print("\nУСПЕХ! Лоты подняты!")
