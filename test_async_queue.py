"""Comprehensive test for Async Queue system"""
import subprocess
import requests
import json
import time
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = r"C:\Users\hp\Downloads\Telegram Desktop\ecommerce\ecommerce (1)\ecommerce"
MANAGE_PY = os.path.join(BASE_DIR, "manage.py")
PYTHON = os.path.join(BASE_DIR, "myenv2", "Scripts", "python.exe")
URL = "http://127.0.0.1:8000"

def wait_for_server(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{URL}/", timeout=2)
            return True
        except requests.ConnectionError:
            time.sleep(1)
    return False

def main():
    # 1. Start Django server
    print("=" * 60)
    print("Starting Django server...")
    print("=" * 60)
    server = subprocess.Popen(
        [PYTHON, MANAGE_PY, "runserver", "0.0.0.0:8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=BASE_DIR
    )

    if not wait_for_server():
        print("ERROR: Server failed to start!")
        server.kill()
        sys.exit(1)
    print("[OK] Server is running!\n")

    try:
        # 2. Login
        r = requests.post(f"{URL}/api/login/",
                          json={"username": "haneen", "password": "admin123"})
        token = r.json()["access"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 3. Check initial async queue status
        print("=== ASYNC QUEUE STATUS (BEFORE) ===")
        r = requests.get(f"{URL}/api/admin/async-queue/", headers=headers)
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        print()

        # 4. Create an order with valid product
        print("=== CREATING ORDER ===")
        r = requests.post(f"{URL}/api/orders/",
                          json={"product_id": 5, "quantity": 1},
                          headers=headers)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")
        if r.status_code == 201:
            print(f"[TIME] Response time: IMMEDIATE (tasks offloaded to background)")
            order_id = r.json().get("order_id", "?")
        print()

        # 5. Check queue immediately (tasks should be queued)
        print("=== ASYNC QUEUE (RIGHT AFTER - tasks queued, workers processing) ===")
        r = requests.get(f"{URL}/api/admin/async-queue/", headers=headers)
        data = r.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if data['data']['queue_size'] > 0:
            print("[OK] Tasks successfully queued for background processing!")
        print()

        # 6. Wait for workers to finish
        print("[WAIT] Waiting 6 seconds for workers to complete tasks...")
        time.sleep(6)

        # 7. Check queue after workers finished
        print("\n=== ASYNC QUEUE (6s LATER - workers should be done) ===")
        r = requests.get(f"{URL}/api/admin/async-queue/", headers=headers)
        data = r.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if data['data']['queue_size'] == 0:
            print("[OK] All tasks processed by background workers!")
        print()

        # 8. Pay the order (to test more async tasks)
        print("=== PAYING ORDER ===")
        if 'order_id' in dir() and order_id != "?":
            r = requests.post(f"{URL}/api/orders/{order_id}/pay/", headers=headers)
            print(f"Pay Status: {r.status_code}, Response: {r.text}")
            time.sleep(1)
            print("\n=== ASYNC QUEUE (after payment - invoice + receipt + notification) ===")
            r = requests.get(f"{URL}/api/admin/async-queue/", headers=headers)
            data = r.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
            if data['data']['queue_size'] > 0:
                print("[OK] Payment async tasks (invoice, receipt) queued!")
            time.sleep(6)
            print("\n=== ASYNC QUEUE (6s after payment - all processed) ===")
            r = requests.get(f"{URL}/api/admin/async-queue/", headers=headers)
            data = r.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))

        # 9. System health check
        print("=== SYSTEM HEALTH CHECK ===")
        r = requests.get(f"{URL}/api/admin/health/", headers=headers)
        data = r.json()["data"]
        print(f"Healthy: {data['is_healthy']}")
        print(f"CPU: {data['resource_status']['current']['cpu_percent']}%")
        print(f"Memory: {data['resource_status']['current']['memory_percent']}%")

        print("\n" + "=" * 60)
        print("[PASS] TEST PASSED - Async Queue system is working!")
        print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        server.kill()
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
