"""
Teste rápido para SQLHDSPRD014_I01
"""
import requests
import json

base_url = "http://127.0.0.1:7000"
server_id = "SQLHDSPRD014_I01"

print("🧪 TESTE - SQLHDSPRD014\\I01")
print("="*70)
print(f"📡 GET {base_url}/api/monitoring/memory/server/{server_id}")
print()

try:
    response = requests.get(f"{base_url}/api/monitoring/memory/server/{server_id}", timeout=60)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("✅ SUCESSO!")
        print(f"Server: {result.get('server_name')}")
        
        data = result.get('data', {})
        print(f"\n📊 SQL Server:")
        print(f"   RAM: {data.get('physical_ram_gb', 'N/A')} GB")
        print(f"   Max Memory: {data.get('max_server_memory_mb', 'N/A')} MB")
        print(f"   Pressure: {data.get('memory_pressure_pct', 'N/A')}%")
        
        os_analysis = data.get('os_memory_analysis')
        if os_analysis:
            if os_analysis.get('available'):
                counters = os_analysis.get('counters', {})
                analysis = os_analysis.get('analysis', {})
                print(f"\n🖥️  OS Memory:")
                print(f"   Available: {counters.get('available_mb', 'N/A')} MB")
                print(f"   Pages/sec: {counters.get('pages_per_sec', 'N/A')}")
                print(f"   Page Reads/sec: {counters.get('page_reads_per_sec', 'N/A')}")
                print(f"   Severity: {analysis.get('severity', 'N/A')}")
            else:
                print(f"\n🖥️  OS Memory: {os_analysis.get('message', 'Não disponível')}")
    else:
        print(f"❌ ERRO {response.status_code}")
        print(f"Resposta: {response.text[:500]}")
        
except Exception as e:
    print(f"❌ ERRO: {e}")

print("\n" + "="*70)

