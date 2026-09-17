# -*- coding: utf-8 -*-
"""Ajuda "?" das modais de backup (FALHAS DE BACKUP, …) em quatro idiomas (2026-09-17).

CAPTURA DO OWNER: modal "DIFF Backup Failed" com o portal em ingles e a ajuda do "?" em portugues sem acentos
("FALHAS DE BACKUP ... PORQUE IMPORTA ... O QUE FAZER ..."). Origem: templates/watcherdb_portal.html ~38063,
`const BACKUP_KPI_INFO = {...}` (Wave R+7.T1, 25/05) -- cinco textos escritos a mao, consumidos em ~38174 pelo
title do icone. Mesma classe de falha do Collector Health e do cartao de Disk Latency.

O QUE MUDA:
 1. static/i18n/{pt,en,es}.json: grupo `kpi_info` com as 5 chaves (backup_failed, backup_log_failed, backup_delayed,
    backup_jobs_disabled, backup_no_checksum); pt em portugues europeu acentuado (AO90); pt-BR so' com o que difere.
 2. Portal: o consumidor passa a `_kpiT('kpi_info.' + chave, BACKUP_KPI_INFO[kpiType])` -- o dicionario antigo fica
    como recurso (nunca se mostra chave crua).
 NAO tratado aqui: o dicionario de ajuda do ecra de queries (~56240, 'multi_offenders' etc.) tem a mesma falha e e'
 maior; fica inventariado.

Uso (raiz do repo):
  py docs/context/KPI_INFO_I18N_2026-09-17_apply.py --check
  py docs/context/KPI_INFO_I18N_2026-09-17_apply.py
  py -m pytest tests/unit/test_kpi_info_i18n_20260917.py tests/unit/test_i18n_parity.py -q --no-cov
  Restart-Service WatcherDBWebServiceV34 ; Ctrl+F5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {"portal": Path("templates/watcherdb_portal.html"), "pt": Path("static/i18n/pt.json"), "en": Path("static/i18n/en.json"),
       "es": Path("static/i18n/es.json"), "ptbr": Path("static/i18n/pt-BR.json"), "changelog": Path("docs/changelog/CHANGELOG.md"),
       "test": Path("tests/unit/test_kpi_info_i18n_20260917.py")}
MARK = "_kpiT('kpi_info.'"

PT = {
    "backup_failed": (
        "FALHAS DE BACKUP\n\nJobs de backup (FULL, DIFF ou LOG) que falharam ou foram cancelados e que ainda NÃO foram corrigidos "
        "por uma execução posterior bem-sucedida do mesmo job.\n\nPORQUE IMPORTA: uma falha por corrigir significa que, neste "
        "momento, não existe cópia de recuperação válida para essa base de dados dentro da janela esperada.\n\nO QUE FAZER: abrir o "
        "Job History do SQL Server Agent na instância, identificar o motivo (disco cheio, permissões, destino inacessível) e voltar a "
        "executar o job.\n\nRECUPERADO: o número do cartão conta só as falhas NÃO RECUPERADAS (sem execução posterior com sucesso). "
        "Por omissão a lista mostra só essas; as já recuperadas não desaparecem em silêncio — use a ligação \"mostrar N "
        "recuperada(s)\" para as ver, com o selo verde \"Recuperado\" e a data.\n\nPRÓXIMA EXECUÇÃO: cada linha mostra quando o job "
        "volta a correr segundo o Agent (decisão: correr à mão agora ou esperar). \"Sem agendamento no Agent\" não é por si um "
        "problema — uma ferramenta externa de backup ou um agendador externo pode disparar o job de fora; veja a aba Backup da "
        "instância para a origem detetada e o próximo esperado pelo histórico.\n\nJANELA: falhas dos últimos 7 dias recolhidas pelo "
        "recolhedor; a aba Backup da instância mostra o estado atual de cada job (última execução) e as falhas das últimas 24 h ao "
        "vivo. Um job com cadência superior a 7 dias que continue partido reaparece no KPI \"Em atraso\".\n\nNão cobre falhas "
        "silenciosas (job reportado como sucesso mas o ficheiro não chegou ao destino externo — TSM/Commvault/Veeam)."),
    "backup_log_failed": (
        "FALHAS DE BACKUP DE LOG\n\nBackups do transaction log que falharam e ainda não foram corrigidos por uma execução posterior "
        "bem-sucedida do mesmo job.\n\nPORQUE IMPORTA: sem backup de log recente, o log de transações continua a crescer e o ponto de "
        "recuperação (RPO) fica cada vez mais distante do momento atual.\n\nRECUPERADO: o número do cartão conta só as falhas NÃO "
        "RECUPERADAS; por omissão a lista mostra só essas — a ligação \"mostrar N recuperada(s)\" revela as já recuperadas com o selo "
        "verde e a data.\n\nJANELA: falhas dos últimos 7 dias recolhidas pelo recolhedor.\n\nO QUE FAZER: verificar o Job History do "
        "SQL Server Agent. Se o job corre mas falha, confirmar o espaço no destino e o recovery model da base (tem de ser FULL ou "
        "BULK_LOGGED)."),
    "backup_delayed": (
        "BACKUPS EM ATRASO\n\nBases de dados sem backup dentro do prazo esperado (FULL: 7 dias, DIFF: 24 h, LOG: 2 h).\n\nPORQUE "
        "IMPORTA: é uma falha de RPO, não uma falha reportada — o job pode estar desativado, nunca ter corrido, ou o agendamento real "
        "ser diferente do assumido.\n\nO QUE FAZER: confirmar o agendamento real do job do SQL Agent para esta base de dados e "
        "comparar com a hora do último backup."),
    "backup_jobs_disabled": (
        "JOBS DE BACKUP DESATIVADOS\n\nJobs de backup que não vão correr: desativados (enabled=0), ou ativos mas com todos os "
        "agendamentos desligados.\n\nPORQUE IMPORTA: é normalmente sinal de uma pausa manual não documentada que ninguém reativou — a "
        "base de dados pode estar sem proteção de backup há semanas sem ninguém reparar. O agendamento desligado é o caso mais "
        "perigoso dos dois, porque o job aparece ativo.\n\nO QUE FAZER: confirmar com a equipa se foi intencional; se não foi, "
        "reativar o job ou o agendamento."),
    "backup_no_checksum": (
        "BACKUPS SEM CHECKSUM\n\nBases de dados com pelo menos 1 backup feito sem WITH CHECKSUM nos últimos 7 dias, ou marcado como "
        "danificado.\n\nPORQUE IMPORTA: sem checksum o SQL Server não valida as páginas durante o backup — uma corrupção silenciosa "
        "pode ser copiada sem aviso, e o RESTORE VERIFYONLY não a deteta. Só se descobre no restore, tarde.\n\nO QUE FAZER: ativar "
        "WITH CHECKSUM nos jobs de backup destas instâncias.\n\nCada linha = par único (instância + base de dados). Inclui FULL, DIFF "
        "e LOG."),
}
EN = {
    "backup_failed": (
        "BACKUP FAILURES\n\nBackup jobs (FULL, DIFF or LOG) that failed or were cancelled and have NOT yet been fixed by a later "
        "successful run of the same job.\n\nWHY IT MATTERS: an unfixed failure means that, right now, there is no valid recovery copy "
        "of that database within the expected window.\n\nWHAT TO DO: open the SQL Server Agent Job History on the instance, find the "
        "cause (disk full, permissions, unreachable destination) and re-run the job.\n\nRECOVERED: the card counts only NOT RECOVERED "
        "failures (no later successful run). By default the list shows only those; the recovered ones do not vanish silently — use "
        "the \"show N recovered\" link to see them, with the green \"Recovered\" badge and the date.\n\nNEXT RUN: each row shows when "
        "the Agent will run the job again (decision: run it by hand now or wait). \"No Agent schedule\" is not a problem by itself — "
        "an external backup tool or scheduler may trigger the job from outside; see the instance's Backup tab for the detected origin "
        "and the next run expected from history.\n\nWINDOW: failures from the last 7 days gathered by the collector; the instance's "
        "Backup tab shows each job's current state (last run) and the last 24 h of failures live. A job with a cadence longer than 7 "
        "days that stays broken reappears in the \"Delayed\" KPI.\n\nDoes not cover silent failures (job reported as success but the "
        "file never reached the external destination — TSM/Commvault/Veeam)."),
    "backup_log_failed": (
        "LOG BACKUP FAILURES\n\nTransaction log backups that failed and have not yet been fixed by a later successful run of the same "
        "job.\n\nWHY IT MATTERS: without a recent log backup the transaction log keeps growing and the recovery point (RPO) drifts "
        "further from now.\n\nRECOVERED: the card counts only NOT RECOVERED failures; by default the list shows only those — the "
        "\"show N recovered\" link reveals the recovered ones with the green badge and the date.\n\nWINDOW: failures from the last 7 "
        "days gathered by the collector.\n\nWHAT TO DO: check the SQL Server Agent Job History. If the job runs but fails, confirm "
        "free space at the destination and the database recovery model (must be FULL or BULK_LOGGED)."),
    "backup_delayed": (
        "DELAYED BACKUPS\n\nDatabases without a backup within the expected deadline (FULL: 7 days, DIFF: 24 h, LOG: 2 h).\n\nWHY IT "
        "MATTERS: this is an RPO gap, not a reported failure — the job may be disabled, may never have run, or the real schedule may "
        "differ from the assumed one.\n\nWHAT TO DO: confirm the real SQL Agent job schedule for this database and compare it with the "
        "time of the last backup."),
    "backup_jobs_disabled": (
        "DISABLED BACKUP JOBS\n\nBackup jobs that will not run: disabled (enabled=0), or enabled but with every schedule switched "
        "off.\n\nWHY IT MATTERS: usually the sign of an undocumented manual pause nobody re-enabled — the database may have been "
        "without backup protection for weeks with nobody noticing. The switched-off schedule is the more dangerous of the two, "
        "because the job looks enabled.\n\nWHAT TO DO: confirm with the team whether it was intentional; if not, re-enable the job or "
        "the schedule."),
    "backup_no_checksum": (
        "BACKUPS WITHOUT CHECKSUM\n\nDatabases with at least 1 backup taken without WITH CHECKSUM in the last 7 days, or marked as "
        "damaged.\n\nWHY IT MATTERS: without checksum SQL Server does not validate pages during the backup — silent corruption can be "
        "copied without warning, and RESTORE VERIFYONLY will not catch it. It is only discovered at restore time, too late.\n\nWHAT TO "
        "DO: enable WITH CHECKSUM in these instances' backup jobs.\n\nEach row = unique pair (instance + database). Includes FULL, DIFF "
        "and LOG."),
}
ES = {
    "backup_failed": (
        "FALLOS DE BACKUP\n\nJobs de backup (FULL, DIFF o LOG) que fallaron o fueron cancelados y que todavía NO han sido corregidos por "
        "una ejecución posterior exitosa del mismo job.\n\nPOR QUÉ IMPORTA: un fallo sin corregir significa que, en este momento, no "
        "existe una copia de recuperación válida de esa base de datos dentro de la ventana esperada.\n\nQUÉ HACER: abrir el Job History "
        "del SQL Server Agent en la instancia, identificar el motivo (disco lleno, permisos, destino inaccesible) y volver a ejecutar "
        "el job.\n\nRECUPERADO: el número de la tarjeta cuenta solo los fallos NO RECUPERADOS (sin ejecución posterior exitosa). Por "
        "defecto la lista muestra solo esos; los ya recuperados no desaparecen en silencio — use el enlace \"mostrar N recuperado(s)\" "
        "para verlos, con el sello verde \"Recuperado\" y la fecha.\n\nPRÓXIMA EJECUCIÓN: cada fila muestra cuándo el Agent volverá a "
        "ejecutar el job (decisión: ejecutarlo a mano ahora o esperar). \"Sin programación en el Agent\" no es un problema por sí "
        "mismo — una herramienta externa de backup o un programador externo puede disparar el job desde fuera; vea la pestaña Backup "
        "de la instancia para el origen detectado y la próxima ejecución esperada según el historial.\n\nVENTANA: fallos de los últimos "
        "7 días recogidos por el recolector; la pestaña Backup de la instancia muestra el estado actual de cada job (última ejecución) "
        "y los fallos de las últimas 24 h en vivo. Un job con cadencia superior a 7 días que siga roto reaparece en el KPI "
        "\"Retrasados\".\n\nNo cubre fallos silenciosos (job reportado como éxito pero el archivo nunca llegó al destino externo — "
        "TSM/Commvault/Veeam)."),
    "backup_log_failed": (
        "FALLOS DE BACKUP DE LOG\n\nBackups del transaction log que fallaron y todavía no han sido corregidos por una ejecución "
        "posterior exitosa del mismo job.\n\nPOR QUÉ IMPORTA: sin un backup de log reciente, el log de transacciones sigue creciendo y "
        "el punto de recuperación (RPO) se aleja cada vez más del momento actual.\n\nRECUPERADO: el número de la tarjeta cuenta solo los "
        "fallos NO RECUPERADOS; por defecto la lista muestra solo esos — el enlace \"mostrar N recuperado(s)\" revela los ya recuperados "
        "con el sello verde y la fecha.\n\nVENTANA: fallos de los últimos 7 días recogidos por el recolector.\n\nQUÉ HACER: revisar el "
        "Job History del SQL Server Agent. Si el job se ejecuta pero falla, confirmar el espacio en el destino y el recovery model de "
        "la base (debe ser FULL o BULK_LOGGED)."),
    "backup_delayed": (
        "BACKUPS RETRASADOS\n\nBases de datos sin backup dentro del plazo esperado (FULL: 7 días, DIFF: 24 h, LOG: 2 h).\n\nPOR QUÉ "
        "IMPORTA: es una brecha de RPO, no un fallo reportado — el job puede estar desactivado, no haberse ejecutado nunca, o la "
        "programación real ser distinta de la asumida.\n\nQUÉ HACER: confirmar la programación real del job del SQL Agent para esta "
        "base de datos y compararla con la hora del último backup."),
    "backup_jobs_disabled": (
        "JOBS DE BACKUP DESACTIVADOS\n\nJobs de backup que no se van a ejecutar: desactivados (enabled=0), o activos pero con todas las "
        "programaciones apagadas.\n\nPOR QUÉ IMPORTA: normalmente es señal de una pausa manual no documentada que nadie reactivó — la "
        "base de datos puede llevar semanas sin protección de backup sin que nadie lo note. La programación apagada es el caso más "
        "peligroso de los dos, porque el job parece activo.\n\nQUÉ HACER: confirmar con el equipo si fue intencional; si no lo fue, "
        "reactivar el job o la programación."),
    "backup_no_checksum": (
        "BACKUPS SIN CHECKSUM\n\nBases de datos con al menos 1 backup hecho sin WITH CHECKSUM en los últimos 7 días, o marcado como "
        "dañado.\n\nPOR QUÉ IMPORTA: sin checksum SQL Server no valida las páginas durante el backup — una corrupción silenciosa puede "
        "copiarse sin aviso, y RESTORE VERIFYONLY no la detecta. Solo se descubre en el restore, tarde.\n\nQUÉ HACER: activar WITH "
        "CHECKSUM en los jobs de backup de estas instancias.\n\nCada fila = par único (instancia + base de datos). Incluye FULL, DIFF y "
        "LOG."),
}
# overlay pt-BR: so' o que difere do pt-PT
PTBR = {
    "backup_failed": PT["backup_failed"].replace("voltar a executar", "reexecutar").replace("use a ligação", "use o link")
        .replace("correr à mão agora", "rodar manualmente agora").replace("recolhedor", "coletor").replace("o ficheiro não chegou", "o arquivo não chegou")
        .replace("a origem detetada", "a origem detectada").replace("volta a correr", "volta a rodar"),
    "backup_log_failed": PT["backup_log_failed"].replace("a ligação", "o link").replace("recolhedor", "coletor").replace("Se o job corre mas falha", "Se o job roda mas falha"),
    "backup_delayed": PT["backup_delayed"].replace("nunca ter corrido", "nunca ter rodado"),
    "backup_jobs_disabled": PT["backup_jobs_disabled"].replace("não vão correr", "não vão rodar").replace("com a equipa", "com a equipe"),
    "backup_no_checksum": PT["backup_no_checksum"].replace("não a deteta", "não a detecta"),
}
GRUPOS = {"pt": PT, "en": EN, "es": ES, "ptbr": PTBR}

PORTAL_EDITS = [
    ("""            const kpiInfo = BACKUP_KPI_INFO[kpiType];
            if (kpiInfo) {
""",
     """            // 2026-09-17: texto da ajuda vem dos locales (kpi_info.*); o dicionario antigo em portugues e' o recurso
            const kpiInfo = BACKUP_KPI_INFO[kpiType] ? _kpiT('kpi_info.' + String(kpiType).replace(/-/g, '_'), BACKUP_KPI_INFO[kpiType]) : null;
            if (kpiInfo) {
""", 1),
]

CHANGELOG_EDIT = (
    "## [Unreleased]\n\n### Changed\n\n",
    "## [Unreleased]\n\n### Changed\n\n"
    "- **Ajuda \"?\" das modais de backup em quatro idiomas** (owner 17/09). Os cinco textos (falhas, falhas de log, em atraso,\n"
    "  jobs desativados, sem checksum) estavam escritos à mão em português sem acentos; passam a `kpi_info.*` em pt/pt-BR/en/es.\n"
    "  [tier: Std]\n\n",
    1,
)

TEST_SRC = r'''"""
2026-09-17 -- ajuda "?" das modais de backup: chaves kpi_info.* nos locales; o consumidor passa por _kpiT.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = (ROOT / "templates/watcherdb_portal.html").read_text(encoding="utf-8")
LOC = {k: json.load(open(ROOT / f"static/i18n/{k}.json", encoding="utf-8")) for k in ("pt", "en", "es", "pt-BR")}
CHAVES = ["backup_failed", "backup_log_failed", "backup_delayed", "backup_jobs_disabled", "backup_no_checksum"]


def test_grupo_kpi_info_completo_em_pt_en_es():
    for loc in ("pt", "en", "es"):
        g = LOC[loc].get("kpi_info") or {}
        assert sorted(g) == sorted(CHAVES), (loc, sorted(set(CHAVES) ^ set(g)))
        assert all(len(v) > 200 and "\n\n" in v for v in g.values()), loc


def test_overlay_ptbr_so_com_o_que_difere():
    over = LOC["pt-BR"].get("kpi_info") or {}
    assert over
    for k, v in over.items():
        assert k in CHAVES and LOC["pt"]["kpi_info"][k] != v, k


def test_pt_acentuado_e_ao90():
    txt = json.dumps(LOC["pt"]["kpi_info"], ensure_ascii=False)
    assert "NÃO" in txt and "execução" in txt and "última" in txt
    assert not re.search(r"desactiv|activ[oa]r?\b|reactiv|actual\b|correcç|detecta\b|protecç", txt)


def test_o_consumidor_passa_pelo_dicionario_de_idiomas():
    assert "_kpiT('kpi_info.' + String(kpiType).replace(/-/g, '_'), BACKUP_KPI_INFO[kpiType])" in PORTAL
    assert "const kpiInfo = BACKUP_KPI_INFO[kpiType];" not in PORTAL
    for k in CHAVES:  # o recurso em portugues continua la' (nunca se mostra chave crua)
        assert f"'{k.replace('_', '-')}': '" in PORTAL
'''


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:140]!r}")
        text = text.replace(o, n)
    return text


def _inserir_grupo(texto: str, grupo: dict, label: str) -> str:
    antes = json.loads(texto)
    if "kpi_info" in antes:
        raise SystemExit(f"[ABORT] {label}: grupo kpi_info ja existe")
    corpo = texto.rstrip()
    if not corpo.endswith("}"):
        raise SystemExit(f"[ABORT] {label}: fim inesperado")
    corpo = corpo[:-1].rstrip()
    bloco = json.dumps(grupo, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    novo = corpo + ',\n  "kpi_info": ' + bloco + "\n}\n"
    depois = json.loads(novo)
    assert {k: v for k, v in depois.items() if k != "kpi_info"} == antes, f"{label}: o resto do ficheiro mudou"
    return novo


def main(argv):
    check = "--check" in argv
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    base = preview or ROOT
    src = {k: base / p for k, p in REL.items()}
    portal = src["portal"].read_bytes().decode("utf-8")
    if MARK in portal:
        print("[ABORT] ja aplicado"); return 1
    for k in PTBR:
        assert PTBR[k] != PT[k], f"overlay pt-BR igual ao pt em {k}"
    out = {"portal": _apply(portal, PORTAL_EDITS, "portal"), "changelog": _apply(src["changelog"].read_bytes().decode("utf-8"), [CHANGELOG_EDIT], "changelog")}
    for loc in ("pt", "en", "es", "ptbr"):
        out[loc] = _inserir_grupo(src[loc].read_bytes().decode("utf-8"), GRUPOS[loc], loc)
    compile(TEST_SRC, str(REL["test"]), "exec")
    print("[ok] portal 1 bloco (consumidor via _kpiT); pt/en/es +5 chaves kpi_info; pt-BR +5 (overlay); changelog; teste")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    src["test"].write_bytes(TEST_SRC.encode("utf-8")); print(f"[new]   {REL['test']}")
    print("\nAplicado. Corre: py -m pytest tests/unit/test_kpi_info_i18n_20260917.py tests/unit/test_i18n_parity.py -q --no-cov ; Restart-Service WatcherDBWebServiceV34")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
