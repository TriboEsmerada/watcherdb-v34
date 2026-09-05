"""
Script de teste para o endpoint de análise de memória do SO
"""
import requests
import json

# URL do endpoint
url = "http://127.0.0.1:7000/api/monitoring/memory/os-snapshot/SQLHDSTST206_DEFAULT"

# Dados de teste - cenário de atenção (memória baixa + paging moderado)
payload = {
    "available_mb": 1200,
    "pages_per_sec": 400,
    "page_reads_per_sec": 80
}

print("🧪 Testando endpoint de análise de memória do SO...")
print(f"📡 URL: {url}")
print(f"📦 Payload: {json.dumps(payload, indent=2)}")
print("\n" + "="*60 + "\n")

try:
    response = requests.post(url, json=payload, timeout=10)
    
    print(f"✅ Status Code: {response.status_code}")
    print(f"📄 Response Headers: {dict(response.headers)}\n")
    
    if response.status_code == 200:
        result = response.json()
        print("🎯 RESULTADO DA ANÁLISE:")
        print("="*60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Extrair informações principais
        if "analysis" in result:
            analysis = result["analysis"]
            print("\n" + "="*60)
            print("📊 RESUMO DA ANÁLISE:")
            print(f"   Severity: {analysis.get('severity', 'N/A')}")
            print(f"   Available MB: {result.get('snapshot', {}).get('available_mb', 'N/A')} MB")
            print(f"   Pages/sec: {result.get('snapshot', {}).get('pages_per_sec', 'N/A')}")
            print(f"   Page Reads/sec: {result.get('snapshot', {}).get('page_reads_per_sec', 'N/A')}")
            
            if "reasons" in analysis:
                print(f"\n   Motivos ({len(analysis['reasons'])}):")
                for i, reason in enumerate(analysis["reasons"], 1):
                    print(f"   {i}. {reason}")
    else:
        print(f"❌ Erro: {response.status_code}")
        print(f"Resposta: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ ERRO: Não foi possível conectar ao servidor.")
    print("   Verifique se o servidor está rodando em http://127.0.0.1:7000")
    print("   Execute: python -m uvicorn watcherdb_main:app --reload --port 7000")
except requests.exceptions.Timeout:
    print("❌ ERRO: Timeout na requisição")
except Exception as e:
    print(f"❌ ERRO: {type(e).__name__}: {str(e)}")

