import json
import os
from datetime import datetime, timedelta
import collections

class StatsManager:
    def __init__(self, sales_file='sales.json'):
        self.sales_file = sales_file
        self._cache = None
        self._last_mtime = 0

    def get_aggregated_data(self):
        if not os.path.exists(self.sales_file):
            return None

        # Проверка кеша по времени изменения файла
        current_mtime = os.path.getmtime(self.sales_file)
        if self._cache and current_mtime == self._last_mtime:
            return self._cache

        try:
            with open(self.sales_file, 'r', encoding='utf-8') as f:
                sales = json.load(f)
        except:
            return None

        if not sales:
            return None

        now = datetime.now()
        ts_24h = (now - timedelta(days=1)).timestamp()
        ts_7d = (now - timedelta(days=7)).timestamp()

        revenue_24h = 0
        revenue_7d = 0
        revenue_by_day = collections.defaultdict(float)
        hourly_dist = collections.defaultdict(int)
        item_stats = collections.defaultdict(float)
        buyer_stats = collections.defaultdict(int)

        # Для графика последних 7 дней (включая сегодня)
        days_list = [(now - timedelta(days=i)).strftime('%d.%m') for i in range(6, -1, -1)]
        revenue_by_day_final = {day: 0.0 for day in days_list}

        for sale in sales:
            ts = sale['timestamp']
            price = sale['price']
            dt = datetime.fromtimestamp(ts)
            
            # Агрегация по дням (последние 7 дней)
            day_str = dt.strftime('%d.%m')
            if day_str in revenue_by_day_final:
                revenue_by_day_final[day_str] += price
            
            # Рекордные метрики
            if ts >= ts_24h:
                revenue_24h += price
            if ts >= ts_7d:
                revenue_7d += price
            
            # Распределение по часам
            hourly_dist[dt.hour] += 1
            
            # Топ товары
            item_stats[sale['title']] += price
            
            # Топ покупатели
            buyer_stats[sale['buyer']] += 1

        # Формируем финальные структуры
        top_item = max(item_stats.items(), key=lambda x: x[1])[0] if item_stats else "N/A"
        top_buyer = max(buyer_stats.items(), key=lambda x: x[1])[0] if buyer_stats else "N/A"

        result = {
            "metrics": {
                "revenue_24h": round(revenue_24h, 2),
                "revenue_7d": round(revenue_7d, 2),
                "top_item": top_item,
                "top_buyer": top_buyer
            },
            "charts": {
                "days_labels": list(revenue_by_day_final.keys()),
                "days_data": list(revenue_by_day_final.values()),
                "hours_labels": [f"{i}:00" for i in range(24)],
                "hours_data": [hourly_dist.get(i, 0) for i in range(24)],
                "items_labels": [k[:30] + '...' if len(k) > 30 else k for k in list(item_stats.keys())[:5]],
                "items_data": list(item_stats.values())[:5]
            }
        }

        # Сохраняем в кеш
        self._cache = result
        self._last_mtime = current_mtime
        return result

    def generate_html(self, data):
        if not data:
            return "<h1>No data available</h1>"

        html_template = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>ASHANOV Stats Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-color: #0f0f13;
            --card-bg: #1a1a23;
            --text-color: #e0e0e0;
            --accent-color: #7289da;
            --grid-color: #2a2a35;
        }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }}
        #dashboard {{
            width: 1200px;
            background: var(--card-bg);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid var(--grid-color);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            border-bottom: 1px solid var(--grid-color);
            padding-bottom: 15px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
            color: var(--accent-color);
        }}
        .header .timestamp {{
            font-size: 14px;
            color: #888;
        }}
        .kpi-container {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .kpi-card {{
            background: rgba(255,255,255,0.03);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--grid-color);
        }}
        .kpi-card .label {{
            font-size: 12px;
            text-transform: uppercase;
            color: #888;
            margin-bottom: 8px;
            letter-spacing: 1px;
        }}
        .kpi-card .value {{
            font-size: 20px;
            font-weight: bold;
            color: #fff;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            grid-template-rows: 350px 350px;
            gap: 25px;
        }}
        .chart-box {{
            background: rgba(255,255,255,0.02);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--grid-color);
            position: relative;
        }}
        .chart-box h3 {{
            margin: 0 0 15px 0;
            font-size: 16px;
            font-weight: 500;
            color: #bbb;
        }}
        canvas {{
            width: 100% !important;
            height: 100% !important;
        }}
        .chart-container {{
            width: 100%;
            height: calc(100% - 40px);
        }}
    </style>
