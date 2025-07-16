/**
 * events.js - Логика для страницы журнала событий с поддержкой площади сегментации
 * Управление алармами, их оценкой и статистикой
 */

// Глобальные переменные
let alarmsData = [];
let updateInterval;
let segmentationUpdateInterval;

// Данные для статистики сегментации
let segmentationData = {
    camera1_area: 0,
    camera2_area: 0,
    current_product: 0,
    max_product: 0,
    average_product: 0,
    total_calculations: 0
};

// Инициализация страницы событий
document.addEventListener('DOMContentLoaded', function() {
    initializeEventsPage();
});

/**
 * Инициализация страницы событий
 */
function initializeEventsPage() {
    setupEventListeners();
    loadAlarms();
    updateStats();
    updateSegmentationStats();
    startAutoUpdate();
    
    console.log('📋 Страница событий инициализирована');
}

/**
 * Настройка обработчиков событий
 */
function setupEventListeners() {
    // Модальное окно изображения
    const imageModal = document.getElementById('image-modal');
    if (imageModal) {
        imageModal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeImageModal();
            }
        });
    }

    const modalClose = document.querySelector('.modal-close');
    if (modalClose) {
        modalClose.addEventListener('click', closeImageModal);
    }

    // Закрытие уведомлений
    const notificationClose = document.getElementById('notification-close');
    if (notificationClose) {
        notificationClose.addEventListener('click', hideNotification);
    }

    // Обработка клавиши Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeImageModal();
        }
    });
    
    console.log('✅ Обработчики событий настроены');
}

/**
 * Загрузка алармов с сервера
 */
async function loadAlarms() {
    try {
        console.log('🔄 Загрузка алармов...');
        
        const response = await fetch('/get_alarms');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        alarmsData = data.alarms || [];
        updateAlarmsDisplay();
        updateCounter(data.total_pending || 0);
        
        console.log(`✅ Загружено ${alarmsData.length} алармов`);
        
    } catch (error) {
        console.error('❌ Ошибка загрузки алармов:', error);
        showNotification('Ошибка загрузки алармов', 'error');
    }
}

/**
 * Обновление отображения алармов в интерфейсе
 */
function updateAlarmsDisplay() {
    const container = document.getElementById('alarms-list');
    if (!container) return;
    
    if (alarmsData.length === 0) {
        container.innerHTML = '<div class="no-alarms">Алармы отсутствуют</div>';
        return;
    }

    const html = alarmsData.map(alarm => createAlarmHTML(alarm)).join('');
    container.innerHTML = html;
    
    console.log(`📋 Отображено ${alarmsData.length} алармов`);
}

/**
 * Создание HTML для одного аларма
 */
function createAlarmHTML(alarm) {
    const date = new Date(alarm.timestamp);
    const timeString = date.toLocaleString('ru-RU');
    const cameraName = alarm.camera_id === 'camera1' ? 'Камера №1' : 'Камера №2';
    const imageUrl = `/alarm_image/${alarm.filename}`;
    
    return `
        <div class="alarm-item" data-alarm-id="${alarm.id}">
            <div class="alarm-header">
                <div class="alarm-camera">${cameraName}</div>
                <div class="alarm-time">${timeString}</div>
            </div>
            <img src="${imageUrl}" 
                 alt="Аларм" 
                 class="alarm-image"
                 onload="console.log('✅ Изображение загружено:', '${alarm.filename}')"
                 onerror="handleImageError(this, '${alarm.filename}')"
                 onclick="openImageModal('${imageUrl}')">
            <div class="alarm-actions">
                <button class="btn-correct" onclick="evaluateAlarm('${alarm.id}', true)">
                    ✓ Верно
                </button>
                <button class="btn-incorrect" onclick="evaluateAlarm('${alarm.id}', false)">
                    ✗ Неверно
                </button>
            </div>
        </div>
    `;
}

/**
 * Обработка ошибки загрузки изображения
 */
