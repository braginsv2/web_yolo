"""
config.py - Конфигурация и константы системы
"""
from pathlib import Path
import torch

# Основные пути проекта
BASE_DIR = Path("D:/yolo_train")
MODELS_DIR = BASE_DIR / "models"
WEBAPP_DIR = BASE_DIR / "webFlask"
ALARMS_BASE_DIR = WEBAPP_DIR / "alarms"

# Папки для алармов
PENDING_DIR = ALARMS_BASE_DIR / "pending"      # Неоцененные алармы
CORRECT_DIR = ALARMS_BASE_DIR / "correct"      # Верно определенные
INCORRECT_DIR = ALARMS_BASE_DIR / "incorrect"  # Неверно определенные

# Файл статистики
STATS_FILE = ALARMS_BASE_DIR / "statistics.json"

# Настройки алармов
ALARM_COOLDOWN = 5.0  # Секунд между алармами
MAX_PENDING_ALARMS = 100  # Максимум неоцененных алармов
MAX_EVALUATED_ALARMS = 100  # Максимум в каждой категории оцененных

# Настройки камер
CAMERA_CONFIG = {
    'buffer_size': 1,
    'fps': 15,
    'width': 640,
    'height': 480,
    'fourcc': 'H264',
    'open_timeout': 10000,
    'read_timeout': 5000,
    'max_attempts': 5
}

# Настройки обработки
PROCESSING_CONFIG = {
    'frame_skip': 2,  # Обрабатывать каждый 2-й кадр
    'queue_maxsize': 5,
    'jpeg_quality': 70
}

# Веб-сервер
SERVER_CONFIG = {
    'host': '127.0.0.1',
    'port': 5000,
    'debug': False,
    'threaded': True,
    'browser_delay': 1.5  # Секунд до открытия браузера
}

# Логирование
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

# YOLO модели
YOLO_MODELS = {
    'segmentation': 'yolov8n-seg.pt',
    'detection': 'yolov8n.pt'
}

# Классы объектов
OBJECT_CLASSES = {
    'person': 0
}

# CUDA и GPU настройки
def detect_device():
    """Автоматическое определение лучшего доступного устройства"""

    if torch.cuda.is_available():
        device = 'cuda'
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
        return {
            'device': device,
            'available': True,
            'gpu_name': gpu_name,
            'gpu_memory_gb': round(gpu_memory, 1),
            'gpu_count': torch.cuda.device_count()
        }
    else:
        return {
            'device': 'cpu',
            'available': False,
            'gpu_name': None,
            'gpu_memory_gb': 0,
            'gpu_count': 0
        }

# Получаем информацию о устройстве при импорте
DEVICE_INFO = detect_device()

# Настройки CUDA
CUDA_CONFIG = {
    'device': DEVICE_INFO['device'],
    'use_half_precision': DEVICE_INFO['available'],  # Использовать FP16 если есть CUDA
    'batch_size': 1,  # Размер batch для обработки
    'memory_fraction': 0.8,  # Доля GPU памяти для использования
}

# Настройки производительности YOLO
YOLO_CONFIG = {
    'device': CUDA_CONFIG['device'],
    'half': CUDA_CONFIG['use_half_precision'],
    'imgsz': 640,  # Размер входного изображения
    'conf': 0.25,  # Порог уверенности
    'iou': 0.45,   # IoU порог для NMS
    'max_det': 300,  # Максимум детекций на изображение
    'verbose': False,
    'save': False,
    'save_txt': False,
    'save_crop': False,
    'show_labels': True,
    'show_conf': True,
    'vid_stride': 1,  # Шаг кадров для видео
    'stream_buffer': False,
    'visualize': False,
}

def create_directories():
    """Создание необходимых директорий"""
    directories = [
        MODELS_DIR,
        ALARMS_BASE_DIR,
        PENDING_DIR,
        CORRECT_DIR,
        INCORRECT_DIR
    ]

    for directory in directories:
        directory.mkdir(exist_ok=True)

def get_camera_streams_config():
    """Конфигурация для глобальной переменной camera_streams"""

    return {
        'camera1': {
            'cap': None,
            'connected': False,
            'frame': None,
            'processed_frame': None,
            'config': {},
            'processing': False,
            'frame_queue': None,  # Будет создана deque в main
            'frame_counter': 0,
            'last_alarm_time': 0
        },

        'camera2': {
            'cap': None,
            'connected': False,
            'frame': None,
            'processed_frame': None,
            'config': {},
            'processing': False,
            'frame_queue': None,  # Будет создана deque в main
            'frame_counter': 0,
            'last_alarm_time': 0
        }
    }

def get_performance_recommendations():
    """Получение рекомендаций по производительности"""

    device_info = DEVICE_INFO
    recommendations = []    

    if device_info['available']:
        # CUDA доступна
        recommendations.append("✅ CUDA доступна - будет использоваться GPU ускорение")
        recommendations.append(f"🔥 GPU: {device_info['gpu_name']}")
        recommendations.append(f"💾 GPU память: {device_info['gpu_memory_gb']} GB")     

        if device_info['gpu_memory_gb'] >= 4:
            recommendations.append("🚀 Достаточно GPU памяти для оптимальной работы")
        else:
            recommendations.append("⚠️ Ограниченная GPU память - возможны замедления")
          
        if device_info['gpu_count'] > 1:
            recommendations.append(f"🔄 Обнаружено {device_info['gpu_count']} GPU (используется первый)")
    else:
        # Только CPU
        recommendations.append("⚠️ CUDA не доступна - будет использоваться CPU")
        recommendations.append("💡 Для ускорения установите CUDA и PyTorch с GPU поддержкой")
        recommendations.append("📖 Инструкция: https://pytorch.org/get-started/locally/")

    return recommendations

def optimize_for_device():
    """Оптимизация настроек для текущего устройства"""
    if DEVICE_INFO['available']:
        # Оптимизация для GPU
        YOLO_CONFIG.update({
            'half': True,  # Используем FP16
            'imgsz': 640,  # Оптимальный размер для большинства GPU
            'max_det': 300,
        })

        PROCESSING_CONFIG.update({
            'frame_skip': 1,  # Меньше пропускаем кадров на GPU
            'queue_maxsize': 8,  # Больше очередь для GPU
        })      

        # Настройка памяти GPU
        if DEVICE_INFO['gpu_memory_gb'] >= 8:
            PROCESSING_CONFIG['queue_maxsize'] = 10
            YOLO_CONFIG['max_det'] = 500
        elif DEVICE_INFO['gpu_memory_gb'] < 4:
            PROCESSING_CONFIG['queue_maxsize'] = 5
            YOLO_CONFIG['max_det'] = 200
            YOLO_CONFIG['imgsz'] = 416  # Меньший размер для экономии памяти
    else:
        # Оптимизация для CPU
        YOLO_CONFIG.update({
            'half': False,  # FP16 не поддерживается на CPU
            'imgsz': 416,   # Меньший размер для CPU
            'max_det': 100,
        })

        PROCESSING_CONFIG.update({
            'frame_skip': 3,  # Больше пропускаем кадров на CPU
            'queue_maxsize': 3,  # Меньшая очередь для CPU
        })

# Применяем оптимизации при импорте
optimize_for_device()