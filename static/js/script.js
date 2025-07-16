// Глобальные переменные
let statusCheckInterval;
let segmentationUpdateInterval;
let cameraStates = {
    camera1: { connected: false, processing: false, segmentation_area: 0 },
    camera2: { connected: false, processing: false, segmentation_area: 0 }
};

let segmentationStats = {
    area_product: 0,
    max_product: 0,
    average_product: 0,
    total_calculations: 0
};

// Инициализация приложения
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    startStatusUpdates();
    startSegmentationUpdates();
});

// Инициализация приложения
function initializeApp() {
    logMessage('Инициализация приложения...');
    checkCameraStatus();
    updateSegmentationDisplay();
}

// Настройка обработчиков событий
function setupEventListeners() {
    // Кнопки подключения камер
    document.getElementById('connect1').addEventListener('click', () => connectCamera('camera1'));
    document.getElementById('connect2').addEventListener('click', () => connectCamera('camera2'));
    
    // Кнопки отключения камер
    document.getElementById('disconnect1').addEventListener('click', () => disconnectCamera('camera1'));
    document.getElementById('disconnect2').addEventListener('click', () => disconnectCamera('camera2'));
    
    // Закрытие уведомлений
    document.getElementById('notification-close').addEventListener('click', hideNotification);
    
    // Обработка Enter в полях ввода
    document.querySelectorAll('.input-group input').forEach(input => {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const cameraId = this.id.includes('1') ? 'camera1' : 'camera2';
                connectCamera(cameraId);
            }
        });
    });
}

// Функция для создания RTSP URL из полей ввода
function buildRtspUrl(cameraNum) {
    const ip = document.getElementById(`ip${cameraNum}`).value.trim();
    const port = document.getElementById(`port${cameraNum}`).value.trim();
    const username = document.getElementById(`username${cameraNum}`).value.trim();
    const password = document.getElementById(`password${cameraNum}`).value.trim();
    const stream = document.getElementById(`stream${cameraNum}`).value.trim();
    
    if (!ip || !port || !username || !password || !stream) {
        throw new Error('Все поля должны быть заполнены');
    }
    
    return `rtsp://${username}:${password}@${ip}:${port}/${stream}`;
}

// Подключение к камере
async function connectCamera(cameraId) {
    const num = cameraId === 'camera1' ? '1' : '2';
    const connectBtn = document.getElementById(`connect${num}`);
    const disconnectBtn = document.getElementById(`disconnect${num}`);
    
    try {
        // Создание RTSP URL из полей ввода
        const rtspUrl = buildRtspUrl(num);
        
        // Блокировка кнопок
        connectBtn.disabled = true;
        connectBtn.textContent = 'Подключение...';
        connectBtn.classList.add('loading');
        
        logMessage(`Подключение к камере ${num}: ${rtspUrl}`);
        
        const response = await fetch('/connect_camera', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                camera_id: cameraId,
                rtsp_url: rtspUrl
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Успешное подключение
            updateCameraStatus(cameraId, true, false);
            startVideoStreams(cameraId);
            logMessage(`Камера ${num} успешно подключена`, 'success');
            showNotification(`Камера ${num} подключена. Детекция человека и подсчет площади сегментации активны.`, 'success');
            
            // Обновление интерфейса
            connectBtn.style.display = 'none';
            disconnectBtn.style.display = 'inline-block';
            
        } else {
            // Ошибка подключения
            logMessage(`Ошибка подключения камеры ${num}: ${result.message}`, 'error');
            showNotification(`Ошибка подключения камеры ${num}: ${result.message}`, 'error');
        }
        
    } catch (error) {
        logMessage(`Ошибка при подключении камеры ${num}: ${error.message}`, 'error');
        showNotification(`Ошибка: ${error.message}`, 'error');
    } finally {
        // Разблокировка кнопок
        connectBtn.disabled = false;
        connectBtn.textContent = 'Подключить';
        connectBtn.classList.remove('loading');
    }
}

// Отключение камеры
async function disconnectCamera(cameraId) {
    const num = cameraId === 'camera1' ? '1' : '2';
    const connectBtn = document.getElementById(`connect${num}`);
    const disconnectBtn = document.getElementById(`disconnect${num}`);
    
    logMessage(`Отключение камеры ${num}...`);
    
    try {
        const response = await fetch('/disconnect_camera', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                camera_id: cameraId
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Успешное отключение
            updateCameraStatus(cameraId, false, false);
            stopVideoStreams(cameraId);
            
            // Сбрасываем площадь сегментации
            updateSegmentationArea(cameraId, 0);
            
            logMessage(`Камера ${num} отключена`, 'success');
            showNotification(`Камера ${num} отключена`, 'success');
            
            // Обновление интерфейса
            connectBtn.style.display = 'inline-block';
            disconnectBtn.style.display = 'none';
            
        } else {
            logMessage(`Ошибка отключения камеры ${num}: ${result.message}`, 'error');
            showNotification(`Ошибка отключения камеры ${num}`, 'error');
        }
        
    } catch (error) {
        logMessage(`Ошибка сети при отключении камеры ${num}: ${error.message}`, 'error');
        showNotification(`Ошибка сети: ${error.message}`, 'error');
    }
}

