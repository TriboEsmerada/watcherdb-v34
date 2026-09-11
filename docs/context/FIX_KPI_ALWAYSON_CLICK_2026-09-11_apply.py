# -*- coding: utf-8 -*-
"""FIX 2026-09-11 -- modal do KPI "DB Always On - Unhealthy": clicar na linha dava
alert 'AG "SQLHDSPRD405\\I01" nao foi encontrado na configuracao'.

Causa: desde a regra unica TC-011 (2026-09-11, outra sessao) as linhas da modal passam a
INSTANCIA ao clique (instanceName = Instance, ~38491), mas selectInstanceFromModal (~48876)
continua a tratar TODO o valor de kpiType 'always-on' como NOME DE AG e chama
/api/alwayson/instance-by-ag/{valor}. O resolvedor procura em alwayson_inventory.json e
sql_servers.json (fontes legadas; o inventario vivo esta na BD desde E6) -> 404 -> alert
com a instancia rotulada como AG. Duas pontas do mesmo fluxo mudaram em datas diferentes.

Fix (so portal): no ramo 'always-on', se o valor ja e' uma instancia (existe em allServers
ou termina em _I<n>) salta-se o resolvedor de AG; so' nomes de AG/GUID vao ao resolvedor; e
quando o resolvedor falha, em vez de alert + fechar, regista no debug e cai no lookup
generico, que ja tem a sua propria mensagem se o servidor for mesmo desconhecido.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/FIX_KPI_ALWAYSON_CLICK_2026-09-11_apply.py --check
  py docs/context/FIX_KPI_ALWAYSON_CLICK_2026-09-11_apply.py
  py -m pytest tests/unit/test_kpi_alwayson_click_20260911.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5 ; KPIs > High Availability > Always On unhealthy > clicar na linha
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "templates" / "watcherdb_portal.html"
TEST = ROOT / "tests" / "unit" / "test_kpi_alwayson_click_20260911.py"

OLD = """            if (kpiType === 'always-on') {
                try {
                    debugLog(`[DBG] Buscando instância no inventory para AG: ${instanceName}`, 'info');
                    const response = await fetch(`/api/alwayson/instance-by-ag/${encodeURIComponent(instanceName)}`);

                    // Verificar se a resposta é OK
                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ error: 'Erro desconhecido' }));
                        debugLog(`[DBG] Erro HTTP ${response.status}: ${errorData.error || 'N/A'}`, 'warning');
                        alert(`AG "${instanceName}" não foi encontrado na configuração.\\n\\n` +
                              `Erro: ${errorData.error || 'AG não configurado'}\\n\\n` +
                              `Sugestão: ${errorData.suggestion || 'Verifique se o AG está configurado no alwayson_inventory.json ou sql_servers.json'}`);
                        closeInstancesModal();
                        return;
                    }

                    const result = await response.json();

                    if (result.success && result.server_id) {
                        debugLog(`? Instância encontrada no inventory: ${result.server_id} (${result.server}\\\\${result.instance || 'DEFAULT'})`, 'success');
                        debugLog(`[DBG] Source: ${result.source || 'unknown'}`, 'info');
                        // Usar o server_id encontrado no inventory
                        resolvedServerId = result.server_id;
                        instanceName = result.server_id;
                    } else {
                        debugLog(`[DBG] AG não encontrado no inventory: ${result.error || 'N/A'}`, 'warning');
                        alert(`AG "${instanceName}" não foi encontrado na configuração.\\n\\n` +
                              `Erro: ${result.error || 'AG não configurado'}\\n\\n` +
                              `Sugestão: ${result.suggestion || 'Verifique se o AG está configurado no alwayson_inventory.json ou sql_servers.json'}`);
                        closeInstancesModal();
                        return;
                    }
                } catch (error) {
                    debugLog(`[DBG] Erro ao buscar instância no inventory: ${error.message}`, 'error');
                    alert(`Erro ao buscar instância para o AG "${instanceName}":\\n${error.message}\\n\\nTente buscar manualmente na barra de pesquisa.`);
                    closeInstancesModal();
                    return;
                }
            }
