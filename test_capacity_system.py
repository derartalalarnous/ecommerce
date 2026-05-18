#!/usr/bin/env python
"""
Comprehensive test for the Resource Management & Capacity Control System
"""

import threading
import requests
import time
from concurrent.futures import ThreadPoolExecutor
import statistics

# Test configuration
URL_BASE = "http://127.0.0.1:8000"
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4NTkwMzc3LCJpYXQiOjE3Nzg1ODY3NzcsImp0aSI6IjJkYTEwM2JjODkyNzRjNjdiYjE0NTI0MTExNzQ5YmZlIiwidXNlcl9pZCI6IjMifQ.U2IDKr3YDx_w1dAo_yT_Fas7dk1gVZrIPBeKFP8j_ZE"

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

class CapacityTester:
    def __init__(self):
        self.results = {
            'successful': 0,
            'rejected': 0,
            'timeout': 0,
            'error': 0,
            'response_times': [],
            'status_codes': {}
        }
        self.lock = threading.Lock()

    def get_resource_status(self):
        """Fetch the current resource status."""
        try:
            response = requests.get(
                f"{URL_BASE}/api/admin/resources/",
                headers=HEADERS,
                timeout=10
            )
            data = response.json()
            print("RESOURCE RESPONSE:", data)

            if 'data' in data:
                return data['data']
            
            return None
        
        except Exception as e:
            print(f"Error fetching resource status: {e}")
            return None

    def get_capacity_status(self):
        """Fetch the current capacity status."""
        try:
            response = requests.get(
                f"{URL_BASE}/api/admin/capacity/",
                headers=HEADERS,
                timeout=10
            )
            data = response.json()
            print("RESOURCE RESPONSE:", data)

            if 'data' in data:
                return data['data']
            
            return None
        
        except Exception as e:
            print(f"Error fetching capacity status: {e}")
            return None

    def get_system_health(self):
        """Fetch the full system health status."""
        try:
            response = requests.get(
                f"{URL_BASE}/api/admin/health/",
                headers=HEADERS,
                timeout=10
            )
            return response.json()['data']
        except Exception as e:
            print(f"Error fetching health status: {e}")
            return None

    def make_order_request(self, product_id= 4, quantity=1):
        """Send a sample order request."""
        start_time = time.time()
        try:
            response = requests.post(
                f"{URL_BASE}/api/orders/",
                json={
                    "product_id": product_id,
                    "quantity": quantity
                },
                headers=HEADERS,
                timeout=30,
                proxies={"http": None, "https": None}
            )

            response_time = time.time() - start_time
            status_code = response.status_code
            if status_code == 400:
                print("400 RESPONSE:", response.text)

            with self.lock:
                self.results['response_times'].append(response_time)
                self.results['status_codes'][status_code] = \
                    self.results['status_codes'].get(status_code, 0) + 1

                if 200 <= status_code < 300:
                    self.results['successful'] += 1
                elif status_code in (429, 503):
                    self.results['rejected'] += 1
                else:
                    self.results['error'] += 1

            return status_code

        except requests.Timeout:
            with self.lock:
                self.results['timeout'] += 1
        except Exception as e:
            with self.lock:
                self.results['error'] += 1
            print(f"Error: {e}")

    def run_concurrent_test(self, num_requests=100, max_workers=20):
        """Run a concurrent request test."""
        print(f"\n{'='*60}")
        print(f"🚀 Concurrent test: {num_requests} requests")
        print(f"{'='*60}\n")

        print("📊 Initial status:")
        self._print_status()

        print(f"\n⏱️  Sending {num_requests} requests with {max_workers} concurrent workers...")

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.make_order_request, 4, 1)
                for _ in range(num_requests)
            ]

            for i, future in enumerate(futures):
                try:
                    future.result(timeout=35)
                except Exception:
                    pass

                if (i + 1) % 20 == 0:
                    print(f"  ✓ Processed {i + 1}/{num_requests} requests")

        total_time = time.time() - start_time

        print(f"\n{'='*60}")
        print("📈 Test results:")
        print(f"{'='*60}")
        self._print_results(total_time)

    def stress_test(self, duration=30, num_workers=50):
        """Run a stress test for a specific duration."""
        print(f"\n{'='*60}")
        print(f"💥 Stress test: {duration} seconds with {num_workers} workers")
        print(f"{'='*60}\n")

        print("📊 Initial status:")
        self._print_status()

        print(f"\n⏱️  Sending continuous requests for {duration} seconds...")

        start_time = time.time()
        stop_flag = threading.Event()

        def worker():
            while not stop_flag.is_set():
                self.make_order_request(4, 1)
                time.sleep(0.1)

        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        elapsed = 0
        while elapsed < duration:
            time.sleep(5)
            elapsed = time.time() - start_time
            print(f"  ⏳ {elapsed:.0f}/{duration}s - successful: {self.results['successful']}, rejected: {self.results['rejected']}")

        stop_flag.set()

        total_time = time.time() - start_time

        print(f"\n{'='*60}")
        print("📈 Stress test results:")
        print(f"{'='*60}")
        self._print_results(total_time)

    def _print_status(self):
        """Print the current system status."""
        resources = self.get_resource_status()
        capacity = self.get_capacity_status()

        if resources:
            print(f"  💻 CPU: {resources['current']['cpu_percent']}%")
            print(f"  🧠 Memory: {resources['current']['memory_percent']}%")
            print(f"  🔁 Active Threads: {resources['current']['active_threads']}")

        if capacity:
            print(f"  ⚡ Capacity Level: {capacity['capacity_level'].upper()}")
            print(f"  📊 Active Operations: {capacity['active_operations']}/{capacity['max_concurrent_allowed']}")
            print(f"  📋 Queued: {capacity['queued_count']}")

    def _print_results(self, total_time):
        """Print the aggregated test results."""
        total = self.results['successful'] + self.results['rejected'] + \
                self.results['timeout'] + self.results['error']

        print(f"\n✅ Successful requests: {self.results['successful']}")
        print(f"❌ Rejected requests: {self.results['rejected']}")
        print(f"⏱️  Timeout requests: {self.results['timeout']}")
        print(f"💥 Error requests: {self.results['error']}")
        print(f"📊 Total requests: {total}")

        print(f"\n⏱️  Total elapsed time: {total_time:.2f} seconds")
        if total_time > 0:
            print(f"📈 Request rate: {total/total_time:.2f} req/sec")

        if self.results['response_times']:
            print(f"\n⏳ Response times:")
            print(f"  - Fastest: {min(self.results['response_times']):.3f}s")
            print(f"  - Slowest: {max(self.results['response_times']):.3f}s")
            print(f"  - Average: {statistics.mean(self.results['response_times']):.3f}s")
            if len(self.results['response_times']) > 1:
                print(f"  - Stddev: {statistics.stdev(self.results['response_times']):.3f}s")

        print(f"\n📊 Status code distribution:")
        for code, count in sorted(self.results['status_codes'].items()):
            percentage = (count / total * 100) if total > 0 else 0
            print(f"  {code}: {count} ({percentage:.1f}%)")

        print(f"\n📊 Final status:")
        self._print_status()

        print(f"\n💡 Recommendations:")
        success_rate = (self.results['successful'] / total * 100) if total > 0 else 0

        if success_rate > 95:
            print(f"  ✅ Excellent performance - success rate: {success_rate:.1f}%")
        elif success_rate > 80:
            print(f"  ⚠️ Good performance - success rate: {success_rate:.1f}%")
        else:
            print(f"  ❌ Poor performance - success rate: {success_rate:.1f}%")
            print(f"     Consider increasing capacity or reducing load")


def main():
    tester = CapacityTester()

    print("\n" + "="*60)
    print("🎯 Resource Management & Capacity Control Test")
    print("="*60)
    print("\nChoose a test option:")
    print("  1️⃣  Concurrent test (100 requests)")
    print("  2️⃣  Stress test (30 seconds)")
    print("  3️⃣  Display current status")
    print("  4️⃣  Run all tests")

    choice = input("\nYour choice (1-4): ").strip()

    if choice == "1":
        tester.run_concurrent_test(num_requests=5, max_workers=2)
    elif choice == "2":
        tester.stress_test(duration=30, num_workers=50)
    elif choice == "3":
        print("\n📊 Current system status:")
        tester._print_status()
    elif choice == "4":
        tester.run_concurrent_test(num_requests=50, max_workers=10)
        time.sleep(5)
        tester = CapacityTester()
        tester.stress_test(duration=20, num_workers=30)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
