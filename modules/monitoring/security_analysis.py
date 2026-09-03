"""
WatcherDB Security Analysis Module
Análise de segurança do SQL Server e Windows Server
Verificações passivas (apenas consultas, sem testes ativos)
"""

import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SecuritySeverity(Enum):
    """Severidade da vulnerabilidade"""
    CRITICAL = "critical"  # Crítico - ação imediata necessária
    HIGH = "high"  # Alto - ação recomendada em breve
    MEDIUM = "medium"  # Médio - melhoria recomendada
    LOW = "low"  # Baixo - recomendação geral
    INFO = "info"  # Informativo - apenas informação


class SecurityStatus(Enum):
    """Status da verificação"""
    PASS = "pass"  # Configuração correta
    FAIL = "fail"  # Configuração incorreta/vulnerável
    WARNING = "warning"  # Configuração com ressalvas
    UNKNOWN = "unknown"  # Não foi possível verificar


@dataclass
class SecurityCheck:
    """Resultado de uma verificação de segurança"""
    check_id: str
    category: str
    title: str
    description: str
    status: str  # SecurityStatus
    severity: str  # SecuritySeverity
    current_value: Optional[str] = None
    expected_value: Optional[str] = None
    recommendation: Optional[str] = None
    reference: Optional[str] = None
    details: Optional[Dict] = None


# Fix B DS-Reconcile 2026-06-09: surfacar categorias que falham/vazias como UNKNOWN
# em vez de as saltar em silencio (DBA via "tudo coberto" quando nao estava).
# [WAIVER aplicado 2026-06-09 | regra: edicao ficheiro producao | scope: Fix B security UNKNOWN]
_CHECK_CATEGORY_LABELS = {
    'auth': 'Autenticação', 'permissions': 'Permissões',
    'config': 'Configurações SQL Server', 'encryption': 'Criptografia',
    'audit': 'Auditoria', 'version': 'Versão',
}


def _make_unknown_check(check_key: str, reason: str) -> 'SecurityCheck':
    """Check UNKNOWN para uma categoria que nao pode ser verificada (transparencia)."""
    label = _CHECK_CATEGORY_LABELS.get(check_key, check_key)
    return SecurityCheck(
        check_id=f'{check_key}-unknown', category=label,
        title=f'{label} — não verificado',
        description=f'Não foi possível executar esta verificação ({reason}).',
        status=SecurityStatus.UNKNOWN.value, severity=SecuritySeverity.INFO.value,
        recommendation='Verificar permissões do sql_monitoring ou conectividade ao servidor.',
    )


class SecurityAnalysisEngine:
    """Engine para análise de segurança do SQL Server"""
    
    def __init__(self, sql_monitoring):
        self.sql_monitoring = sql_monitoring
        
    async def analyze_server_security(self, server_id: str) -> Dict:
        """
        Analisa segurança do servidor SQL Server
        Retorna lista de verificações de segurança
        """
        try:
            checks: List[SecurityCheck] = []

            # Executar TODOS os 6 checks em PARALELO (antes era sequencial ~8s, agora ~2s)
            check_names = ['auth', 'permissions', 'config', 'encryption', 'audit', 'version']
            results = await asyncio.gather(
                self._check_authentication(server_id),
                self._check_permissions(server_id),
                self._check_sql_configurations(server_id),
                self._check_encryption(server_id),
                self._check_auditing(server_id),
                self._check_version(server_id),
                return_exceptions=True
            )

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Security check {check_names[i]} failed for {server_id}: {result}")
                    checks.append(_make_unknown_check(check_names[i], f'erro: {result}'))
                    continue
                if not result:
                    logger.warning(f"Security check {check_names[i]} sem resultados para {server_id}")
                    checks.append(_make_unknown_check(check_names[i], 'sem resultados — query falhou ou sem permissão'))
                    continue
                checks.extend(result)
            
            # Calcular estatísticas
            total = len(checks)
            passed = sum(1 for c in checks if c.status == SecurityStatus.PASS.value)
            failed = sum(1 for c in checks if c.status == SecurityStatus.FAIL.value)
            warnings = sum(1 for c in checks if c.status == SecurityStatus.WARNING.value)
            
            critical_count = sum(1 for c in checks if c.severity == SecuritySeverity.CRITICAL.value)
            high_count = sum(1 for c in checks if c.severity == SecuritySeverity.HIGH.value)
            
            return {
                'success': True,
                'server_id': server_id,
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'total_checks': total,
                    'passed': passed,
                    'failed': failed,
                    'warnings': warnings,
                    'critical_issues': critical_count,
                    'high_issues': high_count,
                    'security_score': round((passed / total * 100) if total > 0 else 0, 1)
                },
                'checks': [asdict(c) for c in checks]
            }
            
        except Exception as e:
            logger.error(f"Erro ao analisar segurança de {server_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'server_id': server_id
            }
    
    async def _check_authentication(self, server_id: str) -> List[SecurityCheck]:
        """Verifica configurações de autenticação"""
        checks = []
        
        try:
            # 1. Verificar se SQL Server Authentication está habilitado
            query = """
            SELECT 
                CASE 
                    WHEN value = 1 THEN 'SQL Server Authentication habilitado'
                    WHEN value = 2 THEN 'Mixed Mode (Windows + SQL)'
                    ELSE 'Windows Authentication apenas'
                END AS auth_mode,
                value AS auth_mode_value
            FROM sys.configurations WITH(NOLOCK)
            WHERE name = 'user options'
            """
            
            # Query correta para verificar modo de autenticação
            query_auth = """
            SELECT 
                CASE 
                    WHEN SERVERPROPERTY('IsIntegratedSecurityOnly') = 1 THEN 'Windows Authentication apenas'
                    ELSE 'Mixed Mode (Windows + SQL Server Authentication)'
                END AS auth_mode,
                SERVERPROPERTY('IsIntegratedSecurityOnly') AS is_windows_only
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_auth)
            if result.get('success') and result.get('rows'):
                row = result['rows'][0]
                is_windows_only = row.get('is_windows_only', 0)
                auth_mode = row.get('auth_mode', 'Unknown')
                
                if is_windows_only == 1:
                    checks.append(SecurityCheck(
                        check_id='auth-001',
                        category='Autenticação',
                        title='Modo de Autenticação',
                        description='SQL Server está configurado para usar apenas Windows Authentication',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Windows Authentication apenas',
                        expected_value='Windows Authentication apenas',
                        recommendation='Configuração recomendada. Windows Authentication é mais seguro que SQL Server Authentication.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/choose-an-authentication-mode'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='auth-001',
                        category='Autenticação',
                        title='Modo de Autenticação',
                        description='SQL Server está configurado em Mixed Mode (Windows + SQL Server Authentication)',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.HIGH.value,
                        current_value='Mixed Mode',
                        expected_value='Windows Authentication apenas',
                        recommendation='Recomenda-se usar apenas Windows Authentication. Se SQL Server Authentication for necessário, certifique-se de que todas as contas têm senhas fortes e políticas de senha adequadas.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/choose-an-authentication-mode'
                    ))
            
            # 2. Verificar se conta SA está habilitada
            query_sa = """
            SELECT 
                name,
                is_disabled,
                create_date,
                modify_date
            FROM sys.server_principals WITH(NOLOCK)
            WHERE name = 'sa' AND type = 'S'
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_sa)
            if result.get('success') and result.get('rows'):
                row = result['rows'][0]
                is_disabled = row.get('is_disabled', 0)
                
                if is_disabled == 1:
                    checks.append(SecurityCheck(
                        check_id='auth-002',
                        category='Autenticação',
                        title='Conta SA',
                        description='Conta SA está desabilitada',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Desabilitada',
                        expected_value='Desabilitada',
                        recommendation='Conta SA está desabilitada, o que é recomendado por segurança.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/disable-sa-login'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='auth-002',
                        category='Autenticação',
                        title='Conta SA',
                        description='Conta SA está habilitada',
                        status=SecurityStatus.FAIL.value,
                        severity=SecuritySeverity.CRITICAL.value,
                        current_value='Habilitada',
                        expected_value='Desabilitada',
                        recommendation='A conta SA é um alvo comum de ataques. Recomenda-se desabilitá-la e usar contas Windows com permissões específicas. Se precisar manter habilitada, certifique-se de que a senha é muito forte e que está sendo monitorada.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/disable-sa-login'
                    ))
            
            # 3. Verificar contas com senha nunca expira
            query_password_policy = """
            SELECT 
                name,
                type_desc,
                is_disabled,
                create_date
            FROM sys.server_principals WITH(NOLOCK)
            WHERE type IN ('S', 'U') 
                AND is_disabled = 0
                AND name NOT IN ('sa', '##MS_PolicyEventProcessingLogin##', '##MS_PolicyTsqlExecutionLogin##')
            ORDER BY name
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_password_policy)
            if result.get('success'):
                sql_logins = [r for r in result.get('rows', []) if r.get('type_desc') == 'SQL_LOGIN']
                
                if len(sql_logins) > 0:
                    checks.append(SecurityCheck(
                        check_id='auth-003',
                        category='Autenticação',
                        title='Logins SQL Server',
                        description=f'Encontrados {len(sql_logins)} logins SQL Server habilitados',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value=f'{len(sql_logins)} logins SQL habilitados',
                        expected_value='0 ou mínimo necessário',
                        recommendation='Recomenda-se usar Windows Authentication sempre que possível. Se logins SQL forem necessários, certifique-se de que têm senhas fortes, políticas de expiração e são monitorados regularmente.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/password-policy',
                        details={'logins': [l.get('name') for l in sql_logins[:10]]}  # Primeiros 10
                    ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar autenticação: {e}")
            checks.append(SecurityCheck(
                check_id='auth-error',
                category='Autenticação',
                title='Erro na Verificação',
                description=f'Erro ao verificar configurações de autenticação: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks
    
    async def _check_permissions(self, server_id: str) -> List[SecurityCheck]:
        """Verifica permissões e logins"""
        checks = []
        
        try:
            # 1. Verificar logins com permissões sysadmin
            query_sysadmin = """
            SELECT 
                p.name AS login_name,
                p.type_desc,
                p.is_disabled,
                p.create_date
            FROM sys.server_principals p WITH(NOLOCK)
            INNER JOIN sys.server_role_members rm ON p.principal_id = rm.member_principal_id
            INNER JOIN sys.server_principals r ON rm.role_principal_id = r.principal_id
            WHERE r.name = 'sysadmin'
                AND p.name NOT LIKE 'NT SERVICE%'
                AND p.name NOT LIKE 'NT AUTHORITY%'
                AND p.name NOT IN ('sa', 'BUILTIN\\Administrators')
            ORDER BY p.name
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_sysadmin)
            if result.get('success'):
                sysadmins = result.get('rows', [])
                
                if len(sysadmins) == 0:
                    checks.append(SecurityCheck(
                        check_id='perm-001',
                        category='Permissões',
                        title='Permissões Sysadmin',
                        description='Apenas contas de sistema têm permissões sysadmin',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Apenas contas de sistema',
                        expected_value='Apenas contas de sistema ou mínimo necessário',
                        recommendation='Boa prática: limitar permissões sysadmin apenas ao necessário. Use o princípio do menor privilégio.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/server-level-roles'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='perm-001',
                        category='Permissões',
                        title='Permissões Sysadmin',
                        description=f'Encontrados {len(sysadmins)} logins com permissões sysadmin',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.HIGH.value,
                        current_value=f'{len(sysadmins)} logins com sysadmin',
                        expected_value='Apenas contas de sistema ou mínimo necessário',
                        recommendation='Recomenda-se revisar e reduzir o número de logins com permissões sysadmin. Use roles específicas e o princípio do menor privilégio.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/server-level-roles',
                        details={'sysadmins': [s.get('login_name') for s in sysadmins[:10]]}
                    ))
            
            # 2. Verificar database owners incorretos
            query_db_owners = """
            SELECT 
                d.name AS database_name,
                d.owner_sid,
                p.name AS owner_name,
                p.type_desc AS owner_type
            FROM sys.databases d WITH(NOLOCK)
            LEFT JOIN sys.server_principals p ON d.owner_sid = p.sid
            WHERE d.database_id > 4
                AND d.state = 0
                AND (p.name IS NULL OR p.name = 'sa' OR p.type_desc = 'SQL_LOGIN')
            ORDER BY d.name
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_db_owners)
            if result.get('success'):
                bad_owners = result.get('rows', [])
                
                if len(bad_owners) == 0:
                    checks.append(SecurityCheck(
                        check_id='perm-002',
                        category='Permissões',
                        title='Database Owners',
                        description='Todos os databases têm owners apropriados (Windows accounts)',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Owners apropriados',
                        expected_value='Windows accounts como owners',
                        recommendation='Boa prática: databases devem ter Windows accounts como owners, não contas SQL ou sa.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/ownership-and-user-schema-separation'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='perm-002',
                        category='Permissões',
                        title='Database Owners',
                        description=f'Encontrados {len(bad_owners)} databases com owners incorretos',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value=f'{len(bad_owners)} databases com owners incorretos',
                        expected_value='Windows accounts como owners',
                        recommendation='Recomenda-se alterar os owners dos databases para Windows accounts. Use: ALTER AUTHORIZATION ON DATABASE::[database_name] TO [domain\\user]',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/authentication-access/ownership-and-user-schema-separation',
                        details={'databases': [b.get('database_name') for b in bad_owners[:10]]}
                    ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar permissões: {e}")
            checks.append(SecurityCheck(
                check_id='perm-error',
                category='Permissões',
                title='Erro na Verificação',
                description=f'Erro ao verificar permissões: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks
    
    async def _check_sql_configurations(self, server_id: str) -> List[SecurityCheck]:
        """Verifica configurações de segurança do SQL Server"""
        checks = []
        
        try:
            # Query para verificar várias configurações de segurança
            query_config = """
            SELECT 
                name,
                value_in_use,
                value,
                description
            FROM sys.configurations WITH(NOLOCK)
            WHERE name IN (
                'xp_cmdshell',
                'Ole Automation Procedures',
                'Ad Hoc Distributed Queries',
                'SQL Mail XPs',
                'Database Mail XPs',
                'Agent XPs',
                'SMO and DMO XPs',
                'Web Assistant Procedures',
                'remote access',
                'remote admin connections'
            )
            ORDER BY name
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_config)
            # Fix B+ 2026-06-09: surfacar o erro REAL em vez de saltar em silencio.
            if not result.get('success'):
                checks.append(_make_unknown_check('config', result.get('error') or 'query devolveu success=False'))
                return checks
            if result.get('success'):
                configs = {row.get('name'): row for row in result.get('rows', [])}
                
                # xp_cmdshell
                xp_cmdshell = configs.get('xp_cmdshell', {})
                if xp_cmdshell.get('value_in_use', 0) == 0:
                    checks.append(SecurityCheck(
                        check_id='config-001',
                        category='Configurações SQL Server',
                        title='xp_cmdshell',
                        description='xp_cmdshell está desabilitado',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Desabilitado',
                        expected_value='Desabilitado',
                        recommendation='Boa prática: xp_cmdshell deve estar desabilitado por padrão. Habilite apenas se necessário e com permissões restritas.',
                        reference='https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/xp-cmdshell-transact-sql'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='config-001',
                        category='Configurações SQL Server',
                        title='xp_cmdshell',
                        description='xp_cmdshell está habilitado',
                        status=SecurityStatus.FAIL.value,
                        severity=SecuritySeverity.CRITICAL.value,
                        current_value='Habilitado',
                        expected_value='Desabilitado',
                        recommendation='xp_cmdshell permite execução de comandos do sistema operacional. Desabilite se não for necessário. Se necessário, restrinja permissões e monitore seu uso.',
                        reference='https://learn.microsoft.com/sql/relational-databases/system-stored-procedures/xp-cmdshell-transact-sql'
                    ))
                
                # OLE Automation Procedures
                ole_auto = configs.get('Ole Automation Procedures', {})
                if ole_auto.get('value_in_use', 0) == 0:
                    checks.append(SecurityCheck(
                        check_id='config-002',
                        category='Configurações SQL Server',
                        title='OLE Automation Procedures',
                        description='OLE Automation Procedures está desabilitado',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Desabilitado',
                        expected_value='Desabilitado',
                        recommendation='Boa prática: OLE Automation deve estar desabilitado por padrão.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/ole-automation-procedures-server-configuration-option'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='config-002',
                        category='Configurações SQL Server',
                        title='OLE Automation Procedures',
                        description='OLE Automation Procedures está habilitado',
                        status=SecurityStatus.FAIL.value,
                        severity=SecuritySeverity.HIGH.value,
                        current_value='Habilitado',
                        expected_value='Desabilitado',
                        recommendation='OLE Automation pode ser um risco de segurança. Desabilite se não for necessário.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/ole-automation-procedures-server-configuration-option'
                    ))
                
                # Ad Hoc Distributed Queries
                ad_hoc = configs.get('Ad Hoc Distributed Queries', {})
                if ad_hoc.get('value_in_use', 0) == 0:
                    checks.append(SecurityCheck(
                        check_id='config-003',
                        category='Configurações SQL Server',
                        title='Ad Hoc Distributed Queries',
                        description='Ad Hoc Distributed Queries está desabilitado',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Desabilitado',
                        expected_value='Desabilitado',
                        recommendation='Boa prática: Ad Hoc Distributed Queries deve estar desabilitado por padrão.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/ad-hoc-distributed-queries-server-configuration-option'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='config-003',
                        category='Configurações SQL Server',
                        title='Ad Hoc Distributed Queries',
                        description='Ad Hoc Distributed Queries está habilitado',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value='Habilitado',
                        expected_value='Desabilitado',
                        recommendation='Ad Hoc Distributed Queries pode ser um risco de segurança. Desabilite se não for necessário.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/ad-hoc-distributed-queries-server-configuration-option'
                    ))
                
                # Remote Access
                remote_access = configs.get('remote access', {})
                if remote_access.get('value_in_use', 0) == 0:
                    checks.append(SecurityCheck(
                        check_id='config-004',
                        category='Configurações SQL Server',
                        title='Remote Access',
                        description='Remote Access está desabilitado',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value='Desabilitado',
                        expected_value='Desabilitado (a menos que necessário)',
                        recommendation='Boa prática: Remote Access deve estar desabilitado a menos que seja necessário para linked servers.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/remote-access-server-configuration-option'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='config-004',
                        category='Configurações SQL Server',
                        title='Remote Access',
                        description='Remote Access está habilitado',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value='Habilitado',
                        expected_value='Desabilitado (a menos que necessário)',
                        recommendation='Remote Access permite conexões remotas. Desabilite se não for necessário para linked servers.',
                        reference='https://learn.microsoft.com/sql/database-engine/configure-windows/remote-access-server-configuration-option'
                    ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar configurações: {e}")
            checks.append(SecurityCheck(
                check_id='config-error',
                category='Configurações SQL Server',
                title='Erro na Verificação',
                description=f'Erro ao verificar configurações: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks
    
    async def _check_encryption(self, server_id: str) -> List[SecurityCheck]:
        """Verifica configurações de criptografia"""
        checks = []
        
        try:
            # Verificar se TDE está habilitado (já temos essa query em queries.py)
            query_tde = """
            SELECT 
                d.name AS database_name,
                d.is_encrypted,
                d.encryption_state_desc
            FROM sys.databases d WITH(NOLOCK)
            WHERE d.database_id > 4
                AND d.state = 0
            ORDER BY d.name
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_tde)
            if result.get('success'):
                databases = result.get('rows', [])
                encrypted = [d for d in databases if d.get('is_encrypted', 0) == 1]
                not_encrypted = [d for d in databases if d.get('is_encrypted', 0) == 0]
                
                if len(encrypted) == len(databases):
                    checks.append(SecurityCheck(
                        check_id='encrypt-001',
                        category='Criptografia',
                        title='TDE (Transparent Data Encryption)',
                        description='Todos os databases estão criptografados com TDE',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value=f'{len(encrypted)}/{len(databases)} databases criptografados',
                        expected_value='Todos os databases críticos criptografados',
                        recommendation='Excelente: TDE protege dados em repouso. Certifique-se de que os certificados estão sendo backupados adequadamente.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/encryption/transparent-data-encryption'
                    ))
                elif len(encrypted) > 0:
                    checks.append(SecurityCheck(
                        check_id='encrypt-001',
                        category='Criptografia',
                        title='TDE (Transparent Data Encryption)',
                        description=f'Apenas {len(encrypted)} de {len(databases)} databases estão criptografados',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value=f'{len(encrypted)}/{len(databases)} databases criptografados',
                        expected_value='Todos os databases críticos criptografados',
                        recommendation='Recomenda-se habilitar TDE para todos os databases que contêm dados sensíveis. TDE protege dados em repouso.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/encryption/transparent-data-encryption',
                        details={'not_encrypted': [d.get('database_name') for d in not_encrypted[:10]]}
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='encrypt-001',
                        category='Criptografia',
                        title='TDE (Transparent Data Encryption)',
                        description='Nenhum database está criptografado com TDE',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.HIGH.value,
                        current_value='0 databases criptografados',
                        expected_value='Todos os databases críticos criptografados',
                        recommendation='Recomenda-se habilitar TDE para databases que contêm dados sensíveis. TDE protege dados em repouso sem requerer mudanças nas aplicações.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/encryption/transparent-data-encryption'
                    ))
            
            # Verificar se conexões usam SSL/TLS
            query_ssl = """
            SELECT 
                CASE 
                    WHEN net_transport = 'TCP' AND encrypt_option = 'TRUE' THEN 'Criptografado'
                    ELSE 'Não criptografado'
                END AS connection_encryption,
                COUNT(*) AS connection_count
            FROM sys.dm_exec_connections WITH(NOLOCK)
            WHERE session_id > 50
            GROUP BY 
                CASE 
                    WHEN net_transport = 'TCP' AND encrypt_option = 'TRUE' THEN 'Criptografado'
                    ELSE 'Não criptografado'
                END
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_ssl)
            if result.get('success'):
                connections = result.get('rows', [])
                encrypted_conns = next((c for c in connections if c.get('connection_encryption') == 'Criptografado'), {}).get('connection_count', 0)
                total_conns = sum(c.get('connection_count', 0) for c in connections)
                
                if total_conns > 0:
                    pct_encrypted = (encrypted_conns / total_conns) * 100
                    if pct_encrypted >= 90:
                        checks.append(SecurityCheck(
                            check_id='encrypt-002',
                            category='Criptografia',
                            title='Conexões Criptografadas',
                            description=f'{pct_encrypted:.1f}% das conexões estão criptografadas',
                            status=SecurityStatus.PASS.value,
                            severity=SecuritySeverity.INFO.value,
                            current_value=f'{pct_encrypted:.1f}% criptografadas',
                            expected_value='100% ou próximo',
                            recommendation='Boa prática: conexões devem usar SSL/TLS para proteger dados em trânsito.',
                            reference='https://learn.microsoft.com/sql/database-engine/configure-windows/enable-encrypted-connections-to-the-database-engine'
                        ))
                    else:
                        checks.append(SecurityCheck(
                            check_id='encrypt-002',
                            category='Criptografia',
                            title='Conexões Criptografadas',
                            description=f'Apenas {pct_encrypted:.1f}% das conexões estão criptografadas',
                            status=SecurityStatus.WARNING.value,
                            severity=SecuritySeverity.MEDIUM.value,
                            current_value=f'{pct_encrypted:.1f}% criptografadas',
                            expected_value='100% ou próximo',
                            recommendation='Recomenda-se configurar SQL Server para forçar conexões criptografadas (SSL/TLS) para proteger dados em trânsito.',
                            reference='https://learn.microsoft.com/sql/database-engine/configure-windows/enable-encrypted-connections-to-the-database-engine'
                        ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar criptografia: {e}")
            checks.append(SecurityCheck(
                check_id='encrypt-error',
                category='Criptografia',
                title='Erro na Verificação',
                description=f'Erro ao verificar criptografia: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks
    
    async def _check_auditing(self, server_id: str) -> List[SecurityCheck]:
        """Verifica configurações de auditoria"""
        checks = []
        
        try:
            # Verificar se Server Audit está habilitado
            query_audit = """
            SELECT 
                name,
                is_state_enabled,
                on_failure_desc,
                create_date
            FROM sys.server_audits WITH(NOLOCK)
            WHERE is_state_enabled = 1
            ORDER BY create_date DESC
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_audit)
            if result.get('success'):
                audits = result.get('rows', [])
                
                if len(audits) > 0:
                    checks.append(SecurityCheck(
                        check_id='audit-001',
                        category='Auditoria',
                        title='Server Audit',
                        description=f'{len(audits)} Server Audit(s) habilitado(s)',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value=f'{len(audits)} audit(s) habilitado(s)',
                        expected_value='Pelo menos 1 Server Audit habilitado',
                        recommendation='Boa prática: Server Audit deve estar habilitado para rastrear atividades de segurança e compliance.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/auditing/sql-server-audit-database-engine',
                        details={'audits': [a.get('name') for a in audits[:5]]}
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='audit-001',
                        category='Auditoria',
                        title='Server Audit',
                        description='Nenhum Server Audit está habilitado',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.MEDIUM.value,
                        current_value='0 audits habilitados',
                        expected_value='Pelo menos 1 Server Audit habilitado',
                        recommendation='Recomenda-se habilitar Server Audit para rastrear atividades de segurança, especialmente para compliance e detecção de atividades suspeitas.',
                        reference='https://learn.microsoft.com/sql/relational-databases/security/auditing/sql-server-audit-database-engine'
                    ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar auditoria: {e}")
            checks.append(SecurityCheck(
                check_id='audit-error',
                category='Auditoria',
                title='Erro na Verificação',
                description=f'Erro ao verificar auditoria: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks
    
    async def _check_version(self, server_id: str) -> List[SecurityCheck]:
        """Verifica versão do SQL Server"""
        checks = []
        
        try:
            query_version = """
            SELECT 
                @@VERSION AS version_string,
                SERVERPROPERTY('ProductVersion') AS product_version,
                SERVERPROPERTY('ProductLevel') AS product_level,
                SERVERPROPERTY('Edition') AS edition,
                SERVERPROPERTY('ProductUpdateLevel') AS update_level
            """
            
            result = await self.sql_monitoring.execute_query(server_id, query_version)
            if result.get('success') and result.get('rows'):
                row = result['rows'][0]
                version_string = row.get('version_string', '')
                product_level = row.get('product_level', '')
                product_version = row.get('product_version', '')
                
                # Extrair versão principal (ex: 15.0.2000.5 -> 15)
                major_version = None
                if product_version:
                    try:
                        major_version = int(product_version.split('.')[0])
                    except (ValueError, TypeError):
                        pass

                # Verificar se é versão antiga (SQL Server 2014 ou anterior)
                if major_version and major_version < 13:  # SQL Server 2016 é versão 13
                    checks.append(SecurityCheck(
                        check_id='version-001',
                        category='Versão',
                        title='Versão do SQL Server',
                        description=f'SQL Server versão {major_version} detectada (versão antiga)',
                        status=SecurityStatus.WARNING.value,
                        severity=SecuritySeverity.HIGH.value,
                        current_value=version_string[:100] if version_string else 'Unknown',
                        expected_value='Versão suportada com patches de segurança',
                        recommendation='Versões antigas do SQL Server podem não receber mais patches de segurança. Recomenda-se planejar upgrade para uma versão suportada.',
                        reference='https://learn.microsoft.com/sql/sql-server/end-of-support/sql-server-end-of-support-overview'
                    ))
                else:
                    checks.append(SecurityCheck(
                        check_id='version-001',
                        category='Versão',
                        title='Versão do SQL Server',
                        description=f'SQL Server versão {major_version if major_version else "Unknown"} detectada',
                        status=SecurityStatus.PASS.value,
                        severity=SecuritySeverity.INFO.value,
                        current_value=version_string[:100] if version_string else 'Unknown',
                        expected_value='Versão suportada com patches de segurança',
                        recommendation='Certifique-se de que está aplicando patches de segurança regularmente. Verifique o ProductLevel para garantir que está na versão mais recente do service pack.',
                        reference='https://learn.microsoft.com/sql/database-engine/install-windows/latest-updates-for-microsoft-sql-server'
                    ))
                
        except Exception as e:
            logger.error(f"Erro ao verificar versão: {e}")
            checks.append(SecurityCheck(
                check_id='version-error',
                category='Versão',
                title='Erro na Verificação',
                description=f'Erro ao verificar versão: {str(e)}',
                status=SecurityStatus.UNKNOWN.value,
                severity=SecuritySeverity.INFO.value
            ))
        
        return checks

