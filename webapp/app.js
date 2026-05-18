const tg = window.Telegram.WebApp;

// Инициализация WebApp
tg.expand();
tg.ready();

// Получаем инфу о пользователе из телеги
if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
    const user = tg.initDataUnsafe.user;
    document.getElementById('tg-name').innerText = user.first_name || 'Admin';
    if (user.photo_url) {
        document.getElementById('tg-avatar').src = user.photo_url;
    }
}

// Функции работы с API
const API_URL = window.location.origin + '/api';

async function fetchData() {
    try {
        const tgBtn = tg.MainButton;
        tgBtn.text = "Обновление...";
        tgBtn.show();
        tgBtn.showProgress();

        // Получаем статистику
        const statsRes = await fetch(`${API_URL}/stats`);
        const statsData = await statsRes.json();
        
        if (statsData.status === 'ok') {
            document.getElementById('stat-balance').innerText = statsData.stats.balance || '0 ₽';
            document.getElementById('stat-sales').innerText = statsData.stats.active_sales || '0';
            document.getElementById('stat-chats').innerText = statsData.stats.unread_chats || '0';
            
            if (statsData.metrics && statsData.metrics.revenue_24h) {
                document.getElementById('stat-rev24').innerText = `${statsData.metrics.revenue_24h} ₽`;
            }
        }

        // Получаем настройки
        const settingsRes = await fetch(`${API_URL}/settings`);
        const settingsData = await settingsRes.json();
        
        if (settingsData.status === 'ok') {
            const s = settingsData.settings;
            document.getElementById('toggle-bump').checked = s.auto_bump;
            document.getElementById('toggle-online').checked = s.online_mode;
            document.getElementById('toggle-ai').checked = s.auto_respond;
            document.getElementById('toggle-notif').checked = s.notifications;
            document.getElementById('toggle-scam').checked = s.anti_scam;
            document.getElementById('toggle-delivery').checked = s.auto_delivery;
        }

        tgBtn.hide();
        tg.HapticFeedback.notificationOccurred('success');
    } catch (e) {
        console.error("Fetch error:", e);
        tg.showAlert("Ошибка при загрузке данных");
        tg.MainButton.hide();
    }
}

async function updateSettings() {
    tg.HapticFeedback.impactOccurred('light');
    
    const newSettings = {
        auto_bump: document.getElementById('toggle-bump').checked,
        online_mode: document.getElementById('toggle-online').checked,
        auto_respond: document.getElementById('toggle-ai').checked,
        notifications: document.getElementById('toggle-notif').checked,
        anti_scam: document.getElementById('toggle-scam').checked,
        auto_delivery: document.getElementById('toggle-delivery').checked
    };

    try {
        await fetch(`${API_URL}/settings`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(newSettings)
        });
        // Успешно сохранено
    } catch (e) {
        console.error("Update error:", e);
        tg.showAlert("Не удалось сохранить настройки");
    }
}

// При старте
fetchData();
