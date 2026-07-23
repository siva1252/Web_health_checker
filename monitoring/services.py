import requests
import time
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from .models import Website, InternalApp, MonitoringCheck, AlertLog, MonitoringSettings
import logging

logger = logging.getLogger(__name__)


class MonitoringService:
    def __init__(self):
        self.settings = MonitoringSettings.get_settings()
    
    def check_website(self, website):
        try:
            start_time = time.time()
            response = requests.get(website.url, timeout=website.timeout, allow_redirects=True)
            end_time = time.time()
            response_time = round(end_time - start_time, 3)
            
            # Create monitoring check
            check = MonitoringCheck.objects.create(
                website=website,
                check_time=timezone.now(),
                is_online=response.status_code == website.expected_status_code,
                response_time=response_time,
                status_code=response.status_code,
                error_message="" if response.status_code == website.expected_status_code else f"Expected status {website.expected_status_code}, got {response.status_code}",
                response_content=response.text[:1000]
            )
            
            # Handle alerts
            self.handle_website_alerts(website, check)
            
            return check
            
        except requests.exceptions.Timeout:
            check = MonitoringCheck.objects.create(
                website=website,
                check_time=timezone.now(),
                is_online=False,
                response_time=None,
                status_code=None,
                error_message=f"Request timed out after {website.timeout} seconds",
                response_content=""
            )
            self.handle_website_alerts(website, check)
            return check
            
        except Exception as e:
            check = MonitoringCheck.objects.create(
                website=website,
                check_time=timezone.now(),
                is_online=False,
                response_time=None,
                status_code=None,
                error_message=f"Error: {str(e)}",
                response_content=""
            )
            self.handle_website_alerts(website, check)
            return check
    
    def check_internal_app(self, internal_app):
        try:
            start_time = time.time()
            response = requests.get(internal_app.url, timeout=internal_app.timeout, allow_redirects=True)
            end_time = time.time()
            response_time = round(end_time - start_time, 3)
            
            # Create monitoring check
            check = MonitoringCheck.objects.create(
                internal_app=internal_app,
                website=internal_app.website,
                check_time=timezone.now(),
                is_online=response.status_code == internal_app.expected_status_code,
                response_time=response_time,
                status_code=response.status_code,
                error_message="" if response.status_code == internal_app.expected_status_code else f"Expected status {internal_app.expected_status_code}, got {response.status_code}",
                response_content=response.text[:1000]
            )
            
            # Handle alerts
            self.handle_internal_app_alerts(internal_app, check)
            
            return check
            
        except requests.exceptions.Timeout:
            check = MonitoringCheck.objects.create(
                internal_app=internal_app,
                website=internal_app.website,
                check_time=timezone.now(),
                is_online=False,
                response_time=None,
                status_code=None,
                error_message=f"Request timed out after {internal_app.timeout} seconds",
                response_content=""
            )
            self.handle_internal_app_alerts(internal_app, check)
            return check
            
        except Exception as e:
            check = MonitoringCheck.objects.create(
                internal_app=internal_app,
                website=internal_app.website,
                check_time=timezone.now(),
                is_online=False,
                response_time=None,
                status_code=None,
                error_message=f"Error: {str(e)}",
                response_content=""
            )
            self.handle_internal_app_alerts(internal_app, check)
            return check
    
    def _count_consecutive_failures(self, queryset):
        """Count how many latest checks in a row were offline."""
        consecutive_failures = 0
        for c in queryset:
            if not c.is_online:
                consecutive_failures += 1
            else:
                break
        return consecutive_failures

    def handle_website_alerts(self, website, check):
        """
        Two-strike rule (every check is 5 minutes apart):
        1st DOWN  → log only, do NOT email (could be a blip)
        2nd DOWN  → confirmed outage → send email once
        3rd+ DOWN → stay silent until the site recovers and fails again
        """
        if website.status != 'active':
            return

        if not check.is_online:
            recent_checks = MonitoringCheck.objects.filter(
                website=website,
                internal_app__isnull=True
            ).order_by('-check_time')[:20]

            consecutive_failures = self._count_consecutive_failures(recent_checks)

            # Exactly 2 = just confirmed down after waiting one more 5-min cycle
            if consecutive_failures == 2 and AlertLog.should_send_alert(website, 'down'):
                subject = f"URGENT: {website.name} is DOWN"
                message = f"""
Dear Administrator,

Monitoring Alert: {website.name} is confirmed DOWN.

The site failed two consecutive health checks (about 10 minutes).
A single failure is ignored to avoid false alarms.

Website Details:
- Name: {website.name}
- URL: {website.url}
- Confirmed at: {check.check_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
- Error Details: {check.error_message}

Please investigate this issue immediately to restore services.

Best regards,
Web Health Checker System
                """

                AlertLog.send_alert(
                    website=website,
                    alert_type='down',
                    subject=subject,
                    message=message,
                    email_to=website.alert_email
                )
        # Online: recovery email not implemented yet (future improvement)

    def handle_internal_app_alerts(self, internal_app, check):
        """Same two-strike rule as websites, scoped to one internal app."""
        if internal_app.website.status != 'active':
            return

        if not check.is_online:
            recent_checks = MonitoringCheck.objects.filter(
                internal_app=internal_app
            ).order_by('-check_time')[:20]

            consecutive_failures = self._count_consecutive_failures(recent_checks)

            if consecutive_failures == 2 and AlertLog.should_send_alert(internal_app.website, 'down'):
                subject = f"URGENT: Internal App {internal_app.name} is DOWN"
                message = f"""
Dear Administrator,

Monitoring Alert: The internal app '{internal_app.name}' on {internal_app.website.name} is confirmed DOWN.

It failed two consecutive health checks (about 10 minutes).
A single failure is ignored to avoid false alarms.

Component Details:
- Internal App: {internal_app.name} ({internal_app.app_type})
- Website: {internal_app.website.name}
- URL: {internal_app.url}
- Confirmed at: {check.check_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
- Error Details: {check.error_message}

Please investigate this issue immediately.

Best regards,
Web Health Checker System
                """

                AlertLog.send_alert(
                    website=internal_app.website,
                    alert_type='down',
                    subject=subject,
                    message=message,
                    email_to=internal_app.website.alert_email
                )
    
    def run_monitoring_cycle(self):
        if not self.settings.is_monitoring_active:
            logger.info("Monitoring is disabled")
            return
        
        # Get all active websites
        websites = Website.objects.filter(status='active')
        
        # Get all active internal apps
        internal_apps = InternalApp.objects.filter(is_active=True, website__status='active')
        
        total_checks = websites.count() + internal_apps.count()
        
        if total_checks > 0:
            logger.info(f"Running {total_checks} monitoring checks")
            
            # Check all websites
            for website in websites:
                try:
                    self.check_website(website)
                except Exception as e:
                    logger.error(f"Error checking website {website.name}: {str(e)}")
            
            # Check all internal apps
            for internal_app in internal_apps:
                try:
                    self.check_internal_app(internal_app)
                except Exception as e:
                    logger.error(f"Error checking internal app {internal_app.name}: {str(e)}")
            
            logger.info("Monitoring cycle completed")
        else:
            logger.info("No active websites or internal apps to monitor")


