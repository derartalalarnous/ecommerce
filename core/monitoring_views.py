"""
Monitoring API Views - عروض لمراقبة الموارد
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from django.views.decorators.http import require_http_methods

from .resource_manager import get_monitor
from .capacity_controller import get_capacity_controller
from .async_tasks import get_task_queue


@api_view(['GET'])
@permission_classes([IsAdminUser])
@require_http_methods(["GET"])
def resource_status_view(request):
    """
    API endpoint لعرض حالة الموارد
    GET /api/admin/resources/
    """
    monitor = get_monitor()
    
    resource_status = monitor.get_resource_status()
    
    return Response({
        'success': True,
        'message': 'Resource status retrieved successfully',
        'data': resource_status
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
@require_http_methods(["GET"])
def capacity_status_view(request):
    """
    API endpoint لعرض حالة السعة الاستيعابية
    GET /api/admin/capacity/
    """
    controller = get_capacity_controller()
    
    capacity_status = controller.get_status()
    
    return Response({
        'success': True,
        'message': 'Capacity status retrieved successfully',
        'data': capacity_status
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
@require_http_methods(["GET"])
def system_health_view(request):
    """
    API endpoint لعرض صحة النظام الكاملة
    GET /api/admin/health/
    """
    monitor = get_monitor()
    controller = get_capacity_controller()
    
    metrics = monitor.get_metrics()
    is_healthy = monitor.is_healthy(max_cpu=80, max_memory=85)
    
    return Response({
        'success': True,
        'message': 'System health check completed',
        'data': {
            'is_healthy': is_healthy,
            'resource_status': monitor.get_resource_status(),
            'capacity_status': controller.get_status(),
            'recommendations': _get_recommendations(monitor, controller)
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def async_queue_status_view(request):
    """
    API endpoint لعرض حالة طابور المهام غير المتزامنة
    GET /api/admin/async-queue/
    """
    queue = get_task_queue()
    return Response({
        'success': True,
        'data': queue.get_status()
    }, status=status.HTTP_200_OK)


def _get_recommendations(monitor, controller) -> list:
    """الحصول على توصيات تحسين الأداء"""
    recommendations = []
    metrics = monitor.get_metrics()
    status_dict = controller.get_status()
    
    if metrics.cpu_percent > 80:
        recommendations.append({
            'type': 'cpu_high',
            'message': 'CPU usage is high. Consider scaling up or optimizing queries.',
            'severity': 'warning'
        })
    
    if metrics.memory_percent > 80:
        recommendations.append({
            'type': 'memory_high',
            'message': 'Memory usage is high. Check for memory leaks.',
            'severity': 'warning'
        })
    
    if status_dict['rejected_count'] > 100:
        recommendations.append({
            'type': 'rejected_operations',
            'message': f"Many operations rejected ({status_dict['rejected_count']}). "
                        "Consider increasing capacity limits.",
            'severity': 'warning'
        })
    
    if metrics.available_memory_mb < 500:
        recommendations.append({
            'type': 'low_memory',
            'message': 'Available memory is low. This may impact system stability.',
            'severity': 'critical'
        })
    
    if not recommendations:
        recommendations.append({
            'type': 'optimal',
            'message': 'System is running optimally.',
            'severity': 'info'
        })
    
    return recommendations


@api_view(['POST'])
@permission_classes([IsAdminUser])
@require_http_methods(["POST"])
def reset_capacity_stats_view(request):
    """
    API endpoint لإعادة تعيين إحصائيات السعة
    POST /api/admin/capacity/reset/
    """
    controller = get_capacity_controller()
    
    # يمكن إضافة منطق إعادة التعيين هنا
    controller.rejected_count = 0
    controller.queued_count = 0
    controller.operation_counter = 0
    
    return Response({
        'success': True,
        'message': 'Capacity statistics reset successfully',
        'data': controller.get_status()
    }, status=status.HTTP_200_OK)
