"""
alarm_manager.py - Управление системой алармов
"""

import cv2
import time
import logging
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from config import (
    PENDING_DIR, CORRECT_DIR, INCORRECT_DIR, STATS_FILE,
    ALARM_COOLDOWN, MAX_PENDING_ALARMS, MAX_EVALUATED_ALARMS
)

logger = logging.getLogger(__name__)

class AlarmManager:
    """Менеджер системы алармов"""

    def __init__(self):
        self.alarms_list: List[Dict] = []  # Неоцененные алармы
        self.evaluated_alarms: Dict[str, List[Dict]] = {
            'correct': [],
            'incorrect': []
        }
        self.camera_last_alarm_times = {}

    def load_alarms_from_folders(self):
        """Загрузка алармов из папок при запуске"""

        try:
            self._load_pending_alarms()
            self._load_evaluated_alarms()
            logger.info(f"Загружено алармов: "
                       f"неоцененных - {len(self.alarms_list)}, "
                       f"верных - {len(self.evaluated_alarms['correct'])}, "
                       f"неверных - {len(self.evaluated_alarms['incorrect'])}")

        except Exception as e:
            logger.error(f"Ошибка загрузки алармов из папок: {e}")
            self.alarms_list = []
            self.evaluated_alarms = {'correct': [], 'incorrect': []}

    def _load_pending_alarms(self):
        """Загрузка неоцененных алармов"""

        self.alarms_list = []
        for img_file in PENDING_DIR.glob("*.jpg"):
            try:
                alarm_data = self._parse_alarm_filename(img_file, evaluated=False)
                if alarm_data:
                    self.alarms_list.append(alarm_data)
            except Exception as e:
                logger.warning(f"Не удалось обработать файл {img_file.name}: {e}")

        # Сортируем по времени (новые первыми)
        self.alarms_list.sort(key=lambda x: x['timestamp'], reverse=True)

    def _load_evaluated_alarms(self):
        """Загрузка оцененных алармов"""
        self.evaluated_alarms = {'correct': [], 'incorrect': []}

        # Загружаем верно определенные
        for img_file in CORRECT_DIR.glob("*.jpg"):
            try:
                alarm_data = self._parse_alarm_filename(img_file, evaluated=True, is_correct=True)
                if alarm_data:
                    self.evaluated_alarms['correct'].append(alarm_data)

            except Exception as e:
                logger.warning(f"Не удалось обработать файл {img_file.name}: {e}")

        # Загружаем неверно определенные
        for img_file in INCORRECT_DIR.glob("*.jpg"):
            try:
                alarm_data = self._parse_alarm_filename(img_file, evaluated=True, is_correct=False)
                if alarm_data:
                    self.evaluated_alarms['incorrect'].append(alarm_data)

            except Exception as e:
                logger.warning(f"Не удалось обработать файл {img_file.name}: {e}")

        # Сортируем оцененные алармы по времени
        self.evaluated_alarms['correct'].sort(key=lambda x: x['timestamp'], reverse=True)
        self.evaluated_alarms['incorrect'].sort(key=lambda x: x['timestamp'], reverse=True)

    def _parse_alarm_filename(self, img_file: Path, evaluated: bool, is_correct: bool = None) -> Optional[Dict]:
        """Парсинг имени файла аларма"""

        filename = img_file.name
        parts = filename.replace('.jpg', '').split('_')

        if len(parts) >= 4 and parts[0] == 'alarm':
            camera_id = parts[1]
            timestamp_str = parts[2] + '_' + parts[3]
            alarm_id = parts[4] if len(parts) > 4 else str(uuid.uuid4())[:8]

            # Преобразуем timestamp
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except:
                timestamp = datetime.fromtimestamp(img_file.stat().st_mtime)
            
            alarm_data = {
                'id': alarm_id,
                'camera_id': camera_id,
                'timestamp': timestamp.isoformat(),
                'filename': filename,
                'filepath': str(img_file),
                'evaluated': evaluated
            }
            
            if evaluated:
                alarm_data['is_correct'] = is_correct

            return alarm_data

        return None
    
    def create_alarm(self, camera_id: str, frame) -> bool:
        """Создание аларма при детекции человека"""

        try:
            current_time = time.time()
            
            # Проверка cooldown
            last_alarm_time = self.camera_last_alarm_times.get(camera_id, 0)
            if current_time - last_alarm_time < ALARM_COOLDOWN:
                return False

            # Обновляем время последнего аларма
            self.camera_last_alarm_times[camera_id] = current_time

            # Создаем уникальное имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alarm_id = str(uuid.uuid4())[:8]
            filename = f"alarm_{camera_id}_{timestamp}_{alarm_id}.jpg"

            # Сохраняем в папку pending
            filepath = PENDING_DIR / filename
            # Сохраняем скриншот с проверкой
            success = cv2.imwrite(str(filepath), frame)
            if not success:
                logger.error(f"Не удалось сохранить изображение: {filepath}")
                return False
            
            # Проверяем, что файл действительно создан
            if not filepath.exists():
                logger.error(f"Файл не был создан: {filepath}")
                return False

            logger.info(f"Файл аларма сохранен: {filepath} (размер: {filepath.stat().st_size} байт)")
            
            # Создаем запись аларма
            alarm_data = {
                'id': alarm_id,
                'camera_id': camera_id,
                'timestamp': datetime.now().isoformat(),
                'filename': filename,
                'filepath': str(filepath),
                'evaluated': False
            }

            # Добавляем в список алармов (в начало для показа последних)
            self.alarms_list.insert(0, alarm_data)

            # Ограничиваем количество неоцененных алармов
            self._cleanup_pending_alarms()

            # Обновляем статистику
            self.save_statistics()

            logger.info(f"Создан аларм для {camera_id}: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания аларма: {e}")
            return False

    def evaluate_alarm(self, alarm_id: str, is_correct: bool) -> bool:
        """Оценка аларма пользователем"""

        try:
            # Находим аларм в списке неоцененных
            alarm_to_evaluate = None
            for i, alarm in enumerate(self.alarms_list):
                if alarm['id'] == alarm_id:
                    alarm_to_evaluate = self.alarms_list.pop(i)
                    break

            if not alarm_to_evaluate:
                logger.error(f"Аларм {alarm_id} не найден")
                return False

            # Перемещаем файл в соответствующую папку
            if not self._move_alarm_to_folder(alarm_to_evaluate, is_correct):
                # Если не удалось переместить файл, возвращаем аларм в список
                self.alarms_list.insert(0, alarm_to_evaluate)
                return False
            
            # Добавляем оценку
            alarm_to_evaluate['is_correct'] = is_correct
            alarm_to_evaluate['evaluated'] = True
            alarm_to_evaluate['evaluation_time'] = datetime.now().isoformat()
            
            # Добавляем в соответствующий список оцененных
            if is_correct:
                self.evaluated_alarms['correct'].insert(0, alarm_to_evaluate)
            else:
                self.evaluated_alarms['incorrect'].insert(0, alarm_to_evaluate)
            
            # Очищаем старые оцененные алармы
            self._cleanup_evaluated_alarms()
            # Сохраняем статистику
            self.save_statistics()
            logger.info(f"Аларм {alarm_id} оценен как {'верный' if is_correct else 'неверный'}")
            return True

        except Exception as e:
            logger.error(f"Ошибка оценки аларма: {e}")
            return False

    def _move_alarm_to_folder(self, alarm_data: Dict, is_correct: bool) -> bool:
        """Перемещение аларма в соответствующую папку"""

        try:
            old_path = Path(alarm_data['filepath'])
            if not old_path.exists():
                logger.error(f"Исходный файл не найден: {old_path}")
                return False

            # Определяем целевую папку
            target_dir = CORRECT_DIR if is_correct else INCORRECT_DIR
            new_path = target_dir / alarm_data['filename']

            # Перемещаем файл
            shutil.move(str(old_path), str(new_path))

            # Обновляем путь в данных аларма
            alarm_data['filepath'] = str(new_path)
            logger.info(f"Аларм перемещен: {old_path} -> {new_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка перемещения аларма: {e}")
            return False

    def _cleanup_pending_alarms(self):
        """Очистка старых неоцененных алармов"""

        if len(self.alarms_list) > MAX_PENDING_ALARMS:
            old_alarm = self.alarms_list.pop()
            try:
                old_path = Path(old_alarm['filepath'])
                if old_path.exists():
                    old_path.unlink()
                    logger.info(f"Удален старый файл аларма: {old_path}")
            except Exception as e:
                logger.error(f"Ошибка удаления старого файла аларма: {e}")
    
    def _cleanup_evaluated_alarms(self):
        """Очистка старых оцененных алармов"""

        try:
            # Очистка верных алармов
            if len(self.evaluated_alarms['correct']) > MAX_EVALUATED_ALARMS:
                alarms_to_remove = self.evaluated_alarms['correct'][MAX_EVALUATED_ALARMS:]
                self.evaluated_alarms['correct'] = self.evaluated_alarms['correct'][:MAX_EVALUATED_ALARMS] 
                for alarm in alarms_to_remove:
                    self._remove_alarm_file(alarm, 'верный')
            
            # Очистка неверных алармов
            if len(self.evaluated_alarms['incorrect']) > MAX_EVALUATED_ALARMS:
                alarms_to_remove = self.evaluated_alarms['incorrect'][MAX_EVALUATED_ALARMS:]
                self.evaluated_alarms['incorrect'] = self.evaluated_alarms['incorrect'][:MAX_EVALUATED_ALARMS]
                for alarm in alarms_to_remove:
                    self._remove_alarm_file(alarm, 'неверный') 

        except Exception as e:
            logger.error(f"Ошибка очистки старых алармов: {e}")

    def _remove_alarm_file(self, alarm: Dict, alarm_type: str):
        """Удаление файла аларма"""
        try:
            file_path = Path(alarm['filepath'])
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Удален старый {alarm_type} аларм: {file_path}")

        except Exception as e:
            logger.error(f"Ошибка удаления старого {alarm_type} аларма: {e}")

    def get_statistics(self) -> Dict:
        """Получение статистики алармов"""

        total_correct = len(self.evaluated_alarms['correct'])
        total_incorrect = len(self.evaluated_alarms['incorrect'])
        total_pending = len(self.alarms_list)
        total_evaluated = total_correct + total_incorrect
        total_alarms = total_evaluated + total_pending
        evaluation_percentage = round((total_evaluated / total_alarms * 100) if total_alarms > 0 else 0, 1)
        accuracy_percentage = round((total_correct / total_evaluated * 100) if total_evaluated > 0 else 0, 1)

        return {
            'total_alarms': total_alarms,
            'pending_alarms': total_pending,
            'correct_alarms': total_correct,
            'incorrect_alarms': total_incorrect,
            'evaluation_percentage': evaluation_percentage,
            'accuracy_percentage': accuracy_percentage
        }

    def save_statistics(self):
        """Сохранение статистики в файл"""

        try:
            stats = self.get_statistics()
            stats['last_updated'] = datetime.now().isoformat()
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            logger.debug("Статистика сохранена")

        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

    def load_statistics(self):
        """Загрузка статистики из файла"""
        try:
            if STATS_FILE.exists():
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Статистика загружена из файла")
            else:
                logger.info("Файл статистики не найден, будет создан новый")
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
    
    def get_pending_alarms(self, limit: int = 10) -> List[Dict]:
        """Получение списка неоцененных алармов"""
        valid_alarms = []
        for alarm in self.alarms_list[:limit]:
            filepath = Path(alarm['filepath'])
            if filepath.exists():
                valid_alarms.append(alarm)
            else:
                logger.warning(f"Файл аларма не найден: {filepath}")

        return valid_alarms

    def find_alarm_file(self, filename: str) -> Optional[Path]:
        """Поиск файла аларма в папках"""
        # Ищем в pending
        filepath = PENDING_DIR / filename
        if filepath.exists():
            return filepath
        
        # Ищем в correct
        filepath = CORRECT_DIR / filename
        if filepath.exists():
            return filepath

        # Ищем в incorrect
        filepath = INCORRECT_DIR / filename
        if filepath.exists():
            return filepath

        return None