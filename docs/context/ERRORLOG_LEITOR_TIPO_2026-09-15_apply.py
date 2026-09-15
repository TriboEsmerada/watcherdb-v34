# -*- coding: utf-8 -*-
"""Leitor do errorlog no V3.4 (2026-09-15) -- conta pelo tipo classificado, nao pela severidade. APLICAR ANTES DO B1b.

Porque: os dois leitores do cartao de errorlog (dashboard e drill) contam como critica qualquer linha com severidade
16 a 24. Hoje o recolhedor grava Severity sempre NULL, logo o cartao diz sempre 0 criticos (falso verde: medido no
instantaneo de 14/09). O B1b vai preencher Severity. Sem esta mudanca, o erro 33208 de auditoria sem acesso ao log de
seguranca (severidade 17, repetitivo, medido em pelo menos 6 instancias PRD) punha cerca de dez instancias a vermelho
de uma vez -- trocava um falso verde por um falso vermelho.

Regra nova, a mesma nos dois leitores (funcao errorlog_bucket em helpers.py):
  Log_Type Critical                           -> critico
  Log_Type Error, AvailabilityGroup, Lifecycle -> aviso
  Log_Type vazio (linhas antigas)              -> aviso, como hoje
  Security, Repetitive, Info                   -> nao entram no cartao (18456 e' sinal de seguranca, nao de motor;
                                                  parecer da persona DBA cliente no A3)
Compativel com os dados de hoje (Log_Type 'Error', Severity NULL): o cartao continua igual ate o B1b correr.

Uso (raiz do repo V3.4):
  py docs/context/ERRORLOG_LEITOR_TIPO_2026-09-15_apply.py --check
  py docs/context/ERRORLOG_LEITOR_TIPO_2026-09-15_apply.py
  py -m pytest tests/unit/test_errorlog_leitor_tipo_20260915.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "helpers": Path("api/routers/intelligence/helpers.py"),
    "kpis": Path("api/routers/intelligence_kpis.py"),
    "changelog": Path("docs/changelog/CHANGELOG.md"),
    "test": Path("tests/unit/test_errorlog_leitor_tipo_20260915.py"),
}
MARK = "def errorlog_bucket("

BUCKET_FN = '''# 2026-09-15 (antes do B1b): o recolhedor passa a classificar o errorlog (Log_Type) e a preencher Severity. Contar pela
# severidade punha o 33208 de auditoria (sev 17, repetitivo) a vermelho em cerca de dez instancias. Conta-se pelo tipo:
# Critical e' critico; Error, AvailabilityGroup e Lifecycle sao aviso; Security, Repetitive e Info nao entram no cartao.
# Linhas antigas (Log_Type 'Error', Severity NULL) continuam aviso, como antes.
ERRORLOG_CRITICAL_TYPES = frozenset({"CRITICAL"})
ERRORLOG_WARNING_TYPES = frozenset({"ERROR", "AVAILABILITYGROUP", "LIFECYCLE", ""})


def errorlog_bucket(row: Dict[str, Any]) -> Optional[str]:
    """'critical', 'warning' ou None quando a linha nao conta no cartao de errorlog."""
    tipo = str(row.get("Log_Type") or "").strip().upper()
    if tipo in ERRORLOG_CRITICAL_TYPES:
        return "critical"
    if tipo in ERRORLOG_WARNING_TYPES:
        return "warning"
    return None


'''

H_LOOP_OLD = """        for row in all_errors:
            instance = row.get('Instance', '')
            if not instance:
                continue

            if instance not in instance_errors:
"""
H_LOOP_NEW = """        for row in all_errors:
            instance = row.get('Instance', '')
            if not instance:
                continue
            bucket = errorlog_bucket(row)
            if bucket is None:
                continue

            if instance not in instance_errors:
