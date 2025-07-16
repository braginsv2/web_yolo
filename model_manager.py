"""
model_manager.py - Управление YOLO моделями с поддержкой CUDA
"""
import logging
import torch
from typing import Optional, Dict, Any
from ultralytics import YOLO
from config import YOLO_MODELS, YOLO_CONFIG, DEVICE_INFO

logger = logging.getLogger(__name__)

class ModelManager:
    """Менеджер для управления YOLO моделями с поддержкой CUDA"""

    def __init__(self):

        self.yolo_seg_model: Optional[YOLO] = None
        self.yolo_det_model: Optional[YOLO] = None
        self.models_loaded = False
        self.device_info = DEVICE_INFO
        self.performance_stats = {
            'inference_times': [],
            'memory_usage': [],
            'total_inferences': 0
        }

    def load_models(self) -> bool:
        """Загрузка моделей YOLO с оптимизацией для устройства"""

        try:
            logger.info("🤖 Загрузка моделей YOLO...")
            self._log_device_info()

            # Загружаем модель сегментации
            logger.info(f"📦 Загрузка модели сегментации: {YOLO_MODELS['segmentation']}")
            self.yolo_seg_model = YOLO(YOLO_MODELS['segmentation'])
            self._configure_model(self.yolo_seg_model, "сегментации")

            # Загружаем модель детекции
            logger.info(f"📦 Загрузка модели детекции: {YOLO_MODELS['detection']}")
            self.yolo_det_model = YOLO(YOLO_MODELS['detection'])
            self._configure_model(self.yolo_det_model, "детекции")

            # Прогрев моделей
            self._warmup_models()
            self.models_loaded = True
            logger.info("✅ YOLO модели загружены и сконфигурированы успешно")

            # Выводим статистику производительности
            self._log_performance_info()
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки YOLO моделей: {e}")
            self.models_loaded = False
            return False

    def _log_device_info(self):
        """Логирование информации об устройстве"""
        logger.info("🔍 Информация об устройстве:")
        logger.info(f"   💻 Устройство: {self.device_info['device'].upper()}")       

        if self.device_info['available']:
            logger.info(f"   🔥 GPU: {self.device_info['gpu_name']}")
            logger.info(f"   💾 GPU память: {self.device_info['gpu_memory_gb']} GB")
            logger.info(f"   📊 Количество GPU: {self.device_info['gpu_count']}")

            # Дополнительная информация о CUDA
            if torch.cuda.is_available():
                logger.info(f"   🔧 CUDA версия: {torch.version.cuda}")
                logger.info(f"   ⚡ cuDNN версия: {torch.backends.cudnn.version()}")
                logger.info(f"   🎯 Архитектура GPU: {torch.cuda.get_device_capability(0)}")
        else:
            logger.warning("   ⚠️ CUDA не доступна - используется CPU")
            logger.info("   💡 Для ускорения установите CUDA и PyTorch с GPU поддержкой")

    def _configure_model(self, model: YOLO, model_type: str):
        """Конфигурация модели для оптимальной производительности"""

        try:
            # Переводим модель на нужное устройство
            model.to(self.device_info['device'])
            logger.info(f"   📍 Модель {model_type} перенесена на {self.device_info['device'].upper()}")
            # Настройка precision для GPU
            if self.device_info['available'] and YOLO_CONFIG['half']:
                try:
                    model.half()  # Используем FP16 для ускорения
                    logger.info(f"   🔧 Модель {model_type} переведена в режим FP16")
                except Exception as e:
                    logger.warning(f"   ⚠️ Не удалось включить FP16 для модели {model_type}: {e}")

            # Оптимизация для inference
            model.eval()  # Переводим в режим inference            

        except Exception as e:
            logger.error(f"❌ Ошибка конфигурации модели {model_type}: {e}")
            raise

    def _warmup_models(self):
        """Прогрев моделей для оптимизации производительности"""

        try:
            logger.info("🔥 Прогрев моделей...")

            # Создаем тестовое изображение
            import numpy as np
            dummy_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

            # Прогреваем модель сегментации
            if self.yolo_seg_model:
                with torch.no_grad():
                    _ = self.yolo_seg_model(dummy_image, **YOLO_CONFIG)
                logger.info("   ✅ Модель сегментации прогрета")

            # Прогреваем модель детекции
            if self.yolo_det_model:
                with torch.no_grad():
                    _ = self.yolo_det_model(dummy_image, **YOLO_CONFIG)
                logger.info("   ✅ Модель детекции прогрета")

            # Очищаем кэш GPU
            if self.device_info['available']:
                torch.cuda.empty_cache()
                logger.info("   🧹 GPU кэш очищен") 

        except Exception as e:
            logger.warning(f"⚠️ Ошибка прогрева моделей: {e}")

    def _log_performance_info(self):
        """Логирование информации о производительности"""

        if self.device_info['available']:
            # Информация об использовании GPU памяти
            allocated = torch.cuda.memory_allocated(0) / 1024**2  # MB
            cached = torch.cuda.memory_reserved(0) / 1024**2  # MB
            logger.info("📊 Статистика GPU памяти:")
            logger.info(f"   📦 Выделено: {allocated:.1f} MB")
            logger.info(f"   💾 Зарезервировано: {cached:.1f} MB")
            logger.info(f"   📈 Эффективность: {(allocated/cached)*100:.1f}%" if cached > 0 else "   📈 Эффективность: N/A")

    def get_segmentation_model(self) -> Optional[YOLO]:
        """Получение модели сегментации"""
        return self.yolo_seg_model if self.models_loaded else None

    def get_detection_model(self) -> Optional[YOLO]:
        """Получение модели детекции"""
        return self.yolo_det_model if self.models_loaded else None

    def are_models_loaded(self) -> bool:
        """Проверка загружены ли модели"""
        return self.models_loaded

    def predict_with_stats(self, model: YOLO, image, model_name: str = "unknown"):
        """Inference с отслеживанием производительности"""
        if not model or not self.models_loaded:
            return None

        import time

        start_time = time.time()

        try:
            # Выполняем inference
            with torch.no_grad():
                results = model(image, **YOLO_CONFIG)
            
            # Записываем статистику
            inference_time = time.time() - start_time
            self.performance_stats['inference_times'].append(inference_time)
            self.performance_stats['total_inferences'] += 1

            # Ограничиваем историю
            if len(self.performance_stats['inference_times']) > 100:
                self.performance_stats['inference_times'].pop(0)

            # Логируем каждые 100 inference
            if self.performance_stats['total_inferences'] % 100 == 0:
                avg_time = sum(self.performance_stats['inference_times'][-50:]) / min(50, len(self.performance_stats['inference_times']))
                fps = 1.0 / avg_time if avg_time > 0 else 0
                logger.info(f"📊 {model_name}: {self.performance_stats['total_inferences']} inference, "
                           f"avg time: {avg_time*1000:.1f}ms, FPS: {fps:.1f}")

            return results

        except Exception as e:
            logger.error(f"❌ Ошибка inference {model_name}: {e}")
            return None

    def get_performance_stats(self) -> Dict[str, Any]:
        """Получение статистики производительности"""

        if not self.performance_stats['inference_times']:
            return {
                'total_inferences': 0,
                'average_time_ms': 0,
                'fps': 0,
                'device': self.device_info['device']
            }
    
        recent_times = self.performance_stats['inference_times'][-50:]  # Последние 50
        avg_time = sum(recent_times) / len(recent_times)
        fps = 1.0 / avg_time if avg_time > 0 else 0

        stats = {
            'total_inferences': self.performance_stats['total_inferences'],
            'average_time_ms': round(avg_time * 1000, 1),
            'fps': round(fps, 1),
            'device': self.device_info['device'],
            'device_info': self.device_info
        }

        # Добавляем GPU статистику если доступна
        if self.device_info['available']:
            stats.update({
                'gpu_memory_allocated_mb': round(torch.cuda.memory_allocated(0) / 1024**2, 1),
                'gpu_memory_cached_mb': round(torch.cuda.memory_reserved(0) / 1024**2, 1),
                'gpu_utilization': self._get_gpu_utilization()
            })

        return stats

    def _get_gpu_utilization(self) -> float:
        """Получение утилизации GPU (приблизительно)"""

        try:
            # Простая оценка на основе памяти
            allocated = torch.cuda.memory_allocated(0)
            total = torch.cuda.get_device_properties(0).total_memory
            return round((allocated / total) * 100, 1)
        except:
            return 0.0
    
    def unload_models(self):
        """Выгрузка моделей из памяти"""

        try:
            if self.yolo_seg_model:
                del self.yolo_seg_model
                self.yolo_seg_model = None
                logger.info("🗑️ Модель сегментации выгружена")

            if self.yolo_det_model:
                del self.yolo_det_model
                self.yolo_det_model = None
                logger.info("🗑️ Модель детекции выгружена")

            # Очищаем GPU память
            if self.device_info['available']:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                logger.info("🧹 GPU память очищена")

            self.models_loaded = False
            logger.info("✅ Все модели выгружены из памяти")
            
        except Exception as e:
            logger.error(f"❌ Ошибка выгрузки моделей: {e}")

    def get_model_info(self) -> Dict[str, Any]:
        """Получение подробной информации о моделях"""

        info = {
            'segmentation_model': YOLO_MODELS['segmentation'],
            'detection_model': YOLO_MODELS['detection'],
            'models_loaded': self.models_loaded,
            'segmentation_loaded': self.yolo_seg_model is not None,
            'detection_loaded': self.yolo_det_model is not None,
            'device_info': self.device_info,
            'yolo_config': YOLO_CONFIG,
            'performance_stats': self.get_performance_stats()
        }

        return info

    def optimize_memory(self):
        """Оптимизация использования памяти"""

        try:
            if self.device_info['available']:
                # Очищаем неиспользуемую память
                torch.cuda.empty_cache()

                # Принудительная сборка мусора
                import gc
                gc.collect()

                logger.info("🔧 Память оптимизирована")

        except Exception as e:
            logger.warning(f"⚠️ Ошибка оптимизации памяти: {e}")