function handleImageError(img, filename) {
    console.error('❌ Ошибка загрузки изображения:', filename);
    img.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzMzMzMzMyIvPjx0ZXh0IHg9IjE1MCIgeT0iMTAwIiBmaWxsPSIjZmZmZmZmIiBmb250LXNpemU9IjE2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5JbWFnZSBub3QgZm91bmQ8L3RleHQ+PC9zdmc+';
}

/**
 * Обновление счетчика алармов
 */
function updateCounter(count) {
    const counter = document.getElementById('alarms-counter');
    if (counter) {
        counter.textContent = count;
    }
}

/**
 * Оценка аларма пользователем
 */
async function evaluateAlarm(alarmId, isCorrect) {
    try {
        console.log(`🔄 Оценка аларма ${alarmId} как ${isCorrect ? 'верный' : 'неверный'}`);
        
        const alarmElement = document.querySelector(`[data-alarm-id="${alarmId}"]`);
        if (!alarmElement) {
            throw new Error('Элемент аларма не найден');
        }
        
        // Блокируем элемент на время обработки
        setAlarmEvaluating(alarmElement, true);

        const response = await fetch('/evaluate_alarm', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                alarm_id: alarmId,
                is_correct: isCorrect
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        if (result.status === 'success') {
            showNotification(
                `Аларм оценен как ${isCorrect ? 'верный' : 'неверный'} и перемещен в соответствующую папку`, 
                'success'
            );
            
            // Анимация удаления
            animateAlarmRemoval(alarmElement);
            
            // Обновляем данные через 300ms
            setTimeout(() => {
                loadAlarms();
                updateStats();
            }, 300);
            
            console.log(`✅ Аларм ${alarmId} успешно оценен`);
            
        } else {
            throw new Error(result.message || 'Ошибка оценки аларма');
        }

    } catch (error) {
        console.error('❌ Ошибка оценки аларма:', error);
        showNotification('Ошибка при оценке аларма: ' + error.message, 'error');
        
        // Восстанавливаем элемент при ошибке
        const alarmElement = document.querySelector(`[data-alarm-id="${alarmId}"]`);
        if (alarmElement) {
            setAlarmEvaluating(alarmElement, false);
        }
    }
}

/**
 * Установка состояния "оценивается" для аларма
 */
function setAlarmEvaluating(alarmElement, isEvaluating) {
    const buttons = alarmElement.querySelectorAll('button');
    
    if (isEvaluating) {
        alarmElement.classList.add('evaluating');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span>';
        });
    } else {
        alarmElement.classList.remove('evaluating');
        buttons.forEach(btn => {
            btn.disabled = false;
        });
        if (buttons.length >= 2) {
            buttons[0].innerHTML = '✓ Верно';
            buttons[1].innerHTML = '✗ Неверно';
        }
    }
}

/**
 * Анимация удаления аларма
 */
function animateAlarmRemoval(alarmElement) {
    alarmElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    alarmElement.style.opacity = '0';
    alarmElement.style.transform = 'translateX(100%)';
}

/**
 * Обновление статистики
 */
async function updateStats() {
    try {
        const response = await fetch('/camera_status');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Основная статистика
        updateStatElement('total-alarms', data.total_alarms || 0);
        updateStatElement('pending-alarms', data.pending_alarms || 0);
        updateStatElement('correct-alarms', data.correct_alarms || 0);
        updateStatElement('incorrect-alarms', data.incorrect_alarms || 0);
        updateStatElement('accuracy-percent', (data.accuracy_percentage || 0) + '%');
        
        // Статистика по папкам
        updateStatElement('pending-count', data.pending_alarms || 0);
        updateStatElement('correct-count', data.correct_alarms || 0);
        updateStatElement('incorrect-count', data.incorrect_alarms || 0);
        
        console.log('📊 Статистика обновлена');
        
    } catch (error) {
        console.error('❌ Ошибка обновления статистики:', error);
    }
}

/**
 * Обновление статистики площади сегментации
 */
