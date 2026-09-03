# filegroup_interactive_report_v5.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, math, re
import logging
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import numpy as np
import pandas as pd
import tempfile
import pyodbc
import csv
import shlex
import subprocess

logger = logging.getLogger(__name__)


import plotly.graph_objects as go
from plotly.io import to_html

# importa a MESMA lib (agora com effective_capacity_mb)
from filegroup_forecast import ForecastConfig, run_pipeline

@dataclass
class ReportConfig:
    threshold_pct: float = 0.85  # ALTERADO: era 0.9 (90%)
    tz: str = "Europe/Lisbon"
    output_html: str = "report_interactive.html"
    workdays_lead: int = 1
    min_buffer_gb: int = 20
    growth_step_mb: int = 1024
    default_forecast_days: int = 60  # Aumentado de 14 para 60 dias

# ----------------------
# Conexões
# ----------------------

def _conn_dbadash() -> pyodbc.Connection:
    # Ajuste para o seu repositório DBADash
    conn_str = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=SQLAGSPRD213\\I01;DATABASE=DBADashDB;Trusted_Connection=yes;"
    return pyodbc.connect(conn_str)

def _conn_target(instance: str, database: str) -> pyodbc.Connection:
    # Conecta direto no ALVO para calcular MAXSIZE do FG
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={instance};DATABASE={database};Trusted_Connection=yes;"
    )

# ----------------------
# Dados
# ----------------------
class OracleExportError(RuntimeError):
    """Erro alto nível ao gerar CSV via oracle_to_csv.py."""

