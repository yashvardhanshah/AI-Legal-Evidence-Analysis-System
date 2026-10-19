"""Real HTTP integration check; start the frontend, backend and migrated DB first."""
import json
import re
from urllib.request import urlopen


def get(url):
    with urlopen(url, timeout=15) as response:
        assert response.status == 200
        return response.read().decode()


assert json.loads(get("http://127.0.0.1:8000/api/v1/health/live"))["status"] == "ok"
assert json.loads(get("http://127.0.0.1:8000/api/v1/health/ready"))["database"] == "connected"
assert json.loads(get("http://127.0.0.1:3000/api/system"))["database"] == "connected"
html = get("http://127.0.0.1:3000")
assert "No case data is available yet" in html
assets = set(re.findall(r'(?:src|href)="([^" ]+\.(?:css|js)(?:\?[^" ]*)?)"', html))
assert assets, "Expected built CSS and JavaScript"
for asset in assets:
    if asset.startswith("/"):
        get("http://127.0.0.1:3000" + asset.replace("&amp;", "&"))
print(f"PASS: liveness, PostgreSQL readiness, frontend proxy, dashboard HTML and {len(assets)} built assets")