async function updateSegmentationStats() {
    try {
        const response = await fetch('/get_segmentation_stats');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Сохраняем предыдущие значения для анимации
        const prevData = { ...segmentationData };
        
        // Обновляем данные
        segmentationData = {
            camera1_area: data.camera1_area || 0,
            camera2_area: data.camera2_area || 0,
            current_product: data.current_product || 0,
            max_product: data.max_product || 0,
            average_product: data.average_product || 0,
            total_calculations: data.total_calculations || 0
        };
        
        // Обновляем отображение с анимацией
        updateSegmentationDisplay(prevData);
        
        console.log('📐 Статистика сегментации обновлена');
        
    } catch (error) {
        console.error('❌ Ошибка обновления статистики сегментации:', error);
    }
}

/**
 * Обновление отображения статистики сегментации
 */
function updateSegmentationDisplay(prevData = {}) {
    // Форматирование больших чисел
    function formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }
    
    // Функция для обновления элемента с анимацией
    function updateElementWithAnimation(elementId, newValue, oldValue) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = formatNumber(newValue);
            
            // Добавляем анимацию если значение изменилось
            if (oldValue !== undefined && oldValue !== newValue && newValue > 0) {
                element.classList.add('updating');
                setTimeout(() => {
                    element.classList.remove('updating');
                }, 600);
            }
        }
    }
    
    // Обновляем площади камер
    updateElementWithAnimation('camera1-current-area', segmentationData.camera1_area, prevData.camera1_area);
    updateElementWithAnimation('camera2-current-area', segmentationData.camera2_area, prevData.camera2_area);
    
    // Обновляем произведение (с выделением)
    updateElementWithAnimation('current-product', segmentationData.current_product, prevData.current_product);
    
    // Обновляем дополнительную статистику
    updateElementWithAnimation('max-product-stat', segmentationData.max_product, prevData.max_product);
    updateElementWithAnimation('avg-product-stat', segmentationData.average_product, prevData.average_product);
    updateElementWithAnimation('total-calculations', segmentationData.total_calculations, prevData.total_calculations);
    
    // Обновляем формулу
    updateFormulaDisplay(prevData);
}

/**
 * Обновление отображения формулы
 */
function updateFormulaDisplay(prevData = {}) {
    function formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }
    
    // Функция для обновления элемента формулы с анимацией
    function updateFormulaElement(elementId, newValue, oldValue) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = formatNumber(newValue);
            
            // Добавляем анимацию если значение изменилось
            if (oldValue !== undefined && oldValue !== newValue) {
                element.classList.add('updating');
                setTimeout(() => {
                    element.classList.remove('updating');
                }, 600);
            }
        }
    }
    
    updateFormulaElement('formula-cam1', segmentationData.camera1_area, prevData.camera1_area);
    updateFormulaElement('formula-cam2', segmentationData.camera2_area, prevData.camera2_area);
    updateFormulaElement('formula-result', segmentationData.current_product, prevData.current_product);
}

/**
 * Обновление отдельного элемента статистики
 */
function updateStatElement(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = value;
    }
}

/**
 * Открытие модального окна изображения
 */
function openImageModal(imageSrc) {
    const modal = document.getElementById('image-modal');
    const modalImage = document.getElementById('modal-image');
    
    if (modal && modalImage) {
        modalImage.src = imageSrc;
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        
        console.log('🖼️ Модальное окно открыто');
    }
}

/**
 * Закрытие модального окна изображения
 */
function closeImageModal() {
    const modal = document.getElementById('image-modal');
    
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
        
        console.log('❌ Модальное окно закрыто');
    }
}

/**
 * Показ уведомления
 */
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notification-text');
    const notificationContent = notification?.querySelector('.notification-content');
    
    if (notification && notificationText && notificationContent) {
        notificationText.textContent = message;
        notificationContent.className = `notification-content ${type}`;
        notification.classList.add('show');
        
        // Автоматическое скрытие через 4 секунды
        setTimeout(hideNotification, 4000);
        
        console.log(`📢 Уведомление (${type}): ${message}`);
    }
}

/**
 * Скрытие уведомления
 */
function hideNotification() {
    const notification = document.getElementById('notification');
    if (notification) {
        notification.classList.remove('show');
    }
}

