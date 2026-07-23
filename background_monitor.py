import os
import time
import django
from concurrent.futures import ThreadPoolExecutor

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server_checker.settings')
django.setup()

from django.conf import settings
from monitoring.models import Website, InternalApp
from monitoring.services import MonitoringService

# Check every 5 minutes by default (from .env MONITORING_INTERVAL=300)
CHECK_INTERVAL = getattr(settings, 'MONITORING_INTERVAL', 300)


def check_target(target, is_website=True):
    """Worker function to check a single target in a thread."""
    service = MonitoringService()
    try:
        if is_website:
            service.check_website(target)
        else:
            service.check_internal_app(target)
    except Exception as e:
        print(f"Error checking {target.name}: {e}")


def run_professional_monitoring():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting monitoring cycle...", flush=True)

    websites = list(Website.objects.filter(status='active'))
    internal_apps = list(InternalApp.objects.filter(is_active=True, website__status='active'))

    # Parallel checks — max_workers=10 so SQLite / target hosts are not overwhelmed
    with ThreadPoolExecutor(max_workers=10) as executor:
        for site in websites:
            executor.submit(check_target, site, True)
        for app in internal_apps:
            executor.submit(check_target, app, False)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle completed. Next run in {CHECK_INTERVAL}s.", flush=True)


if __name__ == "__main__":
    print("--- Professional Health Checker Started ---", flush=True)
    print(
        f"Interval: every {CHECK_INTERVAL} seconds ({CHECK_INTERVAL // 60} min). "
        "Email only after 2 consecutive DOWN checks.",
        flush=True,
    )

    while True:
        run_professional_monitoring()
        time.sleep(CHECK_INTERVAL)