</head>
<body>
    <div id="dashboard" style="visibility: hidden;">
        <div class="header">
            <h1>💎 ASHANOV ANALYTICS</h1>
            <div class="timestamp">Обновлено: {current_time}</div>
        </div>

        <div class="kpi-container">
            <div class="kpi-card">
                <div class="label">Выручка 24ч</div>
                <div class="value">{revenue_24h} ₽</div>
            </div>
            <div class="kpi-card">
                <div class="label">Выручка 7д</div>
                <div class="value">{revenue_7d} ₽</div>
            </div>
            <div class="kpi-card">
                <div class="label">Топ товар</div>
                <div class="value" style="font-size: 14px;">{top_item}</div>
            </div>
            <div class="kpi-card">
                <div class="label">Топ покупатель</div>
                <div class="value">{top_buyer}</div>
            </div>
        </div>

        <div class="charts-grid">
            <div class="chart-box">
                <h3>Доход по дням (₽)</h3>
                <div class="chart-container"><canvas id="revenueChart"></canvas></div>
            </div>
            <div class="chart-box">
                <h3>Топ товары</h3>
                <div class="chart-container"><canvas id="itemsChart"></canvas></div>
            </div>
            <div class="chart-box" style="grid-column: span 2;">
                <h3>Активность по часам (заказы)</h3>
                <div class="chart-container"><canvas id="hoursChart"></canvas></div>
            </div>
        </div>
    </div>

    <script>
        const ctxRevenue = document.getElementById('revenueChart').getContext('2d');
        new Chart(ctxRevenue, {{
            type: 'line',
            data: {{
                labels: {days_labels},
                datasets: [{{
                    label: 'Выручка',
                    data: {days_data},
                    borderColor: '#7289da',
                    backgroundColor: 'rgba(114, 137, 218, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: '#7289da'
                }}]
            }},
            options: {{
                animation: false, // Отключаем анимацию для моментального скриншота
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ grid: {{ color: '#2a2a35' }}, ticks: {{ color: '#888' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#888' }} }}
                }}
            }}
        }});

        const ctxItems = document.getElementById('itemsChart').getContext('2d');
        new Chart(ctxItems, {{
            type: 'doughnut',
            data: {{
                labels: {items_labels},
                datasets: [{{
                    data: {items_data},
                    backgroundColor: ['#7289da', '#43b581', '#faa61a', '#f04747', '#5865f2'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                animation: false,
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ color: '#888', boxWidth: 12, font: {{ size: 10 }} }}
                    }}
                }}
            }}
        }});

        const ctxHours = document.getElementById('hoursChart').getContext('2d');
        new Chart(ctxHours, {{
            type: 'bar',
            data: {{
                labels: {hours_labels},
                datasets: [{{
                    label: 'Заказы',
                    data: {hours_data},
                    backgroundColor: '#7289da',
                    borderRadius: 4
                }}]
            }},
            options: {{
                animation: false,
                devicePixelRatio: 2, // Для четкости на скриншоте
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ grid: {{ color: '#2a2a35' }}, ticks: {{ color: '#888', stepSize: 1 }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#888' }} }}
                }}
            }}
        }});

        // Маркер готовности для Playwright
        document.getElementById('dashboard').style.visibility = 'visible';
        document.body.classList.add('loaded');
    </script>
</body>
</html>
        """
        
        return html_template.format(
            current_time=datetime.now().strftime('%d.%m.%Y %H:%M'),
            revenue_24h=data['metrics']['revenue_24h'],
            revenue_7d=data['metrics']['revenue_7d'],
            top_item=data['metrics']['top_item'],
            top_buyer=data['metrics']['top_buyer'],
            days_labels=json.dumps(data['charts']['days_labels']),
            days_data=json.dumps(data['charts']['days_data']),
            items_labels=json.dumps(data['charts']['items_labels']),
            items_data=json.dumps(data['charts']['items_data']),
            hours_labels=json.dumps(data['charts']['hours_labels']),
            hours_data=json.dumps(data['charts']['hours_data'])
        )