"""
H_SEV_OLD = """            instance_errors[instance]['Error_Count'] += 1

            row_keys_upper = [k.upper() for k in row.keys()]
            severity = None
            for key in ['SEVERITY', 'SEVERITY_LEVEL', 'LEVEL', 'ERROR_LEVEL']:
                if key in row_keys_upper:
                    severity = str(row.get(key, '')).upper()
                    break

            if severity and severity in ['ERROR', 'CRITICAL', 'FATAL', '16', '17', '18', '19', '20', '21', '22', '23', '24']:
                instance_errors[instance]['Critical_Count'] += 1
            elif severity and severity in ['WARNING', 'WARN', '14', '15']:
                instance_errors[instance]['Warning_Count'] += 1
            else:
                instance_errors[instance]['Warning_Count'] += 1

"""
H_SEV_NEW = """            instance_errors[instance]['Error_Count'] += 1
            if bucket == 'critical':
                instance_errors[instance]['Critical_Count'] += 1
            else:
                instance_errors[instance]['Warning_Count'] += 1

"""

K_OLD = """            for row in all_errors:
                instance = row.get('Instance', '')
                if not instance:
                    continue

                if instance not in instance_errors:
                    instance_errors[instance] = {
                        'Instance': instance,
                        'Error_Count': 0,
                        'Critical_Count': 0,
                        'Warning_Count': 0,
                        'Last_Error_Date': None
                    }

                instance_errors[instance]['Error_Count'] += 1

                # Verificar severidade
                row_keys_upper = [k.upper() for k in row.keys()]
                severity = None
                for key in ['SEVERITY', 'SEVERITY_LEVEL', 'LEVEL', 'ERROR_LEVEL']:
                    if key in row_keys_upper:
                        severity = str(row.get(key, '')).upper()
                        break

                if severity and severity in ['ERROR', 'CRITICAL', 'FATAL', '16', '17', '18', '19', '20', '21', '22', '23', '24']:
                    instance_errors[instance]['Critical_Count'] += 1
                elif severity and severity in ['WARNING', 'WARN', '14', '15']:
                    instance_errors[instance]['Warning_Count'] += 1
                else:
                    instance_errors[instance]['Warning_Count'] += 1
"""
# no ficheiro, as linhas em branco deste bloco tem 16 espacos
K_OLD = K_OLD.replace("\n\n", "\n" + " " * 16 + "\n")
K_NEW = """            # 2026-09-15: mesma regra do cartao (helpers.errorlog_bucket): conta pelo tipo classificado, nao pela severidade
            from api.routers.intelligence.helpers import errorlog_bucket
            for row in all_errors:
                instance = row.get('Instance', '')
                if not instance:
                    continue
                bucket = errorlog_bucket(row)
                if bucket is None:
                    continue

                if instance not in instance_errors:
                    instance_errors[instance] = {
                        'Instance': instance,
                        'Error_Count': 0,
                        'Critical_Count': 0,
                        'Warning_Count': 0,
                        'Last_Error_Date': None
                    }

                instance_errors[instance]['Error_Count'] += 1
                if bucket == 'critical':
                    instance_errors[instance]['Critical_Count'] += 1
                else:
                    instance_errors[instance]['Warning_Count'] += 1
