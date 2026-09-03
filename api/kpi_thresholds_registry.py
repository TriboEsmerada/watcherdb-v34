"""
Registry central de thresholds de KPI — FONTE UNICA DA VERDADE.
================================================================

Fase 0 da wave "thresholds configuraveis pelo cliente"
(docs/context/DESIGN_THRESHOLDS_CLIENTE_2026-08-04.md; painel de
2026-08-04: challenger + watcherdb-v1-intel-specialist +
v33-feature-matrix-checker).

Motivo: os thresholds viviam hardcoded em 5 camadas (backend Python,
WHERE de queries, views SQL, colector V1, frontend) e o drift ja tinha
produzido um manual de cliente com valores errados. Este modulo passa a
ser a fonte para TODAS as camadas Python do V3.3; as camadas que nao
consegue alimentar directamente (views SQL, colector V1, frontend
hardcoded) tem aqui o valor ESPELHADO com `source` a dizer onde vive a
definicao real — mudar um espelho AQUI nao muda o comportamento; e' um
inventario anti-drift ate a camada respectiva ser migrada.

Regras:
- `source: 'backend'`  -> o codigo V3.3 LE daqui; mudar aqui muda o produto.
- `source: 'view:...'` / `'collector:...'` -> ESPELHO informativo; a
  definicao real vive no objecto indicado. Testes anti-drift comparam.
- `configurable_f1`: candidato a override de cliente na Fase 1 (gated —
  ver design doc). Lista fechada: nada "meio-configuravel".

NAO adicionar aqui logica de override de cliente (tabela
WDB_KPI_THRESHOLDS) sem o gate da Fase 1 aberto pelo owner.
"""

REGISTRY_VERSION = "2026-08-13.f15"

THRESHOLDS = {
    # ---- fonte: backend (o codigo le daqui) --------------------------------
    "tempdb_usage": {
        "label": "TempDB — utilizacao",
        "warning": 60, "critical": 80, "unit": "%",
        "source": "backend",
        "configurable_f1": True,
        "note": ("DRIFT CONHECIDO (sweep 2026-08-04, FIND-20260804-103): a "
                 "coluna Status da KPI_MSSQL_TEMPDB_USAGE_AGG_VIEW usa "
                 "70/85/95 — duas verdades para o mesmo KPI ate a view ser "
                 "reconciliada; o card/modal V3.3 usam ESTES valores (60/80)"),
        "surfaces": ["card Saude do Disco", "modal tempdb-status"],
    },
    "disk_latency": {
        "label": "Latencia de disco (read/write)",
        "warning": 20, "critical": 50, "unit": "ms",
        "source": "backend",
        "configurable_f1": True,
        "note": ("usado tambem no WHERE de fetch (dashboard e modal) — "
                 "qualquer mudanca via registry cobre o WHERE por f-string; "
                 "o colector V1 (os_performance.py latency_ms_*) espelha "
                 "estes valores para a Severity persistida"),
        "surfaces": ["cards Espaco em Disco + Saude do Disco",
                     "modal disk-latency-critical/warning"],
    },
    "long_locks": {
        "label": "Locks longos (duracao)",
        "warning": 60, "critical": 600, "unit": "s",
        "source": "backend",
        "configurable_f1": True,
        "surfaces": ["lock_count no dashboard"],
    },
    "cpu_critical": {
        "label": "CPU critico (instancia)",
        "warning": None, "critical": 95, "unit": "%",
        "source": "backend",
        "configurable_f1": True,
        "note": ("o card usa Processor_Pct >= critical OR Severity do "
                 "colector (que marca warning a 80 — espelho em "
                 "collector:os_performance.py)"),
        "surfaces": ["card Performance", "modal cpu-critical"],
    },
    "backup_delay_full": {
        "label": "Backup FULL em atraso",
        "warning": 120, "critical": 168, "unit": "h",
        "source": "backend",
        "configurable_f1": True,
        "surfaces": ["card Backups (Em atraso critico/aviso)", "modal backup-delayed",
                     "Resumo Executivo + Por Categoria (delayed_critical -> criticos, 2026-08-06)"],
    },
    "backup_delay_diff": {
        "label": "Backup DIFF em atraso",
        "warning": 24, "critical": 30, "unit": "h",
        "source": "backend",
        "configurable_f1": True,
        "surfaces": ["card Backups (Em atraso critico/aviso)", "modal backup-delayed",
                     "Resumo Executivo + Por Categoria (delayed_critical -> criticos, 2026-08-06)"],
    },
    "backup_delay_log": {
        "label": "Backup LOG em atraso",
        "warning": 1, "critical": 2, "unit": "h",
        "source": "backend",
        "configurable_f1": True,
        "surfaces": ["card Backups (Em atraso critico/aviso)", "modal backup-delayed",
                     "Resumo Executivo + Por Categoria (delayed_critical -> criticos, 2026-08-06)"],
    },

    # ---- espelhos (definicao real vive na camada indicada) ------------------
    "processes_runnable": {
        "label": "Processos a espera de CPU (runnable)",
        "warning": 20, "critical": 50, "unit": "processos",
        "source": "backend",
        "configurable_f1": True,
        "note": ("Fase 1.5 lote 3 (2026-08-13): WHERE dinamico sobre "
                 "Runnable_Count (raw da AGG_VIEW) + State reclassificado no "
                 "backend, comparacao estrita > como a view. O State da view "
                 "mantem-se para Pro/V6 — handoff: migrar read-path no mesmo "
                 "lote senao as edicoes divergem com override activo"),
        "surfaces": ["card Performance (Instancias c/ processos em alarme)",
                     "modal processes-alarm"],
    },
    "integrity_checkdb_age": {
        "label": "CHECKDB antigo (P4)",
        "warning": 30, "critical": None, "unit": "dias",
        "source": "backend",
        "configurable_f1": True,
        "note": ("Fase 1.5 lote 3 (2026-08-13): fronteira P4/P5 recalculada "
                 "no backend sobre Days_Since_CheckDB (raw da VERDICT_VIEW); "
                 "so o warning (dias) e' o cutoff — critical N/A. P1/P3 e "
                 "higiene continuam a vir da view. Verdict da view mantem-se "
                 "para Pro/V6 — handoff: migrar read-path no mesmo lote"),
        "surfaces": ["card Integridade (CHECKDB antigo)", "modal integrity-p4"],
    },
    "memory_critical": {
        "label": "Memoria critica (tendencia 30 min)",
        "warning": None, "critical": None, "unit": "severity",
        "source": "collector:os_performance.py",
        "configurable_f1": False,
        "note": "Severity calculada e persistida pelo colector V1",
        "surfaces": ["card Performance", "modal memory-critical"],
    },
    "disk_space_drive": {
        "label": "Espaco em disco por drive (% livre)",
        "warning": None, "critical": None, "unit": "% livre, por tiers",
        "source": "view:KPI_MSSQL_DISK_USAGE_AGG_VIEW",
        "configurable_f1": False,
        "note": ("tiers de Percent_Free confirmados no sweep 2026-08-04: "
                 "C: normal >=25; restantes por escaloes 20/15/10 conforme o "
                 "tamanho do drive — regra por-drive, nao um par unico"),
        "surfaces": ["card Espaco em Disco"],
    },
    "tlog_usage": {
        "label": "Transaction log — utilizacao",
        "warning": 85, "critical": 95, "unit": "%",
        "source": "backend",
        "configurable_f1": True,
        "note": ("Fase 1.5 lote 3 (2026-08-13): o V3.3 le a "
                 "KPI_MSSQL_TLOG_USAGE_ACTIVE via _th (a AGG_VIEW so expoe "
                 "contagens ja classificadas a 85/95 e continua para Pro/V6; "
                 "a DET_VIEW mantem Status proprio — V3.3 nao a consome). "
                 "2026-09-02: classificacao partilhada card+modal em "
                 "api/routers/intelligence/tlog_usage_classes.py (por BASE; "
                 "o card conta instancias, o modal lista bases). Handoff V6: "
                 "migrar read-path no mesmo lote"),
        "surfaces": ["card Filegroups & Transaction Log",
                     "modal transaction-logs-critical/-warning (por base, 02/09)"],
    },
    "tlog_diagnosis": {
        "label": "Diagnostico de transaction log (drill por base)",
        "warning": None, "critical": None, "unit": "regras",
        "source": "backend",
        "configurable_f1": False,
        "note": ("2026-09-02: constantes do motor de regras do drill-down "
                 "(api/routers/queries/tlog_diagnosis.py) — transacao aberta "
                 "15/120 min; VLFs > 300; runway (margem no volume / log gerado "
                 "por dia, media 7d) 2/7 dias; log vs alvo 3x/10x (alvo = 2x o "
                 "maior backup de log em 30d, piso 512 MB, senao 10% dos dados); "
                 "growth ruim = % ou < 64 MB; margem < 1 GB; >= 10 autogrows "
                 "desde o arranque. % usado e atraso do backup de log vem de "
                 "tlog_usage e backup_delay_log (configuraveis)."),
        "surfaces": ["modal Diagnostico de Transaction Log (drill por base)"],
    },
    # Fase 1.5 (2026-08-13, painel v1-intel GO-com-condicoes + challenger):
    # filegroup_usage deixou de ser espelho — as queries embutidas passaram
    # a ler o registry+overrides via _th(). Modelo por tipo de crescimento
    # 27/07 mantido: dois KPIs para o mesmo card (precedente: backup_*).
    "filegroup_free_pct": {
        "label": "Filegroups — % livre efectivo (limitados)",
        "warning": 5, "critical": 2, "unit": "% livre",
        "source": "backend",
        "configurable_f1": True,
        # menor=pior: warning (5) > critical (2) numericamente. O router
        # valida a direccao com esta flag (default True nos restantes KPIs).
        "higher_is_worse": False,
        # Attention (5-10% livre / Percent_Used>90) fica FIXO nesta fase: o
        # schema partilhado so tem Warning/Critical (ALTER = veto V1). O cap
        # warning<=10 impede a banda Warning de engolir a Attention e mantem
        # validos os pre-filtros WHERE estaticos (Percent_Used>80 no card,
        # >90 no modal) sem SQL dinamico nesse ramo.
        "warning_cap": 10,
        "note": ("Attention fixo (<10% livre) nesta fase; "
                 "views KPI_MSSQL_FG_USAGE_*_VIEW continuam sem consumidor "
                 "vivo (re-verificado 2026-08-13)"),
        "surfaces": ["card Filegroups & Transaction Log",
                     "modal filegroup-usage-critical/warning"],
    },
    "filegroup_unlimited_free_gb": {
        "label": "Filegroups UNLIMITED — GB livres no volume",
        "warning": 10, "critical": 5, "unit": "GB livres",
        "source": "backend",
        "configurable_f1": True,
        "higher_is_worse": False,
        "note": ("modelo disk-bound 27/07: teto real e' o volume; "
                 "Vol_Free_MB=0 = sem visibilidade de coleta => WARNING fixo. "
                 "WHERE dinamico obrigatorio (nao ha folga acima do warning). "
                 "Fonte KPI_MSSQL_DATAFILES_STG verificada viva 2026-08-13 "
                 "(registada em KPI_STG_ACTIVE_TABLE na BD real; canonical "
                 "sem o registo — drift, finding aberto lado V1)"),
        "surfaces": ["card Filegroups & Transaction Log",
                     "modal filegroup-usage-critical/warning"],
    },
    "deadlocks_state": {
        "label": "Deadlocks 24h (State por instancia)",
        "warning": 10, "critical": 20, "unit": "deadlocks/24h",
        "source": "backend",
        "configurable_f1": True,
        "note": ("Fase 1.5 lote 2 (2026-08-13): classificacao movida da view "
                 "para o backend (_th sobre Deadlock_Count) — a coluna "
                 "State/Severity da KPI_MSSQL_DEADLOCKS_AGG_VIEW mantem-se "
                 "para consumidores Pro/V6 mas o V3.3 reclassifica; INFO "
                 "fixo >=1. Handoff V6: migrar o read-path no mesmo lote "
                 "senao as edicoes divergem com override activo"),
        "surfaces": ["card Bloqueios & Deadlocks", "modal deadlocks"],
    },
}


def get(kpi: str) -> dict:
    """Entry completa do registry (KeyError se kpi desconhecido — de proposito)."""
    return THRESHOLDS[kpi]


def value(kpi: str, level: str):
    """Valor de um nivel ('warning'|'critical') — atalho para f-strings de SQL."""
    return THRESHOLDS[kpi][level]


# Dict no formato historico do collect_backup_status (Wave D) — mesma
# estrutura, agora derivada da fonte unica.
BACKUP_DELAY_THRESHOLDS = {
    "FULL": {"warning_h": THRESHOLDS["backup_delay_full"]["warning"],
             "critical_h": THRESHOLDS["backup_delay_full"]["critical"]},
    "DIFF": {"warning_h": THRESHOLDS["backup_delay_diff"]["warning"],
             "critical_h": THRESHOLDS["backup_delay_diff"]["critical"]},
    "LOG":  {"warning_h": THRESHOLDS["backup_delay_log"]["warning"],
             "critical_h": THRESHOLDS["backup_delay_log"]["critical"]},
}


def registry_as_list() -> list:
    """Formato para o endpoint /thresholds e o ecra 'Thresholds em vigor'."""
    out = []
    for key, t in THRESHOLDS.items():
        out.append({
            "kpi": key,
            "label": t["label"],
            "warning": t["warning"],
            "critical": t["critical"],
            "unit": t["unit"],
            "source": t["source"],
            "is_mirror": not t["source"].startswith("backend"),
            "configurable_f1": t["configurable_f1"],
            "higher_is_worse": t.get("higher_is_worse", True),
            "warning_cap": t.get("warning_cap"),
            "note": t.get("note"),
        })
    return out
