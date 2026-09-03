"""
Teste múltiplos cenários de memória para validar a análise
"""
import requests
import json

base_url = "http://127.0.0.1:7000/api/monitoring/memory/os-snapshot/SQLHDSTST206_DEFAULT"

scenarios = [
    {
        "name": "🟢 Cenário Normal",
        "payload": {
            "available_mb": 3000,
            "pages_per_sec": 20,
            "page_reads_per_sec": 5
        }
    },
    {
        "name": "🟡 Cenário Atenção (Memória Baixa)",
        "payload": {
            "available_mb": 800,
            "pages_per_sec": 300,
            "page_reads_per_sec": 50
        }
    },
    {
        "name": "🟠 Cenário Warning (Paging Real)",
        "payload": {
            "available_mb": 400,
            "pages_per_sec": 2000,
            "page_reads_per_sec": 150
        }
    },
    {
        "name": "🔴 Cenário Crítico (Paging Severo + Memória Baixa)",
        "payload": {
            "available_mb": 150,
            "pages_per_sec": 8000,
            "page_reads_per_sec": 523
        }
    },
    {
        "name": "⚪ Cenário Spike de Soft Faults (Alto Pages/sec, Baixo Page Reads)",
        "payload": {
            "available_mb": 2500,
            "pages_per_sec": 12000,
            "page_reads_per_sec": 15
        }
    }
]

print("🧪 TESTANDO MÚLTIPLOS CENÁRIOS DE MEMÓRIA\n")
print("="*70)

for i, scenario in enumerate(scenarios, 1):
    print(f"\n{i}. {scenario['name']}")
    print("-" * 70)
    print(f"   Available MB: {scenario['payload']['available_mb']}")
    print(f"   Pages/sec: {scenario['payload']['pages_per_sec']}")
    print(f"   Page Reads/sec: {scenario['payload']['page_reads_per_sec']}")
    
    try:
        response = requests.post(base_url, json=scenario['payload'], timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            analysis = result.get("analysis", {})
            
            severity = analysis.get("severity", "unknown")
            severity_emoji = {
                "ok": "✅",
                "attention": "🟡",
                "warning": "🟠",
                "critical": "🔴"
            }.get(severity, "❓")
            
            print(f"   Resultado: {severity_emoji} {severity.upper()}")
            
            reasons = analysis.get("reasons", [])
            if reasons:
                print(f"   Motivos:")
                for reason in reasons:
                    print(f"      • {reason}")
        else:
            print(f"   ❌ Erro HTTP {response.status_code}: {response.text[:100]}")
            
    except Exception as e:
        print(f"   ❌ Erro: {str(e)}")
    
    print()

print("="*70)
print("✅ Teste concluído!")

