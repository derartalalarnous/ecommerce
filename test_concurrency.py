import threading
import requests

URL = "http://127.0.0.1:8000/api/orders/"
TOKEN ="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzc4NTkwMzc3LCJpYXQiOjE3Nzg1ODY3NzcsImp0aSI6IjJkYTEwM2JjODkyNzRjNjdiYjE0NTI0MTExNzQ5YmZlIiwidXNlcl9pZCI6IjMifQ.U2IDKr3YDx_w1dAo_yT_Fas7dk1gVZrIPBeKFP8j_ZE"
print("URL is:", URL)
def order():
    try:
        response = requests.post(
            URL,
            json={
                "product_id": 4,
                "quantity": 1
            },
            headers={
                "Authorization": f"Bearer {TOKEN}"
            },
            timeout=30,
            proxies={"http": None, "https": None}
        )
        print(response.status_code, response.text)
    except Exception as e:
        print("Error:", e)

threads = []

for _ in range(3):
    t = threading.Thread(target=order)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