def _rename_header(csv_path: str,
                   from_col: str = "UPDATE_TS",
                   to_col: str = "SnapshotDate",
                   encoding: str = "utf-8") -> None:
    """
    Renomeia apenas o cabeçalho 'from_col' -> 'to_col' no CSV, se existir.
    """
    with open(csv_path, "r", encoding=encoding, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    try:
        i = header.index(from_col)
        header[i] = to_col
        rows[0] = header
        with open(csv_path, "w", encoding=encoding, newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerows(rows)
    except ValueError:
        # Coluna não existe; não faz nada
        return

def _slugify_filename(name: str) -> str:
    """
    Remove caracteres que não são seguros para nome de arquivo em Windows/Linux/Mac.
    Permite letras, números, _, -, .  e troca o resto por _.
    """
    name = name.strip()
    if not name:
        return "filegroup"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    # evita nomes especiais em Windows (CON, PRN, etc.) adicionando prefixo se necessário
    if name.upper() in {"CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
                        "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}:
        name = f"_{name}"
    return name

def get_filegroup_data(instance: str, database_name: str, filegroup_name: str) -> str:
    """
    Gera CSV com nome automático: interactive_{filegroup}_{datetime}_forecast.csv
    Executa oracle_to_csv.py e retorna o caminho completo do arquivo gerado.
    
    Args:
        instance: Nome da instância SQL Server (ex: "SQLIDSPRD03\\I01")
        database_name: Nome do banco de dados
        filegroup_name: Nome do filegroup
    
    Returns:
        str: Caminho completo do arquivo CSV gerado
    
    Raises:
        OracleExportError: Se houver falha na exportação
    """
    # Credenciais via variáveis de ambiente
    ORACLE_USER = os.getenv("ORACLE_USER", "")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
    if not ORACLE_USER or not ORACLE_PASSWORD:
        logger.error("Oracle credentials not set. Set ORACLE_USER and ORACLE_PASSWORD environment variables.")
    
    # Configurações da conexão Oracle
    HOST = "oradb_pcitpr.tap.pt"
    PORT = "1521"
    SERVICE_NAME = "PUSRR.TAP.PT"
    SCHEMA = "PDBACH_MSSQL_KPI"
    TABLE = "KPI_MSSQL_FG_USAGE_HIST"
    MONTHS = 4
    GRANULARITY = "day"
    
    # Caminho do script oracle_to_csv.py
    # Opção 1: No mesmo diretório deste script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    EXPORTER_PATH = os.path.join(script_dir, "oracle_to_csv.py")
    
    # Opção 2: Se preferir caminho absoluto fixo, descomente:
    # EXPORTER_PATH = r"C:\caminho\completo\para\oracle_to_csv.py"
    
    # Valida se o script existe
    if not os.path.exists(EXPORTER_PATH):
        raise OracleExportError(
            f"Script oracle_to_csv.py não encontrado em: {EXPORTER_PATH}\n"
            f"Certifique-se de que o arquivo está no mesmo diretório ou ajuste EXPORTER_PATH."
        )
    
    # Diretório de saída: MESMO diretório deste .py
    output_dir = os.path.dirname(os.path.abspath(__file__))

    
    print(f"📂 Diretório de saída: {output_dir}")
    print(f"📜 Script oracle_to_csv.py: {EXPORTER_PATH}")
    
    # Monta o comando (SEM --output, será gerado automaticamente)
    cmd = [
        sys.executable,  # Usa o mesmo Python que está executando este script
        EXPORTER_PATH,
        "--host", HOST,
        "--port", PORT,
        "--service-name", SERVICE_NAME,
        "agg",
        "--schema", SCHEMA,
        "--table", TABLE,
        "--instance", instance,
        "--db-name", database_name,
        "--filegroup", filegroup_name,
        "--months", str(MONTHS),
        "--granularity", GRANULARITY,
    ]
    
    # Prepara ambiente com credenciais (APENAS para o subprocess)
    child_env = os.environ.copy()
    child_env["ORACLE_USER"] = ORACLE_USER
    child_env["ORACLE_PASSWORD"] = ORACLE_PASSWORD
    
    print(f"🔄 Executando: {shlex.join(cmd)}")
    
    try:
        # Executa NO DIRETÓRIO DE SAÍDA (onde o CSV será criado)
        proc = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            env=child_env, 
            check=False,
            timeout=300,
            cwd=output_dir  # CSV será criado aqui
        )
    except subprocess.TimeoutExpired:
        raise OracleExportError("Timeout ao executar oracle_to_csv.py (>5min)")
    except Exception as exc:
        raise OracleExportError(f"Falha ao executar o exporter: {exc}") from exc
    
    # Valida retorno
    if proc.returncode != 0:
        raise OracleExportError(
            f"oracle_to_csv.py falhou com código {proc.returncode}.\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )
    
    print(f"📤 Saída do script:\n{proc.stdout}")
    
    # Extrai o nome do arquivo gerado da mensagem de saída
    # A mensagem do script é: "OK: X linhas exportadas para 'caminho_do_arquivo.csv'."
    match = re.search(r"OK: \d+ linhas exportadas para '([^']+)'", proc.stdout)
    if not match:
        raise OracleExportError(
            f"Não foi possível identificar o arquivo gerado.\n"
            f"STDOUT:\n{proc.stdout}"
        )
    
    output_csv = match.group(1)
    
    # Como executamos com cwd=output_dir, o caminho pode ser relativo
    # Converte para caminho absoluto
    if not os.path.isabs(output_csv):
        output_csv = os.path.join(output_dir, output_csv)
    
    # Valida se o arquivo realmente existe
    if not os.path.exists(output_csv):
        raise OracleExportError(f"CSV não encontrado: {output_csv}")
    
    file_size = os.path.getsize(output_csv)
    if file_size == 0:
        raise OracleExportError(f"CSV gerado está vazio: {output_csv}")
    
    print(f"✅ CSV gerado com sucesso: {output_csv} ({file_size:,} bytes)")

    return output_csv

def compute_effective_capacity_from_target(instance: str, database_name: str, filegroup_name: str) -> Tuple[Optional[float], Dict[str,float]]:
    """
    Capacidade efetiva (MB) no ALVO:
      - CappedMaxMB = soma por arquivo: MAXSIZE (se -1 => usa tamanho atual), growth=0 => só o alocado
      - UpperBoundToDiskMB = CappedMaxMB + soma de available_bytes por volume (se houver arquivos ilimitados)
    """
    sql = """
    DECLARE @fg sysname = ?;
    ;WITH f AS (
      SELECT 
         df.file_id,
         df.name AS FileName,
         df.physical_name,
         df.type_desc,
         CAST(df.size AS float) * 8.0/1024.0 AS AllocatedMB,
         CAST(FILEPROPERTY(df.name,'SpaceUsed') AS float) * 8.0/1024.0 AS UsedMB,
         CASE WHEN df.max_size = -1 THEN NULL ELSE CAST(df.max_size AS float) * 8.0/1024.0 END AS MaxMB,
         df.growth,
         df.is_percent_growth
      FROM sys.filegroups fg
      JOIN sys.database_files df ON df.data_space_id = fg.data_space_id
      WHERE fg.name = @fg AND df.type_desc = 'ROWS'
    ),
    vols AS (
      SELECT DISTINCT vs.volume_mount_point, CAST(vs.available_bytes AS float)/1024.0/1024.0 AS VolumeFreeMB
      FROM f CROSS APPLY sys.dm_os_volume_stats(DB_ID(), f.file_id) AS vs
    )
    SELECT
      SUM(CASE WHEN (MaxMB IS NULL OR growth = 0) THEN AllocatedMB ELSE MaxMB END) AS CappedMaxMB,
      SUM(AllocatedMB) AS AllocatedSumMB,
      SUM(UsedMB) AS UsedSumMB,
      SUM(CASE WHEN MaxMB IS NULL AND growth > 0 THEN 1 ELSE 0 END) AS UnlimitedFiles,
      (SELECT SUM(VolumeFreeMB) FROM vols) AS SumVolumeFreeMB;
    """
    conn = _conn_target(instance, database_name)
    cur = conn.cursor(); cur.execute(sql, (filegroup_name,))
    row = cur.fetchone(); conn.close()
    if not row or row[0] is None: return None, {}
    capped = float(row[0]); allocated = float(row[1] or 0.0); used = float(row[2] or 0.0)
    unlimited = float(row[3] or 0.0); free_mb = float(row[4] or 0.0)
    info = {
        "CappedMaxMB": capped,
        "AllocatedMB": allocated,
        "UsedMB": used,
        "UnlimitedFiles": unlimited,
        "SumVolumeFreeMB": free_mb,
        "UpperBoundToDiskMB": capped + (free_mb if unlimited > 0 else 0.0),
    }
    return capped, info

# ----------------------
# Gráficos
# ----------------------
def _compute_weekend_spans(start_ts, end_ts, tz="Europe/Lisbon"):
    spans = []
    cur = pd.Timestamp(start_ts); end = pd.Timestamp(end_ts)
    if cur.tzinfo is None: cur = cur.tz_localize(tz)
    else: cur = cur.tz_convert(tz)
    if end.tzinfo is None: end = end.tz_localize(tz)
    else: end = end.tz_convert(tz)
    cur = cur.normalize(); end = end.normalize() + pd.Timedelta(days=1)
    while cur < end:
        if cur.dayofweek in (5, 6): spans.append((cur, cur + pd.Timedelta(days=1)))
        cur += pd.Timedelta(days=1)
    return spans

def build_fig_timeseries(forecast_df: pd.DataFrame) -> go.Figure:
    hist = forecast_df[~forecast_df["is_forecast"]]
    cap_col = "Capacity_MB" if "Capacity_MB" in forecast_df.columns else "Total_Size_MB"
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist["SnapshotDate"], y=hist["Total_Used_MB"], mode="lines+markers",
                             name="Usado (real)",
                             hovertemplate="%{x|%Y-%m-%d}<br>Usado: %{y:.0f} MB<extra></extra>"))
    fig.add_trace(go.Scatter(x=forecast_df["SnapshotDate"], y=forecast_df["yhat"], mode="lines",
                             name="Previsão (yhat)", line=dict(dash="dash"),
                             hovertemplate="%{x|%Y-%m-%d}<br>Previsto: %{y:.0f} MB<extra></extra>"))
    fig.add_trace(go.Scatter(x=forecast_df["SnapshotDate"], y=forecast_df[cap_col], mode="lines",
                             name="Capacidade", line=dict(dash="dot"),
                             hovertemplate="%{x|%Y-%m-%d}<br>Capacidade: %{y:.0f} MB<extra></extra>"))
    spans = _compute_weekend_spans(forecast_df["SnapshotDate"].min(), forecast_df["SnapshotDate"].max())
    shapes = [dict(type="rect", xref="x", x0=s, x1=e, yref="paper", y0=0, y1=1,
                   fillcolor="LightGray", opacity=0.2, line=dict(width=0)) for (s, e) in spans]
    fig.update_layout(
        xaxis=dict(title="Data", rangeselector=dict(buttons=[
            dict(count=7, label="7d", step="day", stepmode="backward"),
            dict(count=30, label="1m", step="day", stepmode="backward"),
            dict(count=90, label="3m", step="day", stepmode="backward"),
            dict(step="all", label="Tudo"),
        ]), rangeslider=dict(visible=True), showspikes=True, spikemode="across"),
        yaxis=dict(title="MB", showspikes=True, spikemode="across"),
        hovermode="x unified",
        shapes=shapes,
        margin=dict(l=20, r=10, t=10, b=40),
    )
    return fig

def build_fig_pct_used(forecast_df: pd.DataFrame, threshold_pct: float = 0.9) -> go.Figure:
    cap_col = "Capacity_MB" if "Capacity_MB" in forecast_df.columns else "Total_Size_MB"
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=forecast_df["SnapshotDate"],
                             y=(forecast_df["yhat"] / forecast_df[cap_col] * 100.0),
                             mode="lines", name="% Usado (previsto)",
                             hovertemplate="%{x|%Y-%m-%d}<br>% Usado: %{y:.2f}%<extra></extra>"))
    fig.add_hline(y=threshold_pct*100.0, line_dash="dot",
                  annotation_text=f"Limiar {int(threshold_pct*100)}%",
                  annotation_position="top left")
    fig.update_layout(
        xaxis=dict(title="Data", rangeslider=dict(visible=True), showspikes=True, spikemode="across"),
        yaxis=dict(title="%", range=[0, 110], showspikes=True, spikemode="across"),
        hovermode="x unified",
        margin=dict(l=20, r=10, t=10, b=40),
    )
    return fig