"""

CHANGELOG_EDIT = ("## [Unreleased]\n\n### Changed\n\n",
                  "## [Unreleased]\n\n### Changed\n\n"
                  "- **Cartão de errorlog conta pelo tipo classificado, não pela severidade** (15/09, preparação do B1b). O\n"
                  "  recolhedor vai passar a preencher a severidade; contar por ela punha o erro 33208 de auditoria\n"
                  "  (severidade 17, repetitivo) a vermelho em cerca de dez instâncias. Crítico passa a ser o tipo Critical;\n"
                  "  aviso são Error, AvailabilityGroup e Lifecycle; falhas de login e repetitivos não entram no cartão. Com\n"
                  "  os dados de hoje o cartão fica igual. [tier: Std]\n"
                  "\n", 1)

TEST_SRC = r'''"""
2026-09-15 -- leitor do errorlog conta pelo tipo classificado (preparacao do B1b).
"""
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPIS = (ROOT / "api" / "routers" / "intelligence_kpis.py").read_text(encoding="utf-8")


def test_bucket_por_tipo():
    from api.routers.intelligence.helpers import errorlog_bucket as b
    assert b({"Log_Type": "Critical", "Severity": 24}) == "critical"
    for t in ("Error", "AvailabilityGroup", "Lifecycle", "", None):
        assert b({"Log_Type": t}) == "warning", t
    for t in ("Security", "Repetitive", "Info"):
        assert b({"Log_Type": t, "Severity": 17}) is None, t
    # linha antiga do recolhedor: Log_Type 'Error' e Severity NULL, continua aviso
    assert b({"Log_Type": "Error", "Severity": None}) == "warning"


def test_cartao_do_dashboard_ignora_33208_e_18456_e_conta_critico_pelo_tipo(monkeypatch):
    from api.routers.intelligence import helpers as h
    linhas = [
        {"Instance": "A_I01", "Log_Date": None, "Log_Type": "Repetitive", "Severity": 17, "Error_Number": 33208},
        {"Instance": "B_I01", "Log_Date": None, "Log_Type": "Security", "Severity": 14, "Error_Number": 18456},
        {"Instance": "C_I01", "Log_Date": None, "Log_Type": "Critical", "Severity": 24, "Error_Number": 824},
        {"Instance": "D_I01", "Log_Date": None, "Log_Type": "Lifecycle", "Severity": None, "Error_Number": None},
        {"Instance": "E_I01", "Log_Date": None, "Log_Type": "Error", "Severity": None, "Error_Number": None},
    ]

    async def fake(query, raise_on_error=True):
        return [] if "TOP 1" in query else linhas

    monkeypatch.setattr(h, "execute_intelligence_query_async", fake)
    res = {"error_log": {}}
    asyncio.run(h.collect_error_log(res))
    assert res["error_log"]["critical_count"] == 1
    assert res["error_log"]["warning_count"] == 2
    assert {i["Instance"] for i in res["error_log"]["instances"]} == {"C_I01", "D_I01", "E_I01"}


def test_drill_usa_a_mesma_regra():
    bloco = KPIS[KPIS.index('elif kpi_type == "error-log":'):KPIS.index('elif kpi_type == "tempdb-status"')]
    assert "from api.routers.intelligence.helpers import errorlog_bucket" in bloco
    assert "'16', '17', '18'" not in bloco
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:90]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    helpers = src["helpers"].read_bytes().decode("utf-8")
    if MARK in helpers:
        print("[ABORT] ja aplicado"); return 1
    helpers = _apply(helpers, [("async def collect_error_log(results: Dict[str, Any]) -> None:\n",
                                BUCKET_FN + "async def collect_error_log(results: Dict[str, Any]) -> None:\n", 1),
                               (H_LOOP_OLD, H_LOOP_NEW, 1), (H_SEV_OLD, H_SEV_NEW, 1)], "helpers")
    kpis = _apply(src["kpis"].read_bytes().decode("utf-8"), [(K_OLD, K_NEW, 1)], "intelligence_kpis")
    chg = _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")
    for nome, txt in (("helpers", helpers), ("kpis", kpis), ("test", TEST_SRC)):
        compile(txt, nome, "exec")
    print("[ok] helpers 3 blocos, intelligence_kpis 1 bloco, changelog; tudo compila")
    if check:
        print("--check OK. Nada escrito."); return 0
    src["helpers"].write_bytes(helpers.encode("utf-8")); print(f"[write] {REL['helpers']}")
    src["kpis"].write_bytes(kpis.encode("utf-8")); print(f"[write] {REL['kpis']}")
    src["changelog"].write_bytes(chg.encode("utf-8")); print(f"[write] {REL['changelog']}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_errorlog_leitor_tipo_20260915.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