"""

NEW = """            if (kpiType === 'always-on') {
                // 2026-09-11: desde a regra unica TC-011 as linhas desta modal passam a INSTANCIA
                // (ex.: SQLHDSPRD405_I01), nao o nome do AG. So' se pergunta ao resolvedor de AG
                // quando o valor NAO e' uma instancia conhecida; e se o resolvedor falhar, cai-se no
                // lookup generico abaixo (que ja' explica quando o servidor e' mesmo desconhecido),
                // em vez de um alert que chamava "AG" a uma instancia.
                const _aoNorm = String(instanceName).replace(/\\\\\\\\/g, '\\\\').replace(/\\\\/g, '_').split('.')[0].toUpperCase();
                const _aoKnown = Array.isArray(allServers) && allServers.some(s => String(s.server_id || s.id || '').replace(/\\\\/g, '_').split('.')[0].toUpperCase() === _aoNorm);
                const _aoLooksInstance = _aoKnown || /_I\\d+$/i.test(_aoNorm);
                if (_aoLooksInstance) {
                    debugLog(`[DBG] always-on: "${instanceName}" ja' e' instancia (conhecida=${_aoKnown}); resolvedor de AG dispensado`, 'info');
                } else {
                    try {
                        debugLog(`[DBG] Buscando instância no inventory para AG: ${instanceName}`, 'info');
                        const response = await fetch(`/api/alwayson/instance-by-ag/${encodeURIComponent(instanceName)}`);
                        const result = response.ok ? await response.json().catch(() => ({})) : {};
                        if (result.success && result.server_id) {
                            debugLog(`? Instância encontrada no inventory: ${result.server_id} (${result.server}\\\\\\\\${result.instance || 'DEFAULT'})`, 'success');
                            resolvedServerId = result.server_id;
                            instanceName = result.server_id;
                        } else {
                            debugLog(`[DBG] resolvedor de AG sem resposta util (HTTP ${response.status}); segue o lookup generico com "${instanceName}"`, 'warning');
                        }
                    } catch (error) {
                        debugLog(`[DBG] resolvedor de AG falhou (${error.message}); segue o lookup generico`, 'warning');
                    }
                }
            }
"""

TEST_SRC = '''"""
2026-09-11 -- modal KPI Always On: clicar na linha (instancia) nao pode ir ao resolvedor de AG.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates" / "watcherdb_portal.html").read_text(encoding="utf-8")


def test_alwayson_click_skips_ag_resolver_for_instances():
    assert "const _aoLooksInstance = _aoKnown || /_I\\\\d+$/i.test(_aoNorm);" in PORTAL
    assert "resolvedor de AG dispensado" in PORTAL


def test_alwayson_click_never_alerts_ag_not_found():
    branch = PORTAL.split("if (kpiType === 'always-on') {\\n                // 2026-09-11", 1)[1].split("// Remover domínio do nome", 1)[0]
    assert "alert(" not in branch and "closeInstancesModal();" not in branch
'''


def main(argv):
    check_only = "--check" in argv
    raw = PORTAL.read_bytes().decode("utf-8"); eol = "\r\n" if "\r\n" in raw else "\n"
    old, new = OLD.replace("\n", eol), NEW.replace("\n", eol)
    if "resolvedor de AG dispensado" in raw:
        print("[ABORT] ja aplicado"); return 1
    n = raw.count(old)
    if n != 1:
        print(f"[ABORT] anchor esperado 1x, encontrado {n}x -- nada escrito"); return 1
    print("[ok] portal: ramo always-on de selectInstanceFromModal (1x)")
    if check_only:
        print("--check OK. Nada escrito."); return 0
    PORTAL.write_bytes(raw.replace(old, new).encode("utf-8")); print("[write] templates/watcherdb_portal.html")
    TEST.write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {TEST.relative_to(ROOT)}")
    print("\\nAplicado. Corre: py -m pytest tests/unit/test_kpi_alwayson_click_20260911.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