# ----------------------
# Plano de ação + SQL
# ----------------------
def _round_up_mb(x_mb: float, step_mb: int) -> int:
    return int(math.ceil(max(0.0, x_mb) / step_mb) * step_mb)

def compute_action_plan_and_sql(df_forecast: pd.DataFrame, events: dict, db_name: str, fg_name: str, cfg: ReportConfig) -> Dict[str, str]:
    tz = cfg.tz
    cap_col = "Capacity_MB" if "Capacity_MB" in df_forecast.columns else "Total_Size_MB"
    cap_mb = float(df_forecast[cap_col].iloc[-1])

    # Verifica se há data de 100% nos eventos
    hit_100_date = events.get("hit_100_pct_date")
    if hit_100_date is not None:
        crit_ts = pd.to_datetime(hit_100_date)
        if crit_ts.tzinfo is None: crit_ts = crit_ts.tz_localize(tz)
    else:
        # Fallback para data de 90% ou máxima previsão
        crit_ts = events.get("cross_90_pct_date")
        if pd.isna(crit_ts) or crit_ts is None:
            idx_max = df_forecast["yhat"].idxmax()
            crit_ts = df_forecast.loc[idx_max, "SnapshotDate"]
        crit_ts = pd.to_datetime(crit_ts)
        if crit_ts.tzinfo is None: crit_ts = crit_ts.tz_localize(tz)

    # Converte SnapshotDate para datetime se necessário
    if not pd.api.types.is_datetime64_any_dtype(df_forecast["SnapshotDate"]):
        df_forecast["SnapshotDate"] = pd.to_datetime(df_forecast["SnapshotDate"], utc=True)
    
    # Aplica timezone se necessário
    if df_forecast["SnapshotDate"].dt.tz is None:
        df_forecast["SnapshotDate"] = df_forecast["SnapshotDate"].dt.tz_localize(tz)
    else:
        df_forecast["SnapshotDate"] = df_forecast["SnapshotDate"].dt.tz_convert(tz)
    
    df_forecast["d_norm"] = df_forecast["SnapshotDate"].dt.normalize()
    ycrit = df_forecast.loc[df_forecast["d_norm"] == crit_ts.normalize(), "yhat"]
    yhat_crit = float(ycrit.iloc[0]) if not ycrit.empty else float(df_forecast.iloc[df_forecast["yhat"].idxmax()]["yhat"])

    buffer_mb = max(0.05 * cap_mb, cfg.min_buffer_gb * 1024)
    delta_mb = max(0.0, (yhat_crit + buffer_mb) - cap_mb)
    delta_mb_r = _round_up_mb(delta_mb, cfg.growth_step_mb)
    new_total_mb = _round_up_mb(cap_mb + delta_mb_r, cfg.growth_step_mb)

    def _biz_days_before(date: pd.Timestamp, days: int) -> pd.Timestamp:
        d, cnt = date, 0
        while cnt < days:
            d = d - pd.Timedelta(days=1)
            if d.dayofweek < 5: cnt += 1
        return d
    exec_by = _biz_days_before(crit_ts, cfg.workdays_lead).strftime("%Y-%m-%d")

    sql_alter = f"""-- ALTER FILE (aumentar arquivo existente)
USE [{db_name}];
GO
ALTER DATABASE [{db_name}] MODIFY FILE
(
    NAME = <LOGICAL_FILE_NAME>,
    SIZE = {new_total_mb}MB,
    FILEGROWTH = {cfg.growth_step_mb}MB
);
GO
"""
    sql_add = f"""-- ADD FILE (adicionar .ndf ao filegroup {fg_name})
USE [{db_name}];
GO
ALTER DATABASE [{db_name}] ADD FILE
(
    NAME = N'{db_name}_{fg_name}_NN',
    FILENAME = N'<CAMINHO>\\{db_name}_{fg_name}_NN.ndf',
    SIZE = {delta_mb_r}MB,
    FILEGROWTH = {cfg.growth_step_mb}MB
) TO FILEGROUP [{fg_name}];
GO
"""
    slope = events.get("slope_mb_per_day")
    slope_txt = f"{slope:.1f} MB/dia" if slope is not None else "-"

    # Informações sobre data de 100%
    hit_100_info = ""
    if hit_100_date is not None:
        hit_100_dt = pd.to_datetime(hit_100_date)
        days_to_100 = (hit_100_dt - pd.Timestamp.now(tz=tz)).days
        hit_100_info = f"• ⚠️ ATINGE 100% EM: {hit_100_dt.strftime('%d/%m/%Y')} ({days_to_100} dias restantes) - AÇÃO URGENTE!"
    
    plan_text = "\n".join([
        f"• Crescimento médio estimado: {slope_txt}",
        hit_100_info,
        f"• Executar expansão até {exec_by} (>= {cfg.workdays_lead} dia(s) útil(eis) antes do pico/limiar).",
        f"• Capacidade (alerta): {int(cap_mb):,} MB | yhat(crit): {int(yhat_crit):,} MB | Buffer: {int(buffer_mb):,} MB".replace(",", "."),
        f"• Delta recomendado (arred.): {delta_mb_r:,} MB".replace(",", "."),
        f"• Sugerir FILEGROWTH fixo = {cfg.growth_step_mb} MB.",
        "• Validar espaço em disco no storage/VM e registrar a mudança.",
    ])

    return {
        "critical_date": crit_ts.strftime("%Y-%m-%d"),
        "exec_by": exec_by,
        "plan_text": plan_text,
        "sql_alter": sql_alter,
        "sql_add": sql_add,
        "slope_txt": slope_txt,
    }

