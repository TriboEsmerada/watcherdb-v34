"""
FILEGROUP INTERACTIVE REPORT - WATCHERDB v5 (WatcherDB Data Source)
Versao que usa dados do proprio WatcherDB Intelligence ao inves de conectar direto no servidor remoto

Uso:
    python filegroup_interactive_report_v5_watcherdb.py "Instance=SERVER;DatabaseName=DB;filegroup_name=FG" [forecast_days] [threshold]
"""

import sys
import os
import pyodbc
from datetime import datetime, timedelta
from pathlib import Path
import json

class FilegroupForecastAnalyzerWatcherDB:
    """Analisador usando dados do WatcherDB Intelligence"""

    def __init__(self, instance, database, filegroup, forecast_days=60, threshold=0.85):
        self.instance = instance
        self.database = database
        self.filegroup = filegroup
        self.forecast_days = forecast_days
        self.threshold = threshold
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]

        self.base_path = Path(__file__).parent
        self.reports_path = self.base_path / "reports"
        self.reports_path.mkdir(exist_ok=True)

        # WatcherDB Intelligence connection
        self.watcherdb_server = "SQLHDSTST505\\I01"
        self.watcherdb_database = "WatcherDB_Intelligence"

    def get_watcherdb_connection(self, timeout=30):
        """Conecta ao WatcherDB Intelligence (local)"""
        try:
            conn_str = (
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={self.watcherdb_server};'
                f'DATABASE={self.watcherdb_database};'
                f'Trusted_Connection=yes;'
                f'Connection Timeout={timeout};'
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            raise Exception(f"Erro ao conectar no WatcherDB Intelligence: {e}")

    def _get_instance_formats(self, conn):
        """
        Gera lista de possíveis formatos de Instance para busca.
        Se o nome não tem sufixo (_I01 ou \\I01), busca no banco o nome real.
        """
        instance_formats = [self.instance]

        # Se já tem underscore _I ou backslash \I, expande ambos formatos
        if '_I' in self.instance and '\\' not in self.instance:
            parts = self.instance.split('_I')
            instance_formats.append(f"{parts[0]}\\I{parts[1]}")
        elif '\\I' in self.instance:
            parts = self.instance.split('\\I')
            instance_formats.append(f"{parts[0]}_I{parts[1]}")
        else:
            # Não tem sufixo - buscar no banco a instância real com LIKE
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT Instance
                    FROM dbo.KPI_MSSQL_FG_USAGE_STG
                    WHERE Instance LIKE ?
                    ORDER BY Instance
                """, (f"{self.instance}%",))
                rows = cursor.fetchall()
                if rows:
                    # Adiciona todas as instâncias encontradas
                    for row in rows:
                        if row[0] not in instance_formats:
                            instance_formats.append(row[0])

                # Também busca na tabela HIST (pode ter formatos diferentes)
                cursor.execute("""
                    SELECT DISTINCT Instance
                    FROM dbo.KPI_MSSQL_FG_USAGE_HIST
                    WHERE Instance LIKE ?
                    ORDER BY Instance
                """, (f"{self.instance}%",))
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        if row[0] not in instance_formats:
                            instance_formats.append(row[0])
            except Exception as e:
                # Se falhar, tenta os sufixos padrão
                instance_formats.append(f"{self.instance}_I01")
                instance_formats.append(f"{self.instance}\\I01")

        return instance_formats

    def _get_available_filegroups(self, conn, instance_formats):
        """Retorna lista de filegroups disponíveis para este servidor/database"""
        try:
            cursor = conn.cursor()

            for instance_sql in instance_formats:
                query = """
                SELECT DISTINCT Filegroup
                FROM dbo.KPI_MSSQL_FG_USAGE_STG
                WHERE Instance = ?
                  AND [Database] = ?
                ORDER BY Filegroup
                """
                cursor.execute(query, (instance_sql, self.database))
                rows = cursor.fetchall()
                if rows:
                    return [row[0] for row in rows]

            return []
        except Exception:
            return []

    def get_historical_data(self, days=30):
        """Busca dados históricos do WatcherDB (tabela KPI_MSSQL_FG_USAGE_HIST)"""
        conn = self.get_watcherdb_connection()

        try:
            cursor = conn.cursor()
            historical_data = []

            # Usa método centralizado para obter formatos possíveis de instance
            instance_formats = self._get_instance_formats(conn)

            # Normaliza todos os formatos para underscore (tabela HIST está normalizada)
            normalized_formats = list(set([fmt.replace('\\', '_') for fmt in instance_formats]))

            found_instance = None

            # Tenta cada formato até encontrar dados
            for instance_sql in normalized_formats:
                query = """
                SELECT
                    Collect_Date,
                    Total_MB,
                    Used_MB,
                    Percent_Used
                FROM dbo.KPI_MSSQL_FG_USAGE_HIST
                WHERE Instance = ?
                  AND [Database] = ?
                  AND Filegroup = ?
                  AND Collect_Date >= DATEADD(DAY, -?, GETDATE())
                ORDER BY Collect_Date ASC
                """
                cursor.execute(query, (instance_sql, self.database, self.filegroup, days))
                rows = cursor.fetchall()

                if rows:
                    found_instance = instance_sql
                    for row in rows:
                        historical_data.append({
                            'date': row[0],
                            'total_mb': float(row[1]) if row[1] else 0,
                            'used_mb': float(row[2]) if row[2] else 0,
                            'used_pct': float(row[3]) if row[3] else 0
                        })
                    break  # Encontrou dados, para de procurar

            if found_instance:
                print(f"✓ Histórico encontrado: {len(historical_data)} dias (instance: {found_instance})", file=sys.stderr)
            else:
                print(f"⚠ Nenhum histórico encontrado para formatos: {normalized_formats}", file=sys.stderr)

            return historical_data

        except Exception as e:
            print(f"⚠ Aviso: Não foi possível obter dados históricos: {e}", file=sys.stderr)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_filegroup_current_data(self):
        """Busca dados atuais do filegroup do WatcherDB"""
        conn = self.get_watcherdb_connection()

        try:
            # Usa método centralizado para obter formatos possíveis de instance
            instance_formats = self._get_instance_formats(conn)

            cursor = conn.cursor()
            row = None
            source_table = "STG"

            # 1. Primeiro tenta na tabela STG (dados atuais)
            for instance_sql in instance_formats:
                query = """
                SELECT TOP 1
                    Instance,
                    [Database],
                    Filegroup,
                    CAST(Total_MB AS FLOAT) AS Size_MB,
                    CAST(Used_MB AS FLOAT) AS Used_MB,
                    CAST(Percent_Used AS FLOAT) AS Used_PCT,
                    Update_TS
                FROM dbo.KPI_MSSQL_FG_USAGE_STG
                WHERE Instance = ?
                  AND [Database] = ?
                  AND Filegroup = ?
                ORDER BY Update_TS DESC
                """

                cursor.execute(query, (instance_sql, self.database, self.filegroup))
                row = cursor.fetchone()

                if row:
                    break  # Encontrou dados, sair do loop

            # 2. Se não encontrou na STG, tenta na HIST (dados históricos mais recentes)
            if not row:
                source_table = "HIST"
                for instance_sql in instance_formats:
                    query = """
                    SELECT TOP 1
                        Instance,
                        [Database],
                        Filegroup,
                        CAST(Total_MB AS FLOAT) AS Size_MB,
                        CAST(Used_MB AS FLOAT) AS Used_MB,
                        CAST(Percent_Used AS FLOAT) AS Used_PCT,
                        Collect_Date AS Update_TS
                    FROM dbo.KPI_MSSQL_FG_USAGE_HIST
                    WHERE Instance = ?
                      AND [Database] = ?
                      AND Filegroup = ?
                    ORDER BY Collect_Date DESC
                    """

                    cursor.execute(query, (instance_sql, self.database, self.filegroup))
                    row = cursor.fetchone()

                    if row:
                        print(f"⚠ Dados obtidos da tabela HIST (coleta atual não tem este filegroup)", file=sys.stderr)
                        break  # Encontrou dados, sair do loop

            if not row:
                # Filegroup não encontrado - buscar filegroups disponíveis para mensagem útil
                available_fgs = self._get_available_filegroups(conn, instance_formats)

                error_msg = (
                    f"Filegroup '{self.filegroup}' não encontrado.\n"
                    f"Servidor: {self.instance}\n"
                    f"Database: {self.database}\n\n"
                )

                if available_fgs:
                    error_msg += "Filegroups disponíveis:\n"
                    for fg in available_fgs[:10]:  # Mostrar até 10
                        error_msg += f"  - {fg}\n"
                    if len(available_fgs) > 10:
                        error_msg += f"  ... e mais {len(available_fgs) - 10} filegroups\n"
                else:
                    error_msg += "Nenhum filegroup encontrado para este servidor/database.\n"

                # Imprimir em STDERR para que API capture corretamente
                print(error_msg, file=sys.stderr)
                return None

            return {
                'filegroup': row[2],
                'size_mb': float(row[3]) if row[3] else 0,
                'used_mb': float(row[4]) if row[4] else 0,
                'used_pct': float(row[5]) if row[5] else 0,
                'data_coleta': row[6],
                'source': source_table
            }

        except Exception as e:
            print(f"ERRO: {e}")
            return None
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def calculate_simple_forecast(self, current_info):
        """Calcula previsao usando dados historicos (se disponiveis) ou crescimento linear"""

        # Tentar obter dados historicos - 6 meses para melhor precisao
        historical_data = self.get_historical_data(days=180)

        # Se temos dados historicos suficientes, calcular taxa real de crescimento
        if len(historical_data) >= 7:
            # Calcular crescimento medio diario baseado em dados reais
            daily_growth_mb = self._calculate_avg_daily_growth(historical_data)
            daily_growth_pct = (daily_growth_mb / current_info['size_mb']) * 100 if current_info['size_mb'] > 0 else 1.0

            # Limitar a valores razoaveis
            daily_growth_pct = max(0.1, min(daily_growth_pct, 5.0))

            print(f"✓ Usando {len(historical_data)} dias de histórico. Crescimento médio: {daily_growth_pct:.3f}% ao dia", file=sys.stderr)
        else:
            # Fallback: crescimento conservador de 1% ao dia
            daily_growth_pct = 1.0
            print(f"⚠ Usando previsão conservadora (1% ao dia). Histórico insuficiente: {len(historical_data)} dias", file=sys.stderr)

        current_pct = current_info['used_pct']
        threshold_pct = self.threshold * 100

        forecast = []
        for day in range(1, self.forecast_days + 1):
            forecast_pct = current_pct + (daily_growth_pct * day)
            forecast_pct = min(forecast_pct, 100)  # Nao ultrapassa 100%

            forecast.append({
                'day': day,
                'date': (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d'),
                'used_pct': forecast_pct
            })

            # Alerta de atencao (threshold, geralmente 85%)
            if forecast_pct >= threshold_pct and not hasattr(self, 'alert_day'):
                self.alert_day = day
                self.alert_date = (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d')

            # Estouro real (100%)
            if forecast_pct >= 100 and not hasattr(self, 'critical_day'):
                self.critical_day = day
                self.critical_date = (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d')

        return forecast

    def _calculate_avg_daily_growth(self, historical_data):
        """Calcula crescimento medio diario em MB baseado em dados historicos"""
        if len(historical_data) < 2:
            return 0.0

        # Calcular diferenca de Used_MB entre primeiro e ultimo dia
        first_day = historical_data[0]
        last_day = historical_data[-1]

        days_diff = (last_day['date'] - first_day['date']).days
        if days_diff <= 0:
            return 0.0

        mb_diff = last_day['used_mb'] - first_day['used_mb']
        avg_daily_growth = mb_diff / days_diff

        return max(0.0, avg_daily_growth)  # Nunca negativo

    def generate_html_report(self, current_info, forecast, historical_data=None):
        """Gera relatorio HTML com historico e previsao"""

        base_name = f"interactive_{self.filegroup}_{self.timestamp}_forecast"
        html_file = self.reports_path / f"{base_name}.html"
        csv_file = self.reports_path / f"{base_name}.csv"

        # Se nao recebeu historico, buscar - 180 dias (6 meses) para drill-down completo
        if historical_data is None:
            historical_data = self.get_historical_data(days=180)

        # CSV
        with open(csv_file, 'w') as f:
            f.write("Day,Date,Used_Pct\\n")
            f.write(f"0,{datetime.now().strftime('%Y-%m-%d')},{current_info['used_pct']:.2f}\\n")
            for item in forecast:
                f.write(f"{item['day']},{item['date']},{item['used_pct']:.2f}\\n")

        # Status - baseado no estouro real (100%), nao no threshold
        if hasattr(self, 'critical_day'):
            days_until = self.critical_day
            status_color = "red" if days_until < 30 else "orange" if days_until < 90 else "yellow"
            status_text = f"CRITICO: Estouro (100%) em {days_until} dias ({self.critical_date})"
        elif hasattr(self, 'alert_day'):
            days_until = self.alert_day
            status_color = "orange" if days_until < 30 else "yellow"
            status_text = f"ATENCAO: Atingira {self.threshold*100:.0f}% em {days_until} dias ({self.alert_date})"
        else:
            status_color = "green"
            status_text = f"OK: Nao atingira {self.threshold*100:.0f}% nos proximos {self.forecast_days} dias"

        # Dados historicos para o grafico
        hist_labels = [item['date'].strftime('%Y-%m-%d') for item in historical_data] if historical_data else []
        hist_data = [item['used_pct'] for item in historical_data] if historical_data else []

        # Dados para Chart.js - combinar historico + previsao
        # Labels: historico + hoje + previsao
        chart_labels = hist_labels + [datetime.now().strftime('%Y-%m-%d')] + [item['date'] for item in forecast]

        # Dados historicos: valores reais, depois null para previsao
        hist_chart_data = hist_data + [current_info['used_pct']] + [None] * len(forecast)

        # Dados previsao: null para historico, depois valores previstos
        forecast_chart_data = [None] * len(hist_labels) + [current_info['used_pct']] + [item['used_pct'] for item in forecast]

        # HTML
        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Analise Preditiva: {self.filegroup}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0a0f1a 0%, #1a2332 100%);
            color: #f1f5f9;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}
        .header h1 {{ font-size: 2rem; margin-bottom: 10px; color: white; }}
        .header .meta {{ font-size: 0.9rem; opacity: 0.9; }}
        .status-card {{
            background: {'#7f1d1d' if status_color == 'red' else '#78350f' if status_color == 'orange' else '#713f12' if status_color == 'yellow' else '#064e3b'};
            border-left: 4px solid {'#dc2626' if status_color == 'red' else '#f59e0b' if status_color == 'orange' else '#eab308' if status_color == 'yellow' else '#10b981'};
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            font-size: 1.1rem;
            font-weight: 500;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .info-card {{
            background: #1a2332;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #2d3e52;
        }}
        .info-card h3 {{
            font-size: 0.85rem;
            color: #94a3b8;
            margin-bottom: 8px;
            text-transform: uppercase;
        }}
        .info-card .value {{ font-size: 1.8rem; font-weight: 700; color: #60a5fa; }}
        .chart-container {{
            background: #1a2332;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid #2d3e52;
        }}
        .chart-container h2 {{ margin-bottom: 20px; color: #cbd5e1; }}
        #forecastChart {{ max-height: 400px; }}
        .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 0.85rem; }}
        .badge {{
            display: inline-block;
            background: #3b82f6;
            color: white;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 0.75rem;
            margin-left: 10px;
        }}
        .chart-controls {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .zoom-btn, .nav-btn {{
            background: #2d3e52;
            border: 1px solid #3d4f66;
            color: #94a3b8;
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s;
        }}
        .zoom-btn:hover, .nav-btn:hover {{
            background: #3d4f66;
            color: #f1f5f9;
        }}
        .zoom-btn.active {{
            background: #3b82f6;
            border-color: #3b82f6;
            color: white;
        }}
        .nav-btn {{
            padding: 8px 12px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Analise Preditiva de Crescimento <span class="badge">WatcherDB Data</span></h1>
            <div class="meta">
                <strong>Instance:</strong> {self.instance} |
                <strong>Database:</strong> {self.database} |
                <strong>Filegroup:</strong> {self.filegroup}
            </div>
        </div>

        <div class="status-card">{status_text}</div>

        <div class="info-grid">
            <div class="info-card">
                <h3>Tamanho Atual</h3>
                <div class="value">{current_info['size_mb']:.0f} MB</div>
            </div>
            <div class="info-card">
                <h3>Uso Atual</h3>
                <div class="value">{current_info['used_mb']:.0f} MB ({current_info['used_pct']:.1f}%)</div>
            </div>
            <div class="info-card">
                <h3>Alerta ({self.threshold*100:.0f}%)</h3>
                <div class="value" style="color: {'#f59e0b' if hasattr(self, 'alert_day') else '#10b981'};">{f"{self.alert_day} dias" if hasattr(self, 'alert_day') else "OK"}</div>
                <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 4px;">{self.alert_date if hasattr(self, 'alert_date') else f"Sem risco em {self.forecast_days} dias"}</div>
            </div>
            <div class="info-card">
                <h3>Estouro (100%)</h3>
                <div class="value" style="color: {'#dc2626' if hasattr(self, 'critical_day') else '#10b981'};">{f"{self.critical_day} dias" if hasattr(self, 'critical_day') else "OK"}</div>
                <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 4px;">{self.critical_date if hasattr(self, 'critical_date') else f"Sem risco em {self.forecast_days} dias"}</div>
            </div>
        </div>

        <div class="chart-container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="margin: 0;">Historico e Previsao de Crescimento</h2>
                <div class="chart-controls">
                    <button class="nav-btn" onclick="navigateChart(-1)" title="Periodo anterior">&#9664;</button>
                    <button class="zoom-btn active" onclick="setZoom('all')" data-zoom="all">Tudo</button>
                    <button class="zoom-btn" onclick="setZoom('6m')" data-zoom="6m">6 Meses</button>
                    <button class="zoom-btn" onclick="setZoom('3m')" data-zoom="3m">3 Meses</button>
                    <button class="zoom-btn" onclick="setZoom('1m')" data-zoom="1m">1 Mes</button>
                    <button class="zoom-btn" onclick="setZoom('2w')" data-zoom="2w">2 Sem</button>
                    <button class="zoom-btn" onclick="setZoom('1w')" data-zoom="1w">1 Sem</button>
                    <button class="nav-btn" onclick="navigateChart(1)" title="Proximo periodo">&#9654;</button>
                </div>
            </div>
            <canvas id="forecastChart"></canvas>
        </div>

        <div class="footer">
            Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WatcherDB Intelligence v5 (WatcherDB Data Source)<br>
            Dados coletados em: {current_info.get('data_coleta', 'N/A')} | Historico: {len(historical_data)} dias
        </div>
    </div>

    <script>
        // Dados separados: historico e previsao
        const histLabels = {json.dumps(hist_labels)};
        const histData = {json.dumps(hist_data)};
        const forecastLabels = {json.dumps([item['date'] for item in forecast])};
        const forecastData = {json.dumps([item['used_pct'] for item in forecast])};
        const currentPct = {current_info['used_pct']};
        const currentDate = '{datetime.now().strftime('%Y-%m-%d')}';
        const threshold = {self.threshold*100};

        let currentZoom = 'all';
        let currentOffset = 0;  // offset negativo = mais antigo
        let chart = null;

        // Dias por zoom (apenas para historico)
        const zoomDays = {{
            'all': 0,  // especial: mostra tudo
            '6m': 180,
            '3m': 90,
            '1m': 30,
            '2w': 14,
            '1w': 7
        }};

        function getVisibleData(zoom, offset) {{
            if (zoom === 'all') {{
                // Modo TUDO: historico completo + previsao
                const labels = [...histLabels, currentDate, ...forecastLabels];
                const hist = [...histData, currentPct, ...Array(forecastLabels.length).fill(null)];
                const forecast = [...Array(histLabels.length).fill(null), currentPct, ...forecastData];
                return {{ labels, hist, forecast, mode: 'all' }};
            }}

            // Modo zoom: apenas historico (navegavel)
            const days = zoomDays[zoom];
            const totalHist = histLabels.length;

            // offset: 0 = mais recente, negativo = mais antigo
            let end = totalHist + offset;
            let start = Math.max(0, end - days);
            end = Math.min(totalHist, start + days);

            const labels = histLabels.slice(start, end);
            const hist = histData.slice(start, end);

            return {{
                labels: labels,
                hist: hist,
                forecast: Array(labels.length).fill(null),
                mode: 'history',
                start: start,
                end: end,
                total: totalHist
            }};
        }}

        function createChart(data) {{
            const ctx = document.getElementById('forecastChart').getContext('2d');

            if (chart) {{
                chart.destroy();
            }}

            // Calcular min Y baseado nos dados visiveis
            const visibleHist = data.hist.filter(v => v !== null);
            const visibleForecast = data.forecast.filter(v => v !== null);
            const allVisible = [...visibleHist, ...visibleForecast];
            const minDataValue = allVisible.length > 0 ? Math.min(...allVisible) : 80;
            const minY = Math.max(0, Math.min(threshold - 5, minDataValue - 5));

            const datasets = [
                {{
                    label: 'Historico',
                    data: data.hist,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 3,
                    pointRadius: data.labels.length > 60 ? 2 : 4,
                    pointBackgroundColor: '#10b981',
                    tension: 0.2,
                    spanGaps: false
                }},
                {{
                    label: 'Alerta (' + threshold + '%)',
                    data: Array(data.labels.length).fill(threshold),
                    borderColor: '#eab308',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                }},
                {{
                    label: 'Estouro (100%)',
                    data: Array(data.labels.length).fill(100),
                    borderColor: '#ef4444',
                    borderWidth: 2,
                    borderDash: [2, 2],
                    pointRadius: 0,
                    fill: false
                }}
            ];

            // Adicionar previsao apenas no modo "all"
            if (data.mode === 'all') {{
                datasets.splice(1, 0, {{
                    label: 'Previsao',
                    data: data.forecast,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 3,
                    pointRadius: data.labels.length > 60 ? 2 : 4,
                    pointBackgroundColor: '#3b82f6',
                    tension: 0.2,
                    spanGaps: false
                }});
            }}

            chart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: data.labels,
                    datasets: datasets
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#cbd5e1', font: {{ size: 14 }} }}
                        }},
                        tooltip: {{
                            mode: 'index',
                            intersect: false
                        }},
                        title: {{
                            display: data.mode === 'history',
                            text: data.mode === 'history' ? 'Periodo: ' + data.labels[0] + ' a ' + data.labels[data.labels.length-1] : '',
                            color: '#94a3b8',
                            font: {{ size: 12 }}
                        }}
                    }},
                    interaction: {{
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }},
                    scales: {{
                        x: {{
                            ticks: {{
                                color: '#94a3b8',
                                maxRotation: 45,
                                minRotation: 45,
                                maxTicksLimit: data.labels.length > 60 ? 20 : 30
                            }},
                            grid: {{ color: 'rgba(148, 163, 184, 0.1)' }}
                        }},
                        y: {{
                            ticks: {{
                                color: '#94a3b8',
                                callback: function(value) {{ return value + '%'; }}
                            }},
                            grid: {{ color: 'rgba(148, 163, 184, 0.1)' }},
                            min: minY,
                            max: 100
                        }}
                    }}
                }}
            }});
        }}

        function setZoom(zoom) {{
            currentZoom = zoom;
            currentOffset = 0;  // Comecar pelo mais recente

            // Atualizar botoes ativos
            document.querySelectorAll('.zoom-btn').forEach(btn => {{
                btn.classList.remove('active');
                if (btn.dataset.zoom === zoom) btn.classList.add('active');
            }});

            const data = getVisibleData(zoom, currentOffset);
            createChart(data);
        }}

        function navigateChart(direction) {{
            if (currentZoom === 'all') return;  // Sem navegacao no modo "Tudo"

            const days = zoomDays[currentZoom];
            const totalHist = histLabels.length;
            const maxBack = -(totalHist - days);  // maximo que pode voltar

            // direction: -1 = mais antigo (volta no tempo), +1 = mais recente
            currentOffset = currentOffset + (direction * Math.ceil(days / 2));

            // Limitar navegacao
            currentOffset = Math.max(maxBack, Math.min(0, currentOffset));

            const data = getVisibleData(currentZoom, currentOffset);
            createChart(data);
        }}

        // Inicializar grafico com tudo
        const initialData = getVisibleData('all', 0);
        createChart(initialData);
    </script>
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"OK: Relatorio gerado: {html_file}")
        print(f"OK: CSV gerado: {csv_file}")

        return str(html_file), str(csv_file)


def parse_identifier(identifier_str):
    """Parse do identifier"""
    parts = {}
    for part in identifier_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            parts[key.strip()] = value.strip()
    return parts.get('Instance'), parts.get('DatabaseName'), parts.get('filegroup_name')


def main():
    if len(sys.argv) < 2:
        print("Uso: python filegroup_interactive_report_v5_watcherdb.py <identifier> [forecast_days] [threshold]")
        sys.exit(1)

    identifier = sys.argv[1]
    forecast_days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85

    instance, database, filegroup = parse_identifier(identifier)

    if not all([instance, database, filegroup]):
        print("ERRO: Identifier invalido")
        sys.exit(1)

    print(f"\\nAnalise Preditiva de Filegroup (WatcherDB Data Source)")
    print(f"Instance: {instance}")
    print(f"Database: {database}")
    print(f"Filegroup: {filegroup}\\n")

    analyzer = FilegroupForecastAnalyzerWatcherDB(instance, database, filegroup, forecast_days, threshold)

    print("Buscando informacoes do filegroup (WatcherDB)...")
    current_info = analyzer.get_filegroup_current_data()

    if not current_info:
        print("ERRO: Nao foi possivel obter dados do filegroup no WatcherDB")
        sys.exit(1)

    print(f"OK: Filegroup encontrado - {current_info['used_pct']:.1f}% usado")

    print("Calculando previsao...")
    forecast = analyzer.calculate_simple_forecast(current_info)

    if hasattr(analyzer, 'critical_day'):
        print(f"ALERTA: Atingira {threshold*100:.0f}% em {analyzer.critical_day} dias")
    else:
        print(f"OK: Nao atingira {threshold*100:.0f}% nos proximos {forecast_days} dias")

    print("\\nGerando relatorios...")
    html_path, csv_path = analyzer.generate_html_report(current_info, forecast)

    print("\\nAnalise concluida!")
    print(f"HTML: {html_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
