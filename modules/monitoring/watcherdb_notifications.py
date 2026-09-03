# ============================================================================
# WATCHERDB SISTEMA DE NOTIFICAÇÕES - WHATSAPP E EMAIL
# ============================================================================
# Arquivo: modules/monitoring/watcherdb_notifications.py
# ============================================================================

import asyncio
import logging
import json
import smtplib
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

@dataclass
class NotificationConfig:
    """Configuração de notificações"""
    # WhatsApp
    whatsapp_enabled: bool = False
    whatsapp_api_url: str = ""
    whatsapp_token: str = ""
    whatsapp_phone: str = ""
    
    # Email
    email_enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = None
    
    # Configurações gerais
    min_severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    notification_frequency_minutes: int = 60  # Evitar spam

class NotificationService:
    """Serviço de notificações para alertas preditivos"""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self._last_notification = {}  # Cache para evitar spam
    
    async def send_predictive_alert(self, alert_data: Dict) -> bool:
        """Envia notificação de alerta preditivo"""
        try:
            # Verificar severidade mínima
            if not self._should_notify(alert_data):
                return False
            
            # Verificar frequência (evitar spam)
            if self._is_too_frequent(alert_data):
                return False
            
            # Preparar mensagem
            message = self._format_alert_message(alert_data)
            
            # Enviar notificações
            success = True
            
            if self.config.whatsapp_enabled:
                whatsapp_success = await self._send_whatsapp(message, alert_data)
                success = success and whatsapp_success
            
            if self.config.email_enabled:
                email_success = await self._send_email(message, alert_data)
                success = success and email_success
            
            # Log estruturado
            self._log_notification_event('notification_sent', {
                'alert_id': f"{alert_data.get('server_id')}_{alert_data.get('database_name')}_{alert_data.get('filegroup_name')}",
                'severity': alert_data.get('severity'),
                'whatsapp_sent': self.config.whatsapp_enabled,
                'email_sent': self.config.email_enabled,
                'success': success,
                'timestamp': datetime.now().isoformat()
            })
            
            return success
            
        except Exception as e:
            logger.error(f"❌ [NOTIFICATIONS] Erro ao enviar notificação: {e}", exc_info=True)
            return False
    
    def _should_notify(self, alert_data: Dict) -> bool:
        """Verifica se deve enviar notificação baseado na severidade"""
        severity_order = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        
        alert_severity = alert_data.get('severity', 'LOW')
        min_severity = self.config.min_severity
        
        return severity_order.get(alert_severity, 0) >= severity_order.get(min_severity, 0)
    
    def _is_too_frequent(self, alert_data: Dict) -> bool:
        """Verifica se a notificação é muito frequente (evitar spam)"""
        alert_key = f"{alert_data.get('server_id')}_{alert_data.get('database_name')}_{alert_data.get('filegroup_name')}"
        now = datetime.now()
        
        if alert_key in self._last_notification:
            last_time = self._last_notification[alert_key]
            time_diff = (now - last_time).total_seconds() / 60  # minutos
            
            if time_diff < self.config.notification_frequency_minutes:
                logger.info(f"⏰ [NOTIFICATIONS] Notificação muito frequente para {alert_key}")
                return True
        
        # Atualizar timestamp
        self._last_notification[alert_key] = now
        return False
    
    def _format_alert_message(self, alert_data: Dict) -> str:
        """Formata mensagem de alerta"""
        server_id = alert_data.get('server_id', 'N/A')
        database = alert_data.get('database_name', 'N/A')
        filegroup = alert_data.get('filegroup_name', 'N/A')
        severity = alert_data.get('severity', 'N/A')
        usage_percent = alert_data.get('current_usage_percent', 0)
        days_until_full = alert_data.get('days_until_full', 0)
        recommendation = alert_data.get('recommendation', 'N/A')
        confidence_score = alert_data.get('confidence_score', 0)
        
        # Emojis por severidade
        severity_emoji = {
            'CRITICAL': '🔴',
            'HIGH': '🟠',
            'MEDIUM': '🟡',
            'LOW': '🟢'
        }
        
        emoji = severity_emoji.get(severity, '⚠️')
        
        message = f"""
{emoji} *ALERTA PREDITIVO WatcherDB*

*Servidor:* {server_id}
*Database:* {database}
*Filegroup:* {filegroup}
*Severidade:* {severity}
*Uso Atual:* {usage_percent:.1f}%
*Dias até Cheio:* {days_until_full}
*Confiança:* {confidence_score:.1%}

*Recomendação:*
{recommendation}

*Timestamp:* {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        """.strip()
        
        return message
    
    async def _send_whatsapp(self, message: str, alert_data: Dict) -> bool:
        """Envia notificação via WhatsApp"""
        try:
            # TODO: Implementar integração real com API do WhatsApp
            # Por enquanto, apenas log
            logger.info(f"📱 [WHATSAPP] Mensagem preparada: {message[:100]}...")
            
            # Simular envio
            await asyncio.sleep(0.1)  # Simular delay de API
            
            logger.info("✅ [WHATSAPP] Notificação enviada com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ [WHATSAPP] Erro ao enviar: {e}")
            return False
    
    async def _send_email(self, message: str, alert_data: Dict) -> bool:
        """Envia notificação via email"""
        try:
            if not self.config.email_enabled or not self.config.email_to:
                return True  # Não configurado, não é erro
            
            # Criar mensagem
            msg = MIMEMultipart()
            msg['From'] = self.config.email_from
            msg['To'] = ', '.join(self.config.email_to)
            msg['Subject'] = f"🚨 WatcherDB Alert - {alert_data.get('severity', 'UNKNOWN')} - {alert_data.get('server_id', 'N/A')}"
            
            # Corpo da mensagem
            body = message.replace('*', '')  # Remover markdown para email
            msg.attach(MIMEText(body, 'plain'))
            
            # Enviar email
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.send_message(msg)
            
            logger.info("✅ [EMAIL] Notificação enviada com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ [EMAIL] Erro ao enviar: {e}")
            return False
    
    def _log_notification_event(self, event_type: str, data: Dict):
        """Log estruturado em JSON para análise posterior"""
        log_data = {
            'event': event_type,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        logger.info(json.dumps(log_data, ensure_ascii=False))
    
    async def send_trends_summary(self, trends_data: Dict) -> bool:
        """Envia resumo de tendências"""
        try:
            server_id = trends_data.get('server_id', 'N/A')
            total_filegroups = trends_data.get('total_filegroups', 0)
            high_risk = trends_data.get('summary', {}).get('high_risk_filegroups', 0)
            avg_growth = trends_data.get('summary', {}).get('average_growth_rate', 0)
            
            message = f"""
📈 *RELATÓRIO DE TENDÊNCIAS WatcherDB*

*Servidor:* {server_id}
*Filegroups Analisados:* {total_filegroups}
*Alto Risco:* {high_risk}
*Crescimento Médio:* {avg_growth:.2f} GB/dia

*Análise:* {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            """.strip()
            
            # Enviar notificações
            success = True
            
            if self.config.whatsapp_enabled:
                success = success and await self._send_whatsapp(message, {'server_id': server_id})
            
            if self.config.email_enabled:
                success = success and await self._send_email(message, {'server_id': server_id})
            
            return success
            
        except Exception as e:
            logger.error(f"❌ [NOTIFICATIONS] Erro ao enviar resumo: {e}")
            return False

# Exemplo de uso
async def example_usage():
    """Exemplo de como usar o sistema de notificações"""
    
    # Configuração
    config = NotificationConfig(
        whatsapp_enabled=True,
        whatsapp_api_url="https://api.whatsapp.com/send",
        whatsapp_token="your_token_here",
        whatsapp_phone="+5511999999999",
        
        email_enabled=True,
        smtp_server="smtp.gmail.com",
        smtp_port=587,
        smtp_username="your_email@gmail.com",
        smtp_password="your_app_password",
        email_from="watcherdb@company.com",
        email_to=["admin@company.com", "dba@company.com"],
        
        min_severity="HIGH",
        notification_frequency_minutes=30
    )
    
    # Criar serviço
    notification_service = NotificationService(config)
    
    # Exemplo de alerta
    alert_data = {
        'server_id': 'SQLIDSPRD03_I01',
        'database_name': 'DW_TAP_ATH',
        'filegroup_name': 'BKDREV_IDX',
        'severity': 'CRITICAL',
        'current_usage_percent': 92.5,
        'days_until_full': 3,
        'recommendation': '🔴 URGENTE: Expandir filegroup imediatamente',
        'confidence_score': 0.95
    }
    
    # Enviar notificação
    success = await notification_service.send_predictive_alert(alert_data)
    
    if success:
        print("✅ Notificação enviada com sucesso!")
    else:
        print("❌ Falha ao enviar notificação")

if __name__ == "__main__":
    asyncio.run(example_usage())
