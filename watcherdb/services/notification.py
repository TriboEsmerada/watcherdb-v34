"""
Notification Service
Handles sending alerts through multiple channels: Email, Teams, Slack, Webhook
"""

import json
import logging
import os
from typing import Dict, Any, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from services.secrets import get_secret

try:
    import aiosmtplib
    AIOSMTPLIB_AVAILABLE = True
except ImportError:
    AIOSMTPLIB_AVAILABLE = False

try:
    import pymsteams
    PYMSTEAMS_AVAILABLE = True
except ImportError:
    PYMSTEAMS_AVAILABLE = False

try:
    from slack_sdk.webhook import WebhookClient
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

import urllib.request
import urllib.error

from watcherdb.models.alerts import Alert, AlertLevel

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification service
    Supports: Email, Microsoft Teams, Slack, Generic Webhooks
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config()
        logger.info("NotificationService initialized")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration (supports YAML or environment variables)"""
        # For now, return default config that reads from environment variables
        # In production, this would load from config.yaml
        return {
            "email": {
                "smtp_server": os.getenv("SMTP_SERVER", "smtp.office365.com"),
                "smtp_port": int(os.getenv("SMTP_PORT", "587")),
                "use_tls": True,
                "from_address": os.getenv("SMTP_FROM", "watcherdb@example.com"),
                "to_addresses": os.getenv("SMTP_TO", "dba@example.com").split(","),
                "username": os.getenv("SMTP_USERNAME", "watcherdb@example.com"),
                # SMTP_PASSWORD pode estar encriptada (prefixo "encrypted:") — get_secret desencripta
                "password": get_secret("SMTP_PASSWORD", ""),
            },
            "teams": {
                "webhook_url": os.getenv("TEAMS_WEBHOOK_URL", ""),
            },
            "slack": {
                "webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
            },
            "webhook": {
                "url": os.getenv("CUSTOM_WEBHOOK_URL", ""),
                "method": "POST",
                "timeout": 10,
            }
        }

    # ==========================================
    # Email Notifications
    # ==========================================
    def send_email(self, alert: Alert) -> bool:
        """Send alert via email"""
        try:
            config = self.config.get("email", {})

            if not config.get("password"):
                logger.warning("Email password not configured, skipping email notification")
                return False

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.level.value.upper()}] {alert.title}"
            msg["From"] = config["from_address"]
            msg["To"] = ", ".join(config["to_addresses"])

            # Create HTML and plain text versions
            text_body = self._format_alert_text(alert)
            html_body = self._format_alert_html(alert)

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
                if config.get("use_tls"):
                    server.starttls()

                server.login(config["username"], config["password"])
                server.send_message(msg)

            logger.info(f"Email sent for alert: {alert.id}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def _format_alert_text(self, alert: Alert) -> str:
        """Format alert as plain text"""
        text = f"{alert.title}\n"
        text += "=" * len(alert.title) + "\n\n"
        text += f"Severity: {alert.level.value.upper()}\n"
        text += f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if alert.server_name:
            text += f"Server: {alert.server_name}\n"
        if alert.database_name:
            text += f"Database: {alert.database_name}\n"

        text += f"\n{alert.message}\n"

        if alert.metadata:
            text += "\nAdditional Information:\n"
            for key, value in alert.metadata.items():
                text += f"  {key}: {value}\n"

        return text

    def _format_alert_html(self, alert: Alert) -> str:
        """Format alert as HTML"""
        color = {
            AlertLevel.INFO: "#0078D4",
            AlertLevel.WARNING: "#FFA500",
            AlertLevel.CRITICAL: "#D13438"
        }.get(alert.level, "#0078D4")

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .alert-box {{ border-left: 4px solid {color}; padding: 15px; background-color: #f9f9f9; }}
                .alert-title {{ color: {color}; font-size: 18px; font-weight: bold; }}
                .alert-meta {{ color: #666; font-size: 12px; margin: 10px 0; }}
                .alert-message {{ margin: 15px 0; line-height: 1.6; }}
                .metadata {{ background-color: #fff; padding: 10px; border: 1px solid #ddd; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="alert-box">
                <div class="alert-title">{alert.title}</div>
                <div class="alert-meta">
                    <strong>Severity:</strong> {alert.level.value.upper()} |
                    <strong>Time:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
        """

        if alert.server_name:
            html += f" | <strong>Server:</strong> {alert.server_name}"
        if alert.database_name:
            html += f" | <strong>Database:</strong> {alert.database_name}"

        html += f"""
                </div>
                <div class="alert-message">
                    {alert.message.replace(chr(10), '<br>')}
                </div>
        """

        if alert.metadata:
            html += '<div class="metadata"><strong>Additional Information:</strong><br>'
            for key, value in alert.metadata.items():
                html += f"<strong>{key}:</strong> {value}<br>"
            html += '</div>'

        html += """
            </div>
        </body>
        </html>
        """

        return html

    # ==========================================
    # Microsoft Teams Notifications
    # ==========================================
    def send_teams(self, alert: Alert) -> bool:
        """Send alert to Microsoft Teams"""
        try:
            webhook_url = self.config.get("teams", {}).get("webhook_url", "")

            if not webhook_url:
                logger.warning("Teams webhook URL not configured")
                return False

            if not PYMSTEAMS_AVAILABLE:
                logger.warning("pymsteams library not installed, using fallback HTTP method")
                return self._send_teams_http(alert, webhook_url)

            # Use pymsteams library
            teams_message = pymsteams.connectorcard(webhook_url)

            # Set title and color based on level
            color_map = {
                AlertLevel.INFO: "0078D4",
                AlertLevel.WARNING: "FFA500",
                AlertLevel.CRITICAL: "D13438"
            }
            teams_message.color(color_map.get(alert.level, "0078D4"))
            teams_message.title(f"[{alert.level.value.upper()}] {alert.title}")
            teams_message.text(alert.message)

            # Add sections
            if alert.server_name or alert.database_name:
                section = pymsteams.cardsection()
                if alert.server_name:
                    section.addFact("Server", alert.server_name)
                if alert.database_name:
                    section.addFact("Database", alert.database_name)
                section.addFact("Time", alert.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
                teams_message.addSection(section)

            teams_message.send()
            logger.info(f"Teams notification sent for alert: {alert.id}")
            return True

        except Exception as e:
            logger.error(f"Error sending Teams notification: {e}")
            return False

    def _send_teams_http(self, alert: Alert, webhook_url: str) -> bool:
        """Send Teams notification using HTTP (fallback when pymsteams not available)"""
        try:
            color_map = {
                AlertLevel.INFO: "0078D4",
                AlertLevel.WARNING: "FFA500",
                AlertLevel.CRITICAL: "D13438"
            }

            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": color_map.get(alert.level, "0078D4"),
                "title": f"[{alert.level.value.upper()}] {alert.title}",
                "text": alert.message,
                "sections": [
                    {
                        "facts": [
                            {"name": "Time", "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
                        ]
                    }
                ]
            }

            if alert.server_name:
                payload["sections"][0]["facts"].append({"name": "Server", "value": alert.server_name})
            if alert.database_name:
                payload["sections"][0]["facts"].append({"name": "Database", "value": alert.database_name})

            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"Teams notification sent (HTTP): {alert.id}")
                    return True
                else:
                    logger.error(f"Teams HTTP error: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Error sending Teams HTTP notification: {e}")
            return False

    # ==========================================
    # Slack Notifications
    # ==========================================
    def send_slack(self, alert: Alert) -> bool:
        """Send alert to Slack"""
        try:
            webhook_url = self.config.get("slack", {}).get("webhook_url", "")

            if not webhook_url:
                logger.warning("Slack webhook URL not configured")
                return False

            # Use HTTP fallback (works without slack_sdk)
            color_map = {
                AlertLevel.INFO: "#0078D4",
                AlertLevel.WARNING: "#FFA500",
                AlertLevel.CRITICAL: "#D13438"
            }

            fields = [
                {"title": "Time", "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S'), "short": True}
            ]

            if alert.server_name:
                fields.append({"title": "Server", "value": alert.server_name, "short": True})
            if alert.database_name:
                fields.append({"title": "Database", "value": alert.database_name, "short": True})

            payload = {
                "username": "WatcherDB",
                "icon_emoji": ":database:",
                "attachments": [
                    {
                        "color": color_map.get(alert.level, "#0078D4"),
                        "title": f"[{alert.level.value.upper()}] {alert.title}",
                        "text": alert.message,
                        "fields": fields,
                        "footer": "WatcherDB Alert System",
                        "ts": int(alert.timestamp.timestamp())
                    }
                ]
            }

            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"Slack notification sent: {alert.id}")
                    return True
                else:
                    logger.error(f"Slack HTTP error: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False

    # ==========================================
    # Generic Webhook Notifications
    # ==========================================
    def send_webhook(self, alert: Alert) -> bool:
        """Send alert to generic webhook"""
        try:
            webhook_config = self.config.get("webhook", {})
            webhook_url = webhook_config.get("url", "")

            if not webhook_url:
                logger.warning("Webhook URL not configured")
                return False

            payload = alert.to_dict()

            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method=webhook_config.get("method", "POST")
            )

            timeout = webhook_config.get("timeout", 10)

            with urllib.request.urlopen(req, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    logger.info(f"Webhook notification sent: {alert.id}")
                    return True
                else:
                    logger.error(f"Webhook HTTP error: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            return False