// Проверка статуса камер
async function checkCameraStatus() {
    try {
        const response = await fetch('/camera_status');
        const status = await response.json();
        
        // Обновление статуса камер
        updateCameraStatus('camera1', status.camera1.connected, status.camera1.processing);
        updateCameraStatus('camera2', status.camera2.connected, status.camera2.processing);
        
        // Обновление площади сегментации
        updateSegmentationArea('camera1', status.camera1.segmentation_area || 0);
        updateSegmentationArea('camera2', status.camera2.segmentation_area || 0);
        
        // Обновление произведения площадей
        updateAreaProduct(status.area_product || 0);
        
        // Запуск видео потоков для подключенных камер
        if (status.camera1.connected) {
            startVideoStreams('camera1');
            document.getElementById('connect1').style.display = 'none';
            document.getElementById('disconnect1').style.display = 'inline-block';
        }
        
        if (status.camera2.connected) {
            startVideoStreams('camera2');
            document.getElementById('connect2').style.display = 'none';
            document.getElementById('disconnect2').style.display = 'inline-block';
        }
        
    } catch (error) {
        logMessage(`Ошибка проверки статуса камер: ${error.message}`, 'error');
    }
}

// Обновление статуса камеры
function updateCameraStatus(cameraId, connected, processing) {
    const num = cameraId === 'camera1' ? '1' : '2';
    const statusElement = document.getElementById(`status${num}`);
    
    if (!statusElement) return; // Защита от ошибок на странице событий
    
    const indicator = statusElement.querySelector('.status-indicator');
    const text = statusElement.querySelector('.indicator-text');
    
    cameraStates[cameraId].connected = connected;
    cameraStates[cameraId].processing = processing;
    
    if (connected && processing) {
        indicator.className = 'status-indicator processing';
        text.textContent = 'Обработка';
    } else if (connected) {
        indicator.className = 'status-indicator connected';
        text.textContent = 'Подключено';
    } else {
        indicator.className = 'status-indicator disconnected';
        text.textContent = 'Отключено';
    }
}

// Обновление площади сегментации для камеры
function updateSegmentationArea(cameraId, area) {
    const areaElement = document.getElementById(`${cameraId}-area`);
    const areaCard = document.querySelector(`#status${cameraId === 'camera1' ? '1' : '2'}`).parentElement.querySelector('.segmentation-area-card');
    
    if (areaElement) {
        const oldValue = cameraStates[cameraId].segmentation_area;
        cameraStates[cameraId].segmentation_area = area;
        
        // Форматируем большие числа
        areaElement.textContent = formatNumber(area);
        
        // Добавляем анимацию при изменении
        if (oldValue !== area && area > 0) {
            areaElement.classList.add('updating');
            if (areaCard) areaCard.classList.add('active');
            
            setTimeout(() => {
                areaElement.classList.remove('updating');
                if (areaCard) areaCard.classList.remove('active');
            }, 500);
        }
    }
    
    // Обновляем формулу в произведении
    updateFormulaDisplay();
}

// Обновление произведения площадей
function updateAreaProduct(product) {
    const productElement = document.getElementById('area-product');
    const productSection = document.querySelector('.segmentation-product-section');
    
    if (productElement) {
        const oldValue = segmentationStats.area_product;
        segmentationStats.area_product = product;
        
        // Форматируем большие числа
        productElement.textContent = formatNumber(product);
        
        // Добавляем анимацию при изменении
        if (oldValue !== product && product > 0) {
            productElement.classList.add('updating');
            if (productSection) productSection.classList.add('active');
            
            setTimeout(() => {
                productElement.classList.remove('updating');
                if (productSection) productSection.classList.remove('active');
            }, 500);
        }
    }
}

// Обновление отображения формулы
function updateFormulaDisplay() {
    const formulaArea1 = document.getElementById('formula-area1');
    const formulaArea2 = document.getElementById('formula-area2');
    
    if (formulaArea1) formulaArea1.textContent = formatNumber(cameraStates.camera1.segmentation_area);
    if (formulaArea2) formulaArea2.textContent = formatNumber(cameraStates.camera2.segmentation_area);
}

// Форматирование больших чисел
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// Обновление дополнительной статистики сегментации
async function updateSegmentationStats() {
    try {
        const response = await fetch('/get_segmentation_stats');
        const stats = await response.json();
        
        // Обновляем максимальное и среднее произведение
        const maxProductElement = document.getElementById('max-product');
        const avgProductElement = document.getElementById('avg-product');
        
        if (maxProductElement) {
            maxProductElement.textContent = formatNumber(stats.max_product || 0);
        }
        
        if (avgProductElement) {
            avgProductElement.textContent = formatNumber(stats.average_product || 0);
        }
        
        // Сохраняем статистику
        segmentationStats = {
            ...segmentationStats,
            max_product: stats.max_product || 0,
            average_product: stats.average_product || 0,
            total_calculations: stats.total_calculations || 0
        };
        
    } catch (error) {
        console.error('Ошибка обновления статистики сегментации:', error);
    }
}

