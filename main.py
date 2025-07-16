"""
main.py - Главный файл Flask приложения системы видеоаналитики с подсчетом площади сегментации
"""

import logging
import webbrowser
from collections import deque
from threading import Timer
from flask import Flask

# Импорты модулей приложения
from config import (
    create_directories, get_camera_streams_config, 
    SERVER_CONFIG, LOGGING_CONFIG
)

from model_manager import ModelManager
from alarm_manager import AlarmManager
from camera_processor import CameraProcessor, VideoStreamGenerator, SegmentationAreaManager
from flask_routes import FlaskRoutes, CameraManager

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG['level']),
    format=LOGGING_CONFIG['format']
)
logger = logging.getLogger(__name__)

class VideoAnalyticsApp:
    """Главный класс приложения системы видеоаналитики"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.model_manager = ModelManager()
        self.alarm_manager = AlarmManager()
        
        # Создаем менеджер площади сегментации
        self.segmentation_area_manager = SegmentationAreaManager()
        
        # Создаем структуру камер
        self.camera_streams = get_camera_streams_config()
        self._initialize_camera_queues()
        
        # Создаем процессоры камер
        self.processors = self._create_camera_processors()
        
        # Создаем менеджер камер
        self.camera_manager = CameraManager(
            self.camera_streams, 
            self.processors, 
            self.model_manager,
            self.segmentation_area_manager  # Передаем менеджер площади
        )
        
        # Создаем генератор видеопотоков
        self.video_generator = VideoStreamGenerator(self.camera_streams)
        
        # Регистрируем маршруты
        self.routes = FlaskRoutes(
            self.app,
            self.camera_manager,
            self.alarm_manager,
            self.video_generator
        )

    def _initialize_camera_queues(self):
        """Инициализация очередей кадров для камер"""
        for camera_id in self.camera_streams:
            self.camera_streams[camera_id]['frame_queue'] = deque(maxlen=2)
            # Добавляем поле для площади сегментации
            self.camera_streams[camera_id]['segmentation_area'] = 0

    def _create_camera_processors(self) -> dict:
        """Создание процессоров для камер"""
        processors = {}
        
        # Функция callback для создания алармов
        def alarm_callback(camera_id: str, frame):
            self.alarm_manager.create_alarm(camera_id, frame)
        
        # Функция callback для обновления площади сегментации
        def segmentation_callback(camera_id: str, area: int):
            self.segmentation_area_manager.update_camera_area(camera_id, area)
        
        # Создаем процессоры для каждой камеры
        for camera_id in ['camera1', 'camera2']:
            processors[camera_id] = CameraProcessor(
                camera_id=camera_id,
                camera_streams=self.camera_streams,
                yolo_model=None,  # Будет установлена позже в _update_processors_models
                alarm_callback=alarm_callback,
                model_manager=self.model_manager,
                segmentation_callback=segmentation_callback  # Новый callback
            )
        
        return processors

    def initialize(self):
        """Инициализация приложения"""
        logger.info("🚀 Инициализация приложения...")
        
        # Создаем необходимые директории
        create_directories()
        logger.info("📁 Директории созданы")
        
        # Загружаем модели YOLO
        models_loaded = self.model_manager.load_models()
        if models_loaded:
            logger.info("🤖 YOLO модели загружены успешно")
            # Обновляем процессоры с загруженными моделями
            self._update_processors_models()
        else:
            logger.warning("⚠️ Не удалось загрузить YOLO модели")
        
        # Загружаем статистику и алармы
        self.alarm_manager.load_statistics()
        self.alarm_manager.load_alarms_from_folders()
        logger.info("📊 Статистика и алармы загружены")
        
        logger.info("✅ Инициализация завершена")

    def _update_processors_models(self):
        """Обновление моделей в процессорах"""
        segmentation_model = self.model_manager.get_segmentation_model()
        
        for processor in self.processors.values():
            processor.yolo_model = segmentation_model

    def run(self):
        """Запуск приложения"""
        try:
            logger.info("🌐 Запуск веб-сервера...")
            
            # Открываем браузер с задержкой
            Timer(SERVER_CONFIG['browser_delay'], self._open_browser).start()
            
            # Выводим информацию о запуске
            self._print_startup_info()
            
            # Запускаем Flask приложение
            self.app.run(
                debug=SERVER_CONFIG['debug'],
                host=SERVER_CONFIG['host'],
                port=SERVER_CONFIG['port'],
                threaded=SERVER_CONFIG['threaded']
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Приложение остановлено пользователем")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
        finally:
            self._cleanup()

    def _open_browser(self):
        """Открытие браузера"""
        url = f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/"
        webbrowser.open_new(url)
        logger.info(f"🌐 Браузер открыт: {url}")

    def _print_startup_info(self):
        """Вывод информации о запуске"""
        logger.info("=" * 70)
        logger.info("🎯 СИСТЕМА ВИДЕОАНАЛИТИКИ ЗАПУЩЕНА")
        logger.info("=" * 70)
        logger.info(f"🌐 URL: http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
        
        # Информация о устройстве и моделях
        model_info = self.model_manager.get_model_info()
        device_info = model_info['device_info']
        
        logger.info("🤖 Информация о моделях:")
        logger.info(f"   📊 Статус: {'✅ Загружены' if model_info['models_loaded'] else '❌ Не загружены'}")
        logger.info(f"   💻 Устройство: {device_info['device'].upper()}")
        
        if device_info['available']:
            logger.info(f"   🔥 GPU: {device_info['gpu_name']}")
            logger.info(f"   💾 GPU память: {device_info['gpu_memory_gb']} GB")
            
            # Показываем рекомендации по производительности
            from config import get_performance_recommendations
            recommendations = get_performance_recommendations()
            logger.info("💡 Рекомендации по производительности:")
            for rec in recommendations:
                logger.info(f"   {rec}")
        else:
            logger.info("   ⚠️ CUDA не доступна - используется CPU")
            logger.info("   💡 Для ускорения установите CUDA и PyTorch с GPU поддержкой")
        
        # Информация о папках алармов
        from config import PENDING_DIR, CORRECT_DIR, INCORRECT_DIR
        logger.info("📁 Папки алармов:")
        logger.info(f"   📋 Неоцененные: {PENDING_DIR}")
        logger.info(f"   ✅ Верные: {CORRECT_DIR}")
        logger.info(f"   ❌ Неверные: {INCORRECT_DIR}")
        
        # Статистика алармов
        stats = self.alarm_manager.get_statistics()
        logger.info("📊 Статистика алармов:")
        logger.info(f"   📊 Всего: {stats['total_alarms']}")
        logger.info(f"   ⏳ Ожидают оценки: {stats['pending_alarms']}")
        logger.info(f"   ✅ Верных: {stats['correct_alarms']}")
        logger.info(f"   ❌ Неверных: {stats['incorrect_alarms']}")
        logger.info(f"   🎯 Точность: {stats['accuracy_percentage']}%")
        
        # Настройки производительности
        from config import YOLO_CONFIG, PROCESSING_CONFIG
        logger.info("⚙️ Настройки производительности:")
        logger.info(f"   🖼️ Размер изображения: {YOLO_CONFIG['imgsz']}")
        logger.info(f"   🔧 Precision: {'FP16' if YOLO_CONFIG['half'] else 'FP32'}")
        logger.info(f"   📊 Пропуск кадров: каждый {PROCESSING_CONFIG['frame_skip']}-й")
        logger.info(f"   🔄 Размер очереди: {PROCESSING_CONFIG['queue_maxsize']}")
        
        # Информация о площади сегментации
        logger.info("🔍 Подсчет площади сегментации:")
        logger.info("   📐 Камера 1: Сегментация людей с подсчетом площади")
        logger.info("   📐 Камера 2: Детекция + сегментация с подсчетом площади")
        logger.info("   ✖️ Произведение площадей: автоматический расчет")
        
        logger.info("=" * 70)

    def _cleanup(self):
        """Очистка ресурсов при завершении"""
        logger.info("🧹 Очистка ресурсов...")
        
        try:
            # Отключаем все камеры
            for camera_id in ['camera1', 'camera2']:
                if self.camera_manager.is_camera_connected(camera_id):
                    self.camera_manager.disconnect_camera(camera_id)
                    logger.info(f"📹 Камера {camera_id} отключена")
            
            # Выгружаем модели из памяти
            self.model_manager.unload_models()
            logger.info("🤖 YOLO модели выгружены")
            
            # Сохраняем финальную статистику
            self.alarm_manager.save_statistics()
            logger.info("💾 Статистика сохранена")
            
            # Выводим финальную статистику площади сегментации
            final_stats = self.segmentation_area_manager.get_stats()
            logger.info("📐 Финальная статистика площади сегментации:")
            logger.info(f"   📊 Всего расчетов: {final_stats['total_calculations']}")
            logger.info(f"   📈 Максимальное произведение: {final_stats['max_product']}")
            logger.info(f"   📊 Среднее произведение: {final_stats['average_product']}")
            logger.info(f"   ✅ Ненулевых произведений: {final_stats['non_zero_products']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке: {e}")
        
        logger.info("✅ Очистка завершена")


def main():
    """Главная функция запуска приложения"""
    try:
        # Создаем и инициализируем приложение
        app = VideoAnalyticsApp()
        app.initialize()
        
        # Запускаем приложение
        app.run()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())