# ----------------------
# HTML
# ----------------------
def _card(label: str, value: str) -> str:
    return f"""
    <div class="card">
        <div class="card-label">{label}</div>
        <div class="card-value">{value}</div>
    </div>
    """

def write_html_report(figs: List[go.Figure], events: dict, meta: dict, plan: dict, cfg: ReportConfig) -> str:
    css = """
    <style>
      body { margin:16px; font-family: Inter, Arial, sans-serif; color:#222; }
      .title { font-size:22px; font-weight:700; margin-bottom:6px; }
      .meta { color:#555; margin-bottom:12px; }
      .grid-cards { display:grid; grid-template-columns: repeat(4, minmax(160px,1fr)); gap:12px; margin-bottom:12px; }
      .card { border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.04); }
      .card-label { font-size:12px; color:#6b7280; }
      .card-value { font-size:18px; font-weight:600; margin-top:4px; }
      .block { border:1px solid #e5e7eb; border-radius:12px; padding:12px; margin-bottom:14px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.04); }
      .block h3 { margin:0 0 8px 0; font-size:18px; }
      .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
      pre { background:#f8fafc; border:1px solid #e5e7eb; padding:10px; border-radius:8px; overflow-x:auto; }
      @media (max-width: 1024px) { .grid-cards { grid-template-columns: 1fr 1fr; } }
      @media (max-width: 640px)  { .grid-cards { grid-template-columns: 1fr; } }
    </style>
    """
    def fmt(ts):
        if ts is None: return "-"
        try: return pd.to_datetime(ts).strftime("%Y-%m-%d")
        except Exception: return str(ts)

    header = f"""
    <div class="title">Forecast de Filegroup</div>
    <div class="meta">
      Instance: <b>{meta.get('Instance','-')}</b> |
      Database: <b>{meta.get('DatabaseName','-')}</b> |
      Filegroup: <b>{meta.get('filegroup_name','-')}</b> |
      Cap. alocada: <b>{meta.get('capacity_alloc_mb','-')} MB</b> |
      Cap. efetiva (MAXSIZE): <b>{meta.get('capacity_eff_mb','-')} MB</b>
    </div>
    """
    # Formatação especial para data de 100%
    hit_100_display = "-"
    hit_100_date = events.get("hit_100_pct_date")
    if hit_100_date is not None:
        hit_100_dt = pd.to_datetime(hit_100_date)
        days_to_100 = (hit_100_dt - pd.Timestamp.now(tz=cfg.tz)).days
        hit_100_display = f"{hit_100_dt.strftime('%d/%m/%Y')} ({days_to_100}d)"
    
    cards = "".join([
        _card("Crescimento médio", plan.get("slope_txt","-")),
        _card(f"Cruza {int(cfg.threshold_pct*100)}%", fmt(events.get("cross_90_pct_date"))),
        _card("Atinge 100%", hit_100_display),
        _card("Fins de semana em alerta", str(len(events.get("weekend_cross_90",[])))),
    ])
    figs_html = "".join([f'<div class="block">{to_html(fig, include_plotlyjs="cdn", full_html=False)}</div>' for fig in figs])

    plan_html = f"""
    <div class="block">
      <h3>Plano de ação</h3>
      <p>Data crítica: <b>{plan.get('critical_date','-')}</b> — executar até <b>{plan.get('exec_by','-')}</b>.</p>
      <pre class="mono">{plan.get('plan_text','')}</pre>
      <h3 style="margin-top:12px;">T-SQL sugerido (ALTER FILE)</h3>
      <pre class="mono">{plan.get('sql_alter','')}</pre>
      <h3 style="margin-top:12px;">T-SQL sugerido (ADD FILE)</h3>
      <pre class="mono">{plan.get('sql_add','')}</pre>
    </div>
    """
    html = f"""
    <html>
    <head><meta charset="utf-8"/><title>Forecast Filegroup - Interativo</title>{css}</head>
    <body>
      {header}
      <div class="grid-cards">{cards}</div>
      {figs_html}
      {plan_html}
      <div style="font-size:12px;color:#888;margin-top:8px;">
         Gerado em {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {cfg.tz}
      </div>
    </body>
    </html>
    """
    with open(cfg.output_html, "w", encoding="utf-8") as f:
        f.write(html)
    return cfg.output_html

# ----------------------
# Orquestração
# ----------------------
def generate_interactive_report(
    instance: str,
    database_name: str,
    filegroup_name: str,
    horizon_days: int = 30,
    threshold_pct: float = 0.9,
    output_html: str = "report_interactive.html",
    tz: str = "Europe/Lisbon",
    workdays_lead: int = 1,
    min_buffer_gb: int = 20,
    growth_step_mb: int = 1024,
) -> str:
    # histórico
    csv_path = get_filegroup_data(instance, database_name, filegroup_name)

    # capacidade efetiva (MAXSIZE) no alvo
    eff_cap_mb, cap_info = None, {}
    try:
        eff_cap_mb, cap_info = compute_effective_capacity_from_target(instance, database_name, filegroup_name)
    except Exception:
        eff_cap_mb, cap_info = None, {}

    filters = {"Instance": instance, "DatabaseName": database_name, "filegroup_name": filegroup_name}
    cfg_fc = ForecastConfig(
        horizon_days=horizon_days,
        weekend_threshold_pct=threshold_pct,
        capacity_buffer_mb=0.0,
        group_filters=filters,
        tz=tz,
        effective_capacity_mb=eff_cap_mb,  # <- aqui está a correção
    )
    # Evita colisões quando várias execuções rodam em paralelo:
    # usa prefixo único por execução (FG sanitizado + timestamp + PID)
    safe_fg = re.sub(r"[^A-Za-z0-9_-]+", "_", filegroup_name)
    unique_prefix = f"interactive_{safe_fg}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{os.getpid()}"
    forecast_csv, _png, events = run_pipeline(
        csv_path,
        cfg_fc,
        output_dir=".",
        save_prefix=unique_prefix,
    )

    try: os.remove(csv_path)
    except: pass

    df_forecast = pd.read_csv(forecast_csv, parse_dates=["SnapshotDate"])
    try:
        if df_forecast["SnapshotDate"].dt.tz is None:
            df_forecast["SnapshotDate"] = df_forecast["SnapshotDate"].dt.tz_localize(tz)
        else:
            df_forecast["SnapshotDate"] = df_forecast["SnapshotDate"].dt.tz_convert(tz)
    except Exception:
        pass

    # gráficos
    fig_ts = build_fig_timeseries(df_forecast)
    fig_pct = build_fig_pct_used(df_forecast, threshold_pct=threshold_pct)

    meta = dict(
        Instance=instance,
        DatabaseName=database_name,
        filegroup_name=filegroup_name,
        capacity_alloc_mb=int(df_forecast["Total_Size_MB"].iloc[-1]),
        capacity_eff_mb=int(eff_cap_mb) if eff_cap_mb else int(df_forecast["Total_Size_MB"].iloc[-1]),
    )
    rcfg = ReportConfig(threshold_pct=threshold_pct, tz=tz, output_html=output_html,
                        workdays_lead=workdays_lead, min_buffer_gb=min_buffer_gb, growth_step_mb=growth_step_mb)
    plan = compute_action_plan_and_sql(df_forecast, events, database_name, filegroup_name, rcfg)
    return write_html_report([fig_ts, fig_pct], events, meta, plan, rcfg)

# ----------------------
# CLI
# ----------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python filegroup_interactive_report_v5.py \"Instance=...;DatabaseName=...;filegroup_name=...\" [horizon_days] [threshold_pct]")
        raise SystemExit(1)

    filters_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    horizon_days = int(sys.argv[2]) if len(sys.argv) >= 3 else 30
    threshold_pct = float(sys.argv[3]) if len(sys.argv) >= 4 else 0.9

    filters = {}
    if filters_arg:
        for pair in filters_arg.split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                filters[k] = v

    required_params = ["Instance", "DatabaseName", "filegroup_name"]
    missing = [p for p in required_params if p not in filters]
    if missing:
        print(f"Erro: Parâmetros obrigatórios ausentes: {', '.join(missing)}")
        raise SystemExit(1)

    ts = datetime.now().strftime("%Y%m%d%H%M")
    safe_fg = re.sub(r"[^A-Za-z0-9_-]+", "_", filters["filegroup_name"]) if "filegroup_name" in filters else "FG"
    dynamic_output = f"report_{safe_fg}_{ts}.html"

    out_html = generate_interactive_report(
        instance=filters["Instance"],
        database_name=filters["DatabaseName"],
        filegroup_name=filters["filegroup_name"],
        horizon_days=horizon_days,
        threshold_pct=threshold_pct,
        output_html=dynamic_output,
        tz="Europe/Lisbon",
        workdays_lead=1,
        min_buffer_gb=20,
        growth_step_mb=1024,
    )
    print("HTML gerado em:", out_html)