/**
 * Запуск автоматического обновления
 */
function startAutoUpdate() {
    // Обновление алармов и основной статистики каждые 5 секунд
    updateInterval = setInterval(() => {
        loadAlarms();
        updateStats();
    }, 5000);
    
    // Обновление статистики сегментации каждые 2 секунды (более частое обновление)
    segmentationUpdateInterval = setInterval(() => {
        updateSegmentationStats();
    }, 2000);
    
    console.log('🔄 Автоматическое обновление запущено');
    console.log('   📊 Алармы и статистика: каждые 5 сек');
    console.log('   📐 Площадь сегментации: каждые 2 сек');
}

/**
 * Остановка автоматического обновления при закрытии страницы
 */
window.addEventListener('beforeunload', function() {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    if (segmentationUpdateInterval) {
        clearInterval(segmentationUpdateInterval);
    }
    
    // Логируем финальную статистику
    console.log('⏹️ Автоматическое обновление остановлено');
    console.log('📐 Финальная статистика сегментации:');
    console.log(`   Камера 1: ${segmentationData.camera1_area} пикс`);
    console.log(`   Камера 2: ${segmentationData.camera2_area} пикс`);
    console.log(`   Произведение: ${segmentationData.current_product} пикс²`);
    console.log(`   Максимальное: ${segmentationData.max_product} пикс²`);
    console.log(`   Среднее: ${segmentationData.average_product} пикс²`);
    console.log(`   Всего расчетов: ${segmentationData.total_calculations}`);
});

/**
 * Дополнительные функции для мониторинга производительности
 */

/**
 * Проверка активности сегментации
 */
function checkSegmentationActivity() {
    const isActive = segmentationData.camera1_area > 0 || segmentationData.camera2_area > 0;
    
    // Добавляем визуальные индикаторы активности
    const camera1Card = document.querySelector('#camera1-current-area').closest('.segmentation-stat-card');
    const camera2Card = document.querySelector('#camera2-current-area').closest('.segmentation-stat-card');
    const productCard = document.querySelector('#current-product').closest('.segmentation-stat-card');
    
    if (camera1Card) {
        camera1Card.classList.toggle('active', segmentationData.camera1_area > 0);
    }
    if (camera2Card) {
        camera2Card.classList.toggle('active', segmentationData.camera2_area > 0);
    }
    if (productCard) {
        productCard.classList.toggle('active', segmentationData.current_product > 0);
    }
    
    return isActive;
}

/**
 * Получение статистики для отладки
 */
function getDebugInfo() {
    return {
        alarms: {
            loaded: alarmsData.length,
            intervals: {
                main: updateInterval ? 'активен' : 'остановлен',
                segmentation: segmentationUpdateInterval ? 'активен' : 'остановлен'
            }
        },
        segmentation: segmentationData,
        activity: checkSegmentationActivity()
    };
}

/**
 * Экспорт статистики в консоль (для отладки)
 */
function exportSegmentationStats() {
    const stats = {
        timestamp: new Date().toISOString(),
        data: segmentationData,
        formatted: {
            camera1_area: formatNumber(segmentationData.camera1_area),
            camera2_area: formatNumber(segmentationData.camera2_area),
            current_product: formatNumber(segmentationData.current_product),
            max_product: formatNumber(segmentationData.max_product),
            average_product: formatNumber(segmentationData.average_product)
        }
    };
    
    console.log('📊 Экспорт статистики сегментации:', stats);
    return stats;
}

/**
 * Форматирование чисел (вспомогательная функция)
 */
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// Периодическая проверка активности сегментации
setInterval(checkSegmentationActivity, 1000);

// Экспорт статистики каждые 30 секунд для отладки
setInterval(() => {
    if (segmentationData.current_product > 0) {
        exportSegmentationStats();
    }
}, 30000);

// Экспорт функций для глобального доступа
window.evaluateAlarm = evaluateAlarm;
window.openImageModal = openImageModal;
window.closeImageModal = closeImageModal;
window.getDebugInfo = getDebugInfo;
window.exportSegmentationStats = exportSegmentationStats;