// Обновление отображения сегментации
function updateSegmentationDisplay() {
    updateSegmentationArea('camera1', cameraStates.camera1.segmentation_area);
    updateSegmentationArea('camera2', cameraStates.camera2.segmentation_area);
    updateAreaProduct(segmentationStats.area_product);
    updateFormulaDisplay();
}

// Запуск видео потоков
function startVideoStreams(cameraId) {
    const num = cameraId === 'camera1' ? '1' : '2';
    const processedImg = document.getElementById(`processed${num}`);
    
    if (!processedImg) return; // Защита от ошибок на странице событий
    
    // Добавление timestamp для предотвращения кеширования
    const timestamp = new Date().getTime();
    
    // Только обработанный поток
    processedImg.src = `/video_feed/${cameraId}?t=${timestamp}`;
    
    // Показ изображения и скрытие placeholder текста
    processedImg.style.display = 'block';
    
    // Исправленный селектор для placeholder текста
    const videoPlaceholder = processedImg.parentElement;
    const placeholderText = videoPlaceholder.querySelector('.placeholder-text');
    if (placeholderText) {
        placeholderText.style.display = 'none';
    }
    
    logMessage(`Видео поток для камеры ${num} запущен`);
}

// Остановка видео потоков
function stopVideoStreams(cameraId) {
    const num = cameraId === 'camera1' ? '1' : '2';
    const processedImg = document.getElementById(`processed${num}`);
    
    if (!processedImg) return; // Защита от ошибок на странице событий
    
    processedImg.src = '';
    
    // Скрытие изображения и показ placeholder текста
    processedImg.style.display = 'none';
    
    // Исправленный селектор для placeholder текста
    const videoPlaceholder = processedImg.parentElement;
    const placeholderText = videoPlaceholder.querySelector('.placeholder-text');
    if (placeholderText) {
        placeholderText.style.display = 'block';
    }
    
    logMessage(`Видео поток для камеры ${num} остановлен`);
}

// Запуск периодических обновлений статуса
function startStatusUpdates() {
    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch('/camera_status');
            const status = await response.json();
            
            // Проверка изменений в статусе камер
            if (status.camera1.connected !== cameraStates.camera1.connected ||
                status.camera1.processing !== cameraStates.camera1.processing) {
                updateCameraStatus('camera1', status.camera1.connected, status.camera1.processing);
            }
            
            if (status.camera2.connected !== cameraStates.camera2.connected ||
                status.camera2.processing !== cameraStates.camera2.processing) {
                updateCameraStatus('camera2', status.camera2.connected, status.camera2.processing);
            }
            
            // Обновление площади сегментации
            updateSegmentationArea('camera1', status.camera1.segmentation_area || 0);
            updateSegmentationArea('camera2', status.camera2.segmentation_area || 0);
            updateAreaProduct(status.area_product || 0);
            
        } catch (error) {
            console.error('Ошибка обновления статуса:', error);
        }
    }, 2000); // Проверка каждые 2 секунды для более частого обновления площади
}

// Запуск обновлений статистики сегментации
function startSegmentationUpdates() {
    segmentationUpdateInterval = setInterval(updateSegmentationStats, 5000); // Каждые 5 секунд
}

// Простое логирование в консоль
function logMessage(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'success' ? '✓' : type === 'error' ? '✗' : '►';
    console.log(`[${timestamp}] ${prefix} ${message.toUpperCase()}`);
}

// Показ уведомления
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notification-text');
    const notificationContent = notification.querySelector('.notification-content');
    
    notificationText.textContent = message;
    notificationContent.className = `notification-content ${type}`;
    
    notification.classList.add('show');
    
    // Автоматическое скрытие через 5 секунд
    setTimeout(() => {
        hideNotification();
    }, 5000);
}

// Скрытие уведомления
function hideNotification() {
    const notification = document.getElementById('notification');
    notification.classList.remove('show');
}

// Глобальные функции для интеграции с HTML
window.checkCameraStatus = checkCameraStatus;
window.updateMainPageStats = function() {
    checkCameraStatus();
    updateSegmentationStats();
};

// Очистка при закрытии страницы
window.addEventListener('beforeunload', function() {
    clearInterval(statusCheckInterval);
    clearInterval(segmentationUpdateInterval);
    
    // Логируем финальную статистику
    logMessage(`Финальная статистика: произведение=${segmentationStats.area_product}, максимум=${segmentationStats.max_product}, среднее=${segmentationStats.average_product}`);
});