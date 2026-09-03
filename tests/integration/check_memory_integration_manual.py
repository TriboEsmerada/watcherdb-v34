"""
Teste de integração completa da análise de memória do SO
"""
import requests
import json

base_url = "http://127.0.0.1:7000"

# Testar endpoint de análise de memória completa
# Testando com SQLHDSPRD014\I01 conforme solicitado
server_id = "SQLHDSPRD014_I01"

print("🧪 TESTE DE INTEGRAÇÃO - Análise de Memória Completa")
print("="*70)
print(f"📡 Endpoint: GET {base_url}/api/monitoring/memory/server/{server_id}")
print()

try:
    response = requests.get(f"{base_url}/api/monitoring/memory/server/{server_id}", timeout=60)
    
    if response.status_code == 200:
        result = response.json()
        
        print("✅ Requisição bem-sucedida!")
        print(f"   Server ID: {result.get('server_id')}")
        print(f"   Server Name: {result.get('server_name')}")
        print()
        
        data = result.get('data', {})
        
        # Verificar se análise OS está presente
        os_analysis = data.get('os_memory_analysis')
        
        if os_analysis:
            print("🖥️  ANÁLISE DE MEMÓRIA DO SO:")
            print("-" * 70)
            
            if os_analysis.get('available'):
                counters = os_analysis.get('counters', {})
                analysis = os_analysis.get('analysis', {})
                
                print(f"   Available MB: {counters.get('available_mb', 'N/A')}")
                print(f"   Pages/sec: {counters.get('pages_per_sec', 'N/A')}")
                print(f"   Page Reads/sec: {counters.get('page_reads_per_sec', 'N/A')}")
                print()
                
                severity = analysis.get('severity', 'unknown')
                severity_emoji = {
                    "ok": "✅",
                    "attention": "🟡",
                    "warning": "🟠",
                    "critical": "🔴"
                }.get(severity, "❓")
                
                print(f"   Severity: {severity_emoji} {severity.upper()}")
                
                reasons = analysis.get('reasons', [])
                if reasons:
                    print(f"   Motivos:")
                    for reason in reasons:
                        print(f"      • {reason}")
            else:
                print(f"   ⚠️  {os_analysis.get('message', 'Não disponível')}")
        else:
            print("⚠️  Análise OS não presente na resposta")
        
        print()
        print("📊 ANÁLISE SQL SERVER:")
        print("-" * 70)
        print(f"   Physical RAM: {data.get('physical_ram_gb', 'N/A')} GB")
        print(f"   Max Server Memory: {data.get('max_server_memory_mb', 'N/A')} MB")
        print(f"   Memory Pressure: {data.get('memory_pressure_pct', 'N/A')}%")
        print(f"   Status: {data.get('memory_pressure_status', 'N/A')}")
        
        alerts = data.get('alerts', [])
        if alerts:
            print()
            print(f"🚨 ALERTAS ({len(alerts)}):")
            print("-" * 70)
            for alert in alerts:
                level = alert.get('level', 'info')
                emoji = {
                    'danger': '🔴',
                    'warning': '🟠',
                    'info': 'ℹ️',
                    'success': '✅'
                }.get(level, '⚪')
                print(f"   {emoji} [{level.upper()}] {alert.get('message', '')}")
        
    else:
        print(f"❌ Erro HTTP {response.status_code}")
        print(f"Resposta: {response.text[:200]}")
        
except requests.exceptions.ConnectionError:
    print("❌ ERRO: Não foi possível conectar ao servidor.")
    print("   Verifique se o servidor está rodando em http://127.0.0.1:7000")
except Exception as e:
    print(f"❌ ERRO: {type(e).__name__}: {str(e)}")

print()
print("="*70)

