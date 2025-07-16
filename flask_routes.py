"""
flask_routes.py - Flask маршруты приложения с поддержкой площади сегментации
"""

import logging
from flask import render_template, request, Response, jsonify, send_file
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FlaskRoutes:
    """Класс для организации Flask маршрутов"""
    
    def __init__(self, app, camera_manager, alarm_manager, video_generator):
        self.app = app
        self.camera_manager = camera_manager
        self.alarm_manager = alarm_manager
        self.video_generator = video_generator
        
        self._register_routes()

    def _register_routes(self):
        """Регистрация всех маршрутов"""
        # Страницы
        self.app.route('/')(self.index)
        self.app.route('/events')(self.events)
        
        # API камер
        self.app.route('/connect_camera', methods=['POST'])(self.connect_camera)
        self.app.route('/disconnect_camera', methods=['POST'])(self.disconnect_camera)
        self.app.route('/camera_status')(self.camera_status)
        
        # API алармов
        self.app.route('/get_alarms')(self.get_alarms)
        self.app.route('/evaluate_alarm', methods=['POST'])(self.evaluate_alarm)
        self.app.route('/alarm_image/<filename>')(self.alarm_image)
        
        # API статистики
        self.app.route('/get_statistics')(self.get_statistics)
        
        # API площади сегментации
        self.app.route('/get_segmentation_stats')(self.get_segmentation_stats)
        
        # Видеопотоки
        self.app.route('/video_feed/<camera_id>')(self.video_feed)
        self.app.route('/video_feed_original/<camera_id>')(self.video_feed_original)

    def index(self):
        """Главная страница"""
        return render_template('index.html')

    def events(self):
        """Страница журнала событий"""
        return render_template('events.html')

    def connect_camera(self):
        """Подключение к камере"""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            rtsp_url = data.get('rtsp_url', '').strip()
            
            if not rtsp_url:
                return jsonify({'status': 'error', 'message': 'RTSP URL не может быть пустым'})
            
            if camera_id not in ['camera1', 'camera2']:
                return jsonify({'status': 'error', 'message': 'Неверный ID камеры'})
            
            # Отключаем камеру если уже подключена
            if self.camera_manager.is_camera_connected(camera_id):
                self.camera_manager.disconnect_camera(camera_id)
            
            # Подключаем камеру
            success = self.camera_manager.connect_camera(camera_id, rtsp_url)
            
            if success:
                return jsonify({'status': 'success', 'message': f'Камера {camera_id} подключена'})
            else:
                return jsonify({'status': 'error', 'message': f'Не удалось подключить камеру {camera_id}'})
                
        except Exception as e:
            logger.error(f"Ошибка подключения камеры: {e}")
            return jsonify({'status': 'error', 'message': str(e)})

    def disconnect_camera(self):
        """Отключение камеры"""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            
            if camera_id not in ['camera1', 'camera2']:
                return jsonify({'status': 'error', 'message': 'Неверный ID камеры'})
            
            success = self.camera_manager.disconnect_camera(camera_id)
            
            if success:
                return jsonify({'status': 'success', 'message': f'Камера {camera_id} отключена'})
            else:
                return jsonify({'status': 'error', 'message': f'Ошибка отключения камеры {camera_id}'})
                
        except Exception as e:
            logger.error(f"Ошибка отключения камеры: {e}")
            return jsonify({'status': 'error', 'message': str(e)})

    def camera_status(self):
        """Получение статуса камер с информацией о производительности"""
        try:
            camera_status_data = self.camera_manager.get_cameras_status()
            alarm_stats = self.alarm_manager.get_statistics()
            
            # Добавляем информацию о производительности моделей
            model_info = self.camera_manager.model_manager.get_model_info()
            performance_stats = self.camera_manager.model_manager.get_performance_stats()
            
            # Добавляем статистику площади сегментации
            segmentation_stats = {}
            if hasattr(self.camera_manager, 'segmentation_area_manager'):
                segmentation_stats = self.camera_manager.segmentation_area_manager.get_stats()
            
            return jsonify({
                **camera_status_data,
                **alarm_stats,
                'model_info': model_info,
                'performance': performance_stats,
                'segmentation': segmentation_stats
            })
            
        except Exception as e:
            logger.error(f"Ошибка получения статуса камер: {e}")
            return jsonify({'error': str(e)}), 500

    def get_alarms(self):
        """Получение списка неоцененных алармов"""
        try:
            alarms = self.alarm_manager.get_pending_alarms(limit=10)
            total_pending = len(self.alarm_manager.alarms_list)
            
            return jsonify({
                'alarms': alarms,
                'total_pending': total_pending
            })
            
        except Exception as e:
            logger.error(f"Ошибка получения алармов: {e}")
            return jsonify({
                'alarms': [],
                'total_pending': 0
            })

    def evaluate_alarm(self):
        """Оценка аларма"""
        try:
            data = request.json
            alarm_id = data.get('alarm_id')
            is_correct = data.get('is_correct')
            
            if not alarm_id:
                return jsonify({'status': 'error', 'message': 'ID аларма не указан'})
            
            if is_correct is None:
                return jsonify({'status': 'error', 'message': 'Оценка не указана'})
            
            success = self.alarm_manager.evaluate_alarm(alarm_id, is_correct)
            
            if success:
                return jsonify({'status': 'success', 'message': 'Аларм оценен'})
            else:
                return jsonify({'status': 'error', 'message': 'Ошибка оценки аларма'})
                
        except Exception as e:
            logger.error(f"Ошибка оценки аларма: {e}")
            return jsonify({'status': 'error', 'message': str(e)})

    def alarm_image(self, filename: str):
        """Получение изображения аларма"""
        try:
            filepath = self.alarm_manager.find_alarm_file(filename)
            
            if filepath:
                return send_file(filepath, mimetype='image/jpeg')
            else:
                logger.error(f"Файл аларма не найден: {filename}")
                return "Файл не найден", 404
                
        except Exception as e:
            logger.error(f"Ошибка получения изображения: {e}")
            return "Ошибка сервера", 500

    def get_statistics(self):
        """Получение подробной статистики"""
        try:
            stats = self.alarm_manager.get_statistics()
            
            # Добавляем информацию о папках
            stats['folders'] = {
                'pending': str(self.alarm_manager.pending_dir) if hasattr(self.alarm_manager, 'pending_dir') else '',
                'correct': str(self.alarm_manager.correct_dir) if hasattr(self.alarm_manager, 'correct_dir') else '',
                'incorrect': str(self.alarm_manager.incorrect_dir) if hasattr(self.alarm_manager, 'incorrect_dir') else ''
            }
            
            return jsonify(stats)
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return jsonify({'error': str(e)}), 500

    def get_segmentation_stats(self):
        """Получение статистики площади сегментации"""
        try:
            if hasattr(self.camera_manager, 'segmentation_area_manager'):
                stats = self.camera_manager.segmentation_area_manager.get_stats()
                
                # Добавляем информацию о производительности камер
                camera_stats = {}
                for camera_id in ['camera1', 'camera2']:
                    if camera_id in self.camera_manager.processors:
                        processor = self.camera_manager.processors[camera_id]
                        camera_stats[camera_id] = processor.get_performance_stats()
                
                stats['camera_performance'] = camera_stats
                
                return jsonify(stats)
            else:
                return jsonify({
                    'current_product': 0,
                    'camera1_area': 0,
                    'camera2_area': 0,
                    'max_product': 0,
                    'average_product': 0,
                    'total_calculations': 0,
                    'non_zero_products': 0,
                    'camera_performance': {}
                })
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики сегментации: {e}")
            return jsonify({'error': str(e)}), 500

    def video_feed(self, camera_id: str):
        """Обработанный видео поток"""
        try:
            if camera_id not in ['camera1', 'camera2']:
                return "Неверный ID камеры", 400
            
            return Response(
                self.video_generator.generate_frames(camera_id, processed=True),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
            
        except Exception as e:
            logger.error(f"Ошибка видеопотока {camera_id}: {e}")
            return "Ошибка видеопотока", 500

    def video_feed_original(self, camera_id: str):
        """Оригинальный видео поток"""
        try:
            if camera_id not in ['camera1', 'camera2']:
                return "Неверный ID камеры", 400
            
            return Response(
                self.video_generator.generate_frames(camera_id, processed=False),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
            
        except Exception as e:
            logger.error(f"Ошибка видеопотока {camera_id}: {e}")
            return "Ошибка видеопотока", 500


class CameraManager:
    """Менеджер камер для интеграции с Flask маршрутами"""
    
    def __init__(self, camera_streams: dict, processors: dict, model_manager, segmentation_area_manager=None):
        self.camera_streams = camera_streams
        self.processors = processors
        self.model_manager = model_manager
        self.segmentation_area_manager = segmentation_area_manager

    def is_camera_connected(self, camera_id: str) -> bool:
        """Проверка подключения камеры"""
        return self.camera_streams[camera_id]['connected']

    def connect_camera(self, camera_id: str, rtsp_url: str) -> bool:
        """Подключение камеры"""
        try:
            processor = self.processors[camera_id]
            
            # Подключаем камеру
            if processor.connect_camera(rtsp_url):
                # Запускаем обработку
                if processor.start_processing():
                    return True
                else:
                    processor.disconnect_camera()
                    return False
            else:
                return False
                
        except Exception as e:
            logger.error(f"Ошибка подключения камеры {camera_id}: {e}")
            return False

    def disconnect_camera(self, camera_id: str) -> bool:
        """Отключение камеры"""
        try:
            processor = self.processors[camera_id]
            processor.disconnect_camera()
            
            # Сбрасываем площадь сегментации при отключении
            if self.segmentation_area_manager:
                self.segmentation_area_manager.update_camera_area(camera_id, 0)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отключения камеры {camera_id}: {e}")
            return False

    def get_cameras_status(self) -> dict:
        """Получение статуса всех камер"""
        status = {
            'camera1': {
                'connected': self.camera_streams['camera1']['connected'],
                'processing': self.camera_streams['camera1']['processing'],
                'segmentation_area': self.camera_streams['camera1'].get('segmentation_area', 0)
            },
            'camera2': {
                'connected': self.camera_streams['camera2']['connected'],
                'processing': self.camera_streams['camera2']['processing'],
                'segmentation_area': self.camera_streams['camera2'].get('segmentation_area', 0)
            },
            'models_loaded': self.model_manager.are_models_loaded()
        }
        
        # Добавляем произведение площадей
        if self.segmentation_area_manager:
            status['area_product'] = self.segmentation_area_manager.get_current_product()
        else:
            status['area_product'] = 0
            
        return status