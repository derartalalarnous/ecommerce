"""
Middleware - معالجات للتحكم في الطلبات والموارد
"""

import logging
import time
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework.response import Response
from rest_framework import status

from .capacity_controller import (
    get_capacity_controller, 
    CapacityLevel,
    CapacityExceededError
)
from .resource_manager import get_monitor

logger = logging.getLogger(__name__)


class ResourceCapacityMiddleware(MiddlewareMixin):
    """Middleware للتحكم في السعة والموارد الحاسوبية"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.capacity_controller = get_capacity_controller()
        self.resource_monitor = get_monitor()
        super().__init__(get_response)
    
    def process_request(self, request):
        """معالجة الطلب الواردl"""
        request.start_time = time.time()
        
        # تسجيل معلومات الطلب
        request.request_id = f"{request.method}_{request.path}_{time.time()}"
        
        # التحقق من صحة الموارد
        if not self.resource_monitor.is_healthy(max_cpu=90, max_memory=90):
            logger.warning(f"Resources at high level: {self.resource_monitor.get_resource_status()}")
        
        # معالجة الطلبات الحساسة (مثل تحديثات المخزون)
        if self._is_critical_operation(request):
            if not self.capacity_controller.acquire(timeout=30):
                return self._get_capacity_exceeded_response()
            request.acquired_capacity = True
        
        return None
    
    def process_response(self, request, response):
        """معالجة الاستجابة"""
        # تحرير الموارد المخصصة
        if hasattr(request, 'acquired_capacity') and request.acquired_capacity:
            self.capacity_controller.release()
        
        # إضافة رؤوس الاستجابة
        response['X-Processing-Time'] = str(
            round(time.time() - request.start_time, 3)
        )
        
        # إضافة معلومات الموارد (في بيئة التطوير)
        if not getattr(self, '_is_production', False):
            metrics = self.resource_monitor.get_metrics()
            response['X-System-CPU'] = str(round(metrics.cpu_percent, 2))
            response['X-System-Memory'] = str(round(metrics.memory_percent, 2))
            response['X-Active-Operations'] = str(
                self.capacity_controller.active_operations
            )
        
        return response
    
    def process_exception(self, request, exception):
        """معالجة الاستثناءات"""
        if isinstance(exception, CapacityExceededError):
            return self._get_capacity_exceeded_response()
        return None
    
    @staticmethod
    def _is_critical_operation(request) -> bool:
        """تحديد ما إذا كانت العملية حساسة"""
        critical_paths = [
            '/api/orders/',  # إنشاء الأوامر
            '/api/checkout/',
            '/api/payment/',
        ]
        
        for path in critical_paths:
            if request.path.startswith(path) and request.method in ['POST', 'PUT', 'DELETE']:
                return True
        
        return False
    
    @staticmethod
    def _get_capacity_exceeded_response():
        """إرجاع استجابة عند تجاوز السعة"""
        return JsonResponse(
            {
                'error': 'System is at capacity. Please try again later.',
                'status': 'SERVICE_OVERLOADED'
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


class ThrottlingMiddleware(MiddlewareMixin):
    """Middleware للتحكم في معدل الطلبات (Rate Limiting)"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.capacity_controller = get_capacity_controller()
        # قاموس لتخزين عدد الطلبات لكل IP
        self.request_counts = {}
        self.reset_time = {}
        super().__init__(get_response)
    
    def process_request(self, request):
        """تطبيق حد الطلبات"""
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # إعادة تعيين العداد كل دقيقة
        if client_ip not in self.reset_time or \
            current_time - self.reset_time[client_ip] > 60:
            self.request_counts[client_ip] = 0
            self.reset_time[client_ip] = current_time
        
        # زيادة عداد الطلبات
        self.request_counts[client_ip] += 1
        
        # تحديد حد الطلبات بناءً على مستوى السعة
        capacity_level = self.capacity_controller.get_capacity_level()
        rate_limits = {
            CapacityLevel.OPTIMAL: 1000,
            CapacityLevel.NORMAL: 500,
            CapacityLevel.HIGH: 200,
            CapacityLevel.CRITICAL: 50,
        }
        
        max_requests = rate_limits.get(capacity_level, 1000)
        
        if self.request_counts[client_ip] > max_requests:
            logger.warning(
                f"Rate limit exceeded for {client_ip}: "
                f"{self.request_counts[client_ip]}/{max_requests}"
            )
            return JsonResponse(
                {
                    'error': 'Rate limit exceeded',
                    'retry_after': self._get_retry_after(client_ip, current_time)
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        return None
    
    @staticmethod
    def _get_client_ip(request) -> str:
        """استخراج عنوان IP من الطلب"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _get_retry_after(self, client_ip: str, current_time: float) -> int:
        """الحصول على وقت إعادة المحاولة"""
        reset_time = self.reset_time.get(client_ip, current_time)
        retry_after = max(1, int(60 - (current_time - reset_time)))
        return retry_after


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware لتسجيل الطلبات والأداء"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        request.start_time = time.time()
        return None
    
    def process_response(self, request, response):
        duration = time.time() - request.start_time
        
        # تسجيل الطلبات البطيئة (> 1 ثانية)
        if duration > 1.0:
            logger.warning(
                f"Slow request: {request.method} {request.path} "
                f"took {duration:.2f}s, status={response.status_code}"
            )
        
        # تسجيل معلومات الطلب
        logger.debug(
            f"Request: {request.method} {request.path} - "
            f"Status: {response.status_code}, Duration: {duration:.3f}s"
        )
        
        return response