class MonitoringStats:
    
    @staticmethod
    def get_website_stats(website):
        from django.utils import timezone
        
        checks = MonitoringCheck.objects.filter(
            website=website,
            internal_app__isnull=True
        ).order_by('-check_time')[:20]
        
        if not checks.exists():
            return {
                'total_checks': 0,
                'online_checks': 0,
                'offline_checks': 0,
                'uptime_percentage': 0,
                'avg_response_time': 0,
                'last_check': None,
                'status': 'unknown'
            }
        
        online_count = sum(1 for c in checks if c.is_online)
        total_count = len(checks)
        
        avg_response_time = 0
        response_times = [c.response_time for c in checks if c.is_online and c.response_time is not None]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
        
        uptime_percentage = (online_count / total_count) * 100
        
        return {
            'total_checks': total_count,
            'online_checks': online_count,
            'offline_checks': total_count - online_count,
            'uptime_percentage': round(uptime_percentage, 2),
            'avg_response_time': round(avg_response_time, 3),
            'last_check': checks[0].check_time,
            'status': 'online' if checks[0].is_online else 'offline'
        }
    
    @staticmethod
    def get_global_stats():
        websites = Website.objects.filter(status='active')
        internal_apps = InternalApp.objects.filter(is_active=True, website__status='active')
        
        total_websites = websites.count()
        online_websites = sum(1 for w in websites if w.is_online)
        
        total_internal_apps = internal_apps.count()
        online_internal_apps = sum(1 for app in internal_apps if app.is_online)
        
        # Calculate average uptime percentage across all websites
        avg_uptime = 0
        if websites.exists():
            avg_uptime = sum(w.uptime_percentage for w in websites) / total_websites
            
        return {
            'total_websites': total_websites,
            'online_websites': online_websites,
            'offline_websites': total_websites - online_websites,
            'total_internal_apps': total_internal_apps,
            'online_internal_apps': online_internal_apps,
            'offline_internal_apps': total_internal_apps - online_internal_apps,
            'overall_uptime': round(avg_uptime, 2)
        }
#migrations
