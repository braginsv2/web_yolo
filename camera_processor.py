"""
camera_processor.py - Обработка видеопотоков камер с подсчетом площади сегментации
"""

import cv2
import numpy as np
import threading
import time
import logging
import queue
from typing import Optional, Callable

from config import CAMERA_CONFIG, PROCESSING_CONFIG, OBJECT_CLASSES

logger = logging.getLogger(__name__)

class CameraProcessor:
    """Процессор для обработки видеопотока камеры с поддержкой CUDA и подсчетом площади сегментации"""
    
    def __init__(self, camera_id: str, camera_streams: dict, yolo_model, alarm_callback: Callable, model_manager=None, segmentation_callback=None):
        self.camera_id = camera_id
        self.camera_streams = camera_streams
        self.yolo_model = yolo_model
        self.alarm_callback = alarm_callback
        self.model_manager = model_manager
        self.segmentation_callback = segmentation_callback  # Новый callback для площади сегментации
        
        self.running = False
        self.capture_thread: Optional[threading.Thread] = None
        self.process_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.process_queue = queue.Queue(maxsize=PROCESSING_CONFIG['queue_maxsize'])
        
        # Статистика производительности
        self.frame_stats = {
            'processed_frames': 0,
            'dropped_frames': 0,
            'last_fps_update': time.time(),
            'fps': 0.0
        }
        
        # Статистика сегментации
        self.segmentation_stats = {
            'last_segmentation_area': 0,
            'total_segmentation_pixels': 0,
            'frames_with_segmentation': 0,
            'average_segmentation_area': 0.0
        }

    def connect_camera(self, rtsp_url: str) -> bool:
        """Подключение к RTSP камере"""
        try:
            logger.info(f"Подключение к RTSP камере: {rtsp_url}")
            
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            
            # Настройка параметров для RTSP
            self._configure_camera(cap)
            
            if cap.isOpened():
                success = self._test_camera_connection(cap)
                if success:
                    with self.lock:
                        self.camera_streams[self.camera_id]['cap'] = cap
                        self.camera_streams[self.camera_id]['connected'] = True
                        self.camera_streams[self.camera_id]['config'] = {'rtsp_url': rtsp_url}
                        self.camera_streams[self.camera_id]['frame_counter'] = 0
                    
                    logger.info(f"Камера {self.camera_id} подключена успешно")
                    return True
                else:
                    cap.release()
                    return False
            else:
                logger.error(f"Не удалось открыть камеру {self.camera_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка подключения к камере {self.camera_id}: {e}")
            return False

    def _configure_camera(self, cap):
        """Конфигурация параметров камеры"""
        cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_CONFIG['buffer_size'])
        cap.set(cv2.CAP_PROP_FPS, CAMERA_CONFIG['fps'])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_CONFIG['width'])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_CONFIG['height'])
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('H', '2', '6', '4'))
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, CAMERA_CONFIG['open_timeout'])
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, CAMERA_CONFIG['read_timeout'])

    def _test_camera_connection(self, cap) -> bool:
        """Тестирование подключения к камере"""
        for attempt in range(CAMERA_CONFIG['max_attempts']):
            ret, frame = cap.read()
            if ret and frame is not None:
                logger.info(f"Кадр получен успешно на попытке {attempt + 1}")
                return True
            else:
                time.sleep(1)
        
        logger.error(f"Не удалось получить кадр после {CAMERA_CONFIG['max_attempts']} попыток")
        return False

    def disconnect_camera(self):
        """Отключение камеры"""
        self.running = False
        
        # Ждем завершения потоков
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=3)
        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=3)
            
        with self.lock:
            if self.camera_streams[self.camera_id]['cap']:
                self.camera_streams[self.camera_id]['cap'].release()
                
            # Сброс состояния камеры
            self.camera_streams[self.camera_id].update({
                'cap': None,
                'connected': False,
                'frame': None,
                'processed_frame': None,
                'processing': False,
                'frame_counter': 0,
                'segmentation_area': 0  # Сброс площади сегментации
            })
            
            if self.camera_streams[self.camera_id]['frame_queue']:
                self.camera_streams[self.camera_id]['frame_queue'].clear()
            
        logger.info(f"Камера {self.camera_id} отключена")

    def start_processing(self) -> bool:
        """Запуск обработки потока"""
        if not self.camera_streams[self.camera_id]['connected']:
            return False
            
        self.running = True
        self.camera_streams[self.camera_id]['processing'] = True
        
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        
        self.capture_thread.start()
        self.process_thread.start()
        
        logger.info(f"Обработка камеры {self.camera_id} запущена")
        return True

    def _capture_loop(self):
        """Поток для захвата кадров"""
        logger.info(f"Запущен поток захвата для камеры {self.camera_id}")
        
        while self.running:
            try:
                with self.lock:
                    cap = self.camera_streams[self.camera_id]['cap']
                    if not cap or not cap.isOpened():
                        break
                
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # Изменяем размер кадра
                frame = cv2.resize(frame, (CAMERA_CONFIG['width'], CAMERA_CONFIG['height']))
                
                with self.lock:
                    # Добавляем в очередь кадров
                    if self.camera_streams[self.camera_id]['frame_queue']:
                        self.camera_streams[self.camera_id]['frame_queue'].append(frame.copy())
                    
                    self.camera_streams[self.camera_id]['frame'] = frame.copy()
                    self.camera_streams[self.camera_id]['frame_counter'] += 1
                
                # Добавляем кадр для обработки (каждый N-й кадр)
                if self.camera_streams[self.camera_id]['frame_counter'] % PROCESSING_CONFIG['frame_skip'] == 0:
                    try:
                        self.process_queue.put_nowait(frame.copy())
                    except queue.Full:
                        # Считаем пропущенные кадры
                        self.frame_stats['dropped_frames'] += 1
                
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Ошибка в потоке захвата {self.camera_id}: {e}")
                break
        
        logger.info(f"Поток захвата для камеры {self.camera_id} завершен")

    def _process_loop(self):
        """Поток для обработки кадров с отслеживанием производительности"""
        logger.info(f"Запущен поток обработки для камеры {self.camera_id}")
        
        while self.running:
            try:
                try:
                    frame = self.process_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Отслеживание FPS
                current_time = time.time()
                self.frame_stats['processed_frames'] += 1
                
                # Обновляем FPS каждые 30 кадров
                if self.frame_stats['processed_frames'] % 30 == 0:
                    time_diff = current_time - self.frame_stats['last_fps_update']
                    if time_diff > 0:
                        self.frame_stats['fps'] = 30 / time_diff
                        self.frame_stats['last_fps_update'] = current_time
                
                # Выбираем метод обработки в зависимости от камеры
                if self.camera_id == 'camera1':
                    processed_frame = self._process_frame_segmentation(frame)
                else:
                    processed_frame = self._process_frame_detection(frame)
                
                with self.lock:
                    self.camera_streams[self.camera_id]['processed_frame'] = processed_frame
                
                self.process_queue.task_done()
                
                # Логируем статистику каждые 1000 кадров
                if self.frame_stats['processed_frames'] % 1000 == 0:
                    logger.info(f"📊 {self.camera_id}: {self.frame_stats['processed_frames']} кадров, "
                              f"FPS: {self.frame_stats['fps']:.1f}, "
                              f"пропущено: {self.frame_stats['dropped_frames']}, "
                              f"сегментация: {self.segmentation_stats['last_segmentation_area']} пикс.")
                
            except Exception as e:
                logger.error(f"Ошибка в потоке обработки {self.camera_id}: {e}")
                break
        
        self.camera_streams[self.camera_id]['processing'] = False
        logger.info(f"Поток обработки для камеры {self.camera_id} завершен")

    def get_performance_stats(self) -> dict:
        """Получение статистики производительности камеры"""
        return {
            'camera_id': self.camera_id,
            'processed_frames': self.frame_stats['processed_frames'],
            'dropped_frames': self.frame_stats['dropped_frames'],
            'fps': round(self.frame_stats['fps'], 1),
            'queue_size': self.process_queue.qsize(),
            'is_running': self.running,
            'segmentation_area': self.segmentation_stats['last_segmentation_area'],
            'avg_segmentation_area': round(self.segmentation_stats['average_segmentation_area'], 1),
            'frames_with_segmentation': self.segmentation_stats['frames_with_segmentation']
        }

    def _calculate_segmentation_area(self, masks, boxes) -> int:
        """Подсчет площади сегментации людей в пикселях"""
        total_area = 0
        
        if masks is not None and boxes is not None:
            masks_data = masks.data.cpu().numpy()
            
            for i, (mask, box) in enumerate(zip(masks_data, boxes)):
                cls = int(box.cls[0].cpu().numpy())
                if cls == OBJECT_CLASSES['person']:
                    # Изменяем размер маски под размер кадра
                    mask_resized = cv2.resize(mask, (CAMERA_CONFIG['width'], CAMERA_CONFIG['height']))
                    
                    # Подсчитываем пиксели маски (где значение > 0.5)
                    person_pixels = np.sum(mask_resized > 0.5)
                    total_area += person_pixels
        
        return int(total_area)

    def _process_frame_segmentation(self, frame):
        """Обработка кадра для сегментации (камера 1)"""
        if not self.yolo_model:
            # Если модель не загружена, просто обнуляем площадь сегментации
            self._update_segmentation_stats(0)
            return frame
            
        try:
            # Используем model_manager для inference с отслеживанием производительности
            if hasattr(self, 'model_manager') and self.model_manager:
                results = self.model_manager.predict_with_stats(
                    self.yolo_model, frame, "Сегментация"
                )
            else:
                # Fallback на обычный inference
                results = self.yolo_model(frame, verbose=False)
            
            if not results:
                # Обнуляем площадь сегментации если нет результатов
                self._update_segmentation_stats(0)
                return frame
            
            # Подсчитываем площадь сегментации
            segmentation_area = 0
            if results[0].masks is not None and results[0].boxes is not None:
                segmentation_area = self._calculate_segmentation_area(results[0].masks, results[0].boxes)
            
            # Обновляем статистику сегментации
            self._update_segmentation_stats(segmentation_area)
            
            # Проверяем наличие людей
            person_detected = self._check_person_detection(results)
            
            # Создаем аларм если обнаружен человек
            if person_detected:
                self.alarm_callback(self.camera_id, frame)
            
            # Возвращаем обработанный кадр только с масками людей
            return self._draw_segmentation_masks(frame, results)
            
        except Exception as e:
            logger.error(f"Ошибка обработки кадра сегментации {self.camera_id}: {e}")
            self._update_segmentation_stats(0)
            return frame

    def _process_frame_detection(self, frame):
        """Обработка кадра для детекции (камера 2)"""
        if not self.yolo_model:
            # Если модель не загружена, просто обнуляем площадь сегментации
            self._update_segmentation_stats(0)
            return frame
            
        try:
            # Используем model_manager для inference с отслеживанием производительности
            if hasattr(self, 'model_manager') and self.model_manager:
                results = self.model_manager.predict_with_stats(
                    self.yolo_model, frame, "Детекция"
                )
            else:
                # Fallback на обычный inference
                results = self.yolo_model(frame, verbose=False)
            
            if not results:
                # Обнуляем площадь сегментации если нет результатов
                self._update_segmentation_stats(0)
                return frame
            
            # Подсчитываем площадь сегментации (если есть маски)
            segmentation_area = 0
            if results[0].masks is not None and results[0].boxes is not None:
                segmentation_area = self._calculate_segmentation_area(results[0].masks, results[0].boxes)
            
            # Обновляем статистику сегментации
            self._update_segmentation_stats(segmentation_area)
            
            # Проверяем наличие людей
            person_detected = self._check_person_detection(results)
            
            # Создаем аларм если обнаружен человек
            if person_detected:
                self.alarm_callback(self.camera_id, frame)
            
            # Возвращаем результат с масками и боксами для людей
            annotated_frame = self._draw_segmentation_masks(frame, results)
            return self._draw_detection_boxes(annotated_frame, results)
            
        except Exception as e:
            logger.error(f"Ошибка обработки кадра детекции {self.camera_id}: {e}")
            self._update_segmentation_stats(0)
            return frame

    def _update_segmentation_stats(self, area: int):
        """Обновление статистики сегментации"""
        self.segmentation_stats['last_segmentation_area'] = area
        
        # Обновляем статистику в camera_streams для доступа извне
        with self.lock:
            self.camera_streams[self.camera_id]['segmentation_area'] = area
        
        if area > 0:
            self.segmentation_stats['frames_with_segmentation'] += 1
            self.segmentation_stats['total_segmentation_pixels'] += area
            
            # Подсчет средней площади сегментации
            self.segmentation_stats['average_segmentation_area'] = (
                self.segmentation_stats['total_segmentation_pixels'] / 
                self.segmentation_stats['frames_with_segmentation']
            )
        
        # Вызываем callback для обновления произведения площадей
        if self.segmentation_callback:
            try:
                self.segmentation_callback(self.camera_id, area)
            except Exception as e:
                logger.error(f"Ошибка в segmentation_callback: {e}")

    def _check_person_detection(self, results) -> bool:
        """Проверка наличия людей в результатах детекции"""
        try:
            if results and len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls = int(box.cls[0].cpu().numpy())
                    if cls == OBJECT_CLASSES['person']:
                        return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки детекции людей: {e}")
            return False

    def _draw_segmentation_masks(self, frame, results):
        """Рисование масок сегментации для людей"""
        try:
            annotated_frame = frame.copy()
            
            if (results and len(results) > 0 and 
                results[0].masks is not None and results[0].boxes is not None):
                
                masks = results[0].masks.data.cpu().numpy()
                boxes = results[0].boxes
                
                for i, (mask, box) in enumerate(zip(masks, boxes)):
                    cls = int(box.cls[0].cpu().numpy())
                    if cls == OBJECT_CLASSES['person']:
                        # Изменяем размер маски под размер кадра
                        mask_resized = cv2.resize(mask, (frame.shape[1], frame.shape[0]))
                        
                        # Создаем цветную маску для человека
                        color = np.random.randint(50, 255, 3)
                        colored_mask = np.zeros_like(frame)
                        colored_mask[mask_resized > 0.5] = color
                        
                        # Накладываем маску с прозрачностью
                        alpha = 0.7 if self.camera_id == 'camera1' else 0.8
                        beta = 0.3 if self.camera_id == 'camera1' else 0.2
                        annotated_frame = cv2.addWeighted(annotated_frame, alpha, colored_mask, beta, 0)
            
            return annotated_frame
        except Exception as e:
            logger.error(f"Ошибка рисования масок сегментации: {e}")
            return frame

    def _draw_detection_boxes(self, frame, results):
        """Рисование боксов детекции для людей"""
        try:
            if results and len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes
                for box in boxes:
                    cls = int(box.cls[0].cpu().numpy())
                    if cls == OBJECT_CLASSES['person']:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = box.conf[0].cpu().numpy()
                        
                        # Рисуем бокс для человека
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                        
                        # Добавляем label с confidence
                        label = f"Person: {conf:.2f}"
                        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        
                        # Фон для текста
                        cv2.rectangle(frame, (x1, y1-30), (x1 + label_size[0], y1), (0, 255, 0), -1)
                        cv2.putText(frame, label, (x1, y1-10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            
            return frame
        except Exception as e:
            logger.error(f"Ошибка рисования боксов детекции: {e}")
            return frame


class VideoStreamGenerator:
    """Генератор видеопотока для Flask"""
    
    def __init__(self, camera_streams: dict):
        self.camera_streams = camera_streams

    def generate_frames(self, camera_id: str, processed: bool = True):
        """Генератор кадров для стрима"""
        while True:
            try:
                if processed:
                    frame = self.camera_streams[camera_id]['processed_frame']
                else:
                    frame = self.camera_streams[camera_id]['frame']
                    
                if frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame, [
                        cv2.IMWRITE_JPEG_QUALITY, PROCESSING_CONFIG['jpeg_quality'],
                        cv2.IMWRITE_JPEG_OPTIMIZE, 1
                    ])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                else:
                    time.sleep(0.05)
                    
            except Exception as e:
                logger.error(f"Ошибка генерации кадров для {camera_id}: {e}")
                time.sleep(0.1)


class SegmentationAreaManager:
    """Менеджер для подсчета произведения площадей сегментации двух камер"""
    
    def __init__(self):
        self.camera_areas = {
            'camera1': 0,
            'camera2': 0
        }
        self.area_product = 0
        self.lock = threading.Lock()
        
        # Статистика
        self.stats = {
            'max_product': 0,
            'total_calculations': 0,
            'average_product': 0.0,
            'non_zero_products': 0
        }
    
    def update_camera_area(self, camera_id: str, area: int):
        """Обновление площади сегментации для камеры"""
        with self.lock:
            self.camera_areas[camera_id] = area
            self._calculate_product()
    
    def _calculate_product(self):
        """Подсчет произведения площадей"""
        new_product = self.camera_areas['camera1'] * self.camera_areas['camera2']
        self.area_product = new_product
        
        # Обновляем статистику
        self.stats['total_calculations'] += 1
        
        if new_product > self.stats['max_product']:
            self.stats['max_product'] = new_product
        
        if new_product > 0:
            self.stats['non_zero_products'] += 1
            
        # Средний продукт (только для ненулевых значений)
        if self.stats['non_zero_products'] > 0:
            total_sum = self.stats['average_product'] * (self.stats['non_zero_products'] - 1) + new_product
            self.stats['average_product'] = total_sum / self.stats['non_zero_products']
    
    def get_current_product(self) -> int:
        """Получение текущего произведения площадей"""
        with self.lock:
            return self.area_product
    
    def get_camera_areas(self) -> dict:
        """Получение площадей по камерам"""
        with self.lock:
            return self.camera_areas.copy()
    
    def get_stats(self) -> dict:
        """Получение статистики"""
        with self.lock:
            return {
                'current_product': self.area_product,
                'camera1_area': self.camera_areas['camera1'],
                'camera2_area': self.camera_areas['camera2'],
                'max_product': self.stats['max_product'],
                'average_product': round(self.stats['average_product'], 1),
                'total_calculations': self.stats['total_calculations'],
                'non_zero_products': self.stats['non_zero_products']
            }