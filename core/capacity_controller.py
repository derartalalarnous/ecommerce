"""
Capacity Controller - التحكم في الطاقة الاستيعابية والعمليات المتوازية
"""

import threading
import time
import queue
from typing import Callable, Any, Optional
from enum import Enum
import logging
from functools import wraps

from .resource_manager import get_monitor

logger = logging.getLogger(__name__)


class CapacityLevel(Enum):
    """مستويات الطاقة الاستيعابية"""
    OPTIMAL = "optimal"          # < 50% resources
    NORMAL = "normal"            # 50-70% resources
    HIGH = "high"                # 70-85% resources
    CRITICAL = "critical"        # > 85% resources


class CapacityController:
    """التحكم في الطاقة الاستيعابية والعمليات المتوازية"""
    
    def __init__(self, 
                max_concurrent_operations: int = 50,
                max_queue_size: int = 1000):
        self.max_concurrent = max_concurrent_operations
        self.max_queue_size = max_queue_size
        self.active_operations = 0
        self.pending_queue = queue.Queue(maxsize=max_queue_size)
        self.lock = threading.RLock()
        self.semaphore = threading.Semaphore(max_concurrent_operations)
        self.operation_counter = 0
        self.rejected_count = 0
        self.queued_count = 0
        
    def get_capacity_level(self) -> CapacityLevel:
        """تحديد مستوى الطاقة الحالي"""
        metrics = get_monitor().get_metrics()
        
        if metrics.cpu_percent > 85 or metrics.memory_percent > 85:
            return CapacityLevel.CRITICAL
        elif metrics.cpu_percent > 70 or metrics.memory_percent > 70:
            return CapacityLevel.HIGH
        elif metrics.cpu_percent > 50 or metrics.memory_percent > 50:
            return CapacityLevel.NORMAL
        else:
            return CapacityLevel.OPTIMAL
    
    def get_max_concurrent_allowed(self) -> int:
        """الحصول على الحد الأقصى المسموح للعمليات المتوازية بناءً على الموارد"""
        level = self.get_capacity_level()
        base_max = self.max_concurrent
        
        if level == CapacityLevel.CRITICAL:
            return max(1, int(base_max * 0.3))  # 30% من الحد الأقصى
        elif level == CapacityLevel.HIGH:
            return max(5, int(base_max * 0.6))  # 60% من الحد الأقصى
        elif level == CapacityLevel.NORMAL:
            return max(10, int(base_max * 0.8))  # 80% من الحد الأقصى
        else:  # OPTIMAL
            return base_max
    
    def can_accept_operation(self) -> bool:
        """التحقق من إمكانية قبول عملية جديدة"""
        level = self.get_capacity_level()
        
        # في حالة الطوارئ، رفض العمليات الجديدة
        if level == CapacityLevel.CRITICAL:
            return False
        
        # في حالة الارتفاع العالي، اقبل العمليات المهمة فقط
        allowed_concurrent = self.get_max_concurrent_allowed()
        return self.active_operations < allowed_concurrent
    
    def acquire(self, timeout: Optional[float] = 5.0) -> bool:
        """الحصول على حق تنفيذ عملية
        
        Args:
            timeout: المدة القصوى للانتظار بالثواني
            
        Returns:
            True إذا تم الحصول على الحق، False إذا انقضت المهلة الزمنية
        """
        level = self.get_capacity_level()
        
        # في الحالات الحرجة، لا تنتظر
        if level == CapacityLevel.CRITICAL:
            if not self.semaphore.acquire(blocking=False):
                self.rejected_count += 1
                return False
        else:
            # في الحالات الأخرى، حاول الانتظار
            if not self.semaphore.acquire(timeout=timeout):
                self.rejected_count += 1
                return False
        
        with self.lock:
            self.active_operations += 1
            self.operation_counter += 1
        
        return True
    
    def release(self):
        """تحرير حق تنفيذ العملية"""
        with self.lock:
            self.active_operations = max(0, self.active_operations - 1)
        self.semaphore.release()
    
    def queue_operation(self, operation_id: str, data: dict) -> bool:
        """إضافة عملية إلى قائمة الانتظار"""
        try:
            self.pending_queue.put_nowait({
                'id': operation_id,
                'data': data,
                'timestamp': time.time()
            })
            self.queued_count += 1
            return True
        except queue.Full:
            logger.warning(f"Queue is full. Cannot queue operation {operation_id}")
            return False
    
    def get_pending_operation(self, timeout: float = 1.0) -> Optional[dict]:
        """الحصول على عملية من قائمة الانتظار"""
        try:
            return self.pending_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_status(self) -> dict:
        """الحصول على حالة السعة الاستيعابية"""
        return {
            'capacity_level': self.get_capacity_level().value,
            'active_operations': self.active_operations,
            'max_concurrent_allowed': self.get_max_concurrent_allowed(),
            'total_processed': self.operation_counter,
            'rejected_count': self.rejected_count,
            'queued_count': self.queued_count,
            'pending_queue_size': self.pending_queue.qsize(),
            'queue_max_size': self.max_queue_size,
        }


class CapacityDecorator:
    """ديكوريتور للتحكم في الطاقة الاستيعابية"""
    
    def __init__(self, controller: Optional[CapacityController] = None):
        self.controller = controller or _default_controller
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            operation_id = f"{func.__name__}_{id(args)}"
            
            # محاولة الحصول على حق التنفيذ
            if not self.controller.acquire(timeout=30):
                logger.error(f"Operation {operation_id} rejected due to capacity limits")
                raise CapacityExceededError(
                    "System capacity exceeded. Please try again later."
                )
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                self.controller.release()
        
        return wrapper


class CapacityExceededError(Exception):
    """استثناء عند تجاوز السعة الاستيعابية"""
    pass


# Global instance
_default_controller = CapacityController(
    max_concurrent_operations=50,
    max_queue_size=1000
)

def get_capacity_controller() -> CapacityController:
    """الحصول على مثيل التحكم في السعة العام"""
    return _default_controller
