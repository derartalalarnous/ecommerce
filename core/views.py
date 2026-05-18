from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from .models import Product , Order , OrderItem
from .serializers import ProductSerializer , OrderSerializer , OrderItemSerializer , CreateOrderSerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import RegisterSerializer
from rest_framework.views import APIView
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import F
from .async_tasks import get_task_queue





@api_view(['POST'])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({"message": "User created successfully"})



class ProductListCreateAPIView(APIView):

    def get(self, request):
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDetailAPIView(APIView):

    def get_object(self, id):
        try:
            return Product.objects.get(id=id)
        except Product.DoesNotExist:
            return None

    def get(self, request, id):
        product = self.get_object(id)
        if not product:
            return Response({"error": "Not found"}, status=404)

        serializer = ProductSerializer(product)
        return Response(serializer.data)

    def put(self, request, id):
        product = self.get_object(id)
        if not product:
            return Response({"error": "Not found"}, status=404)

        serializer = ProductSerializer(product, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, id):
        product = self.get_object(id)
        if not product:
            return Response({"error": "Not found"}, status=404)

        product.delete()
        return Response({"message": "Deleted successfully"}, status=204)
    

class OrderListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']
        
        if quantity <= 0:
            return Response({"error": "Invalid quantity"}, status=400)

        with transaction.atomic():
            updated = Product.objects.filter(
                id=product_id,
                stock__gte=quantity
            ).update(stock=F('stock') - quantity)

        if not updated:
            return Response({"error": "Not enough stock"}, status=400)

        order = Order.objects.create(user=request.user)

        OrderItem.objects.create(
            order=order,
            product_id=product_id,
            quantity=quantity
        )

        queue = get_task_queue()
        queue.enqueue('order_confirmation', order.id)
        queue.enqueue('send_notification', request.user.id,
                       f"Order #{order.id} created successfully")

        return Response({"message": "Order created"}, status=201)    
    

class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)
        serializer = OrderSerializer(order)
        return Response(serializer.data)
    
    def put(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)
        item = order.orderitem_set.first()
        
        with transaction.atomic():
            item = order.orderitem_set.select_for_update().first()
            product = item.product

        new_quantity = request.data.get('quantity')

        if not new_quantity:
            return Response({"error": "Quantity required"}, status=400)

        new_quantity = int(new_quantity)
        product = item.product

        # نحسب الفرق
        diff = new_quantity - item.quantity

        if diff > 0 and product.stock < diff:
            return Response({"error": "Not enough stock"}, status=400)

        # نعدل المخزون
        product.stock -= diff
        product.save()

        # نعدل الطلب
        item.quantity = new_quantity
        item.save()

        return Response({"message": "Order updated"})
    
    def delete(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)
        item = order.orderitem_set.first()
        product = item.product
        
        with transaction.atomic():
            item = order.orderitem_set.select_for_update().first()
            product = item.product  

        # رجع الكمية للمخزون
        product.stock += item.quantity
        product.save()

        order.delete()

        return Response({"message": "Order deleted"}, status=204)    


class PayOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)

        if order.status != 'PENDING':
            return Response({"error": "Order already processed"}, status=400)

        # محاكاة الدفع
        order.status = 'PAID'
        order.save()

        queue = get_task_queue()
        queue.enqueue('generate_invoice', order.id)
        queue.enqueue('payment_receipt', order.id)
        queue.enqueue('send_notification', request.user.id,
                       f"Order #{order.id} paid successfully")

        return Response({"message": "Payment successful"})

class CompleteOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)

        if order.status != 'PAID':
            return Response({"error": "Order not paid"}, status=400)

        order.status = 'COMPLETED'
        order.save()

        queue = get_task_queue()
        queue.enqueue('send_notification', request.user.id,
                       f"Order #{order.id} completed")

        return Response({"message": "Order completed"})

class CancelOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        order = get_object_or_404(Order, id=id, user=request.user)

        if order.status == 'CANCELLED':
            return Response({"error": "Already cancelled"}, status=400)

        item = order.orderitem_set.first()
        product = item.product

        # رجع المخزون
        product.stock += item.quantity
        product.save()

        order.status = 'CANCELLED'
        order.save()

        queue = get_task_queue()
        queue.enqueue('cancellation_notice', order.id)
        queue.enqueue('send_notification', request.user.id,
                       f"Order #{order.id} cancelled")

        return Response({"message": "Order cancelled"})            
    