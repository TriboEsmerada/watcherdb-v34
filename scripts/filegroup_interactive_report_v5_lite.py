"""
FILEGROUP INTERACTIVE REPORT - WATCHERDB v5 LITE
Versão simplificada sem dependências de pandas/numpy

Uso:
    python filegroup_interactive_report_v5_lite.py "Instance=SERVER;DatabaseName=DB;filegroup_name=FG" [forecast_days] [threshold]
"""

import sys
import os
import pyodbc
from datetime import datetime, timedelta
from pathlib import Path
import json

class FilegroupForecastAnalyzerLite:
    """Analisador simplificado sem pandas"""

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

    def get_sql_connection(self, timeout=30):
        """Conecta ao SQL Server"""
        try:
            # Converter formato do dashboard (SERVER_IXXXX) para SQL Server (SERVER\IXXXX)
            server = self.instance

            # Se formato: SQLHDSPRD005_I0003 -> SQLHDSPRD005\I0003
            if '_I' in server and '\\' not in server:
                parts = server.split('_I')
                server = f"{parts[0]}\\I{parts[1]}"

            # Forcar TCP/IP ao inves de Named Pipes
            # Adicionar ,1433 se nao tiver porta especificada
            if ',' not in server and '\\' in server:
                # Formato: SERVER\INSTANCE -> SERVER\INSTANCE,1433
                server = f"{server},1433"

            conn_str = (
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={server};'
                f'DATABASE={self.database};'
                f'Trusted_Connection=yes;'
                f'Connection Timeout={timeout};'
                f'Network=dbmssocn;'  # Forcar TCP/IP
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            raise Exception(f"Erro ao conectar no SQL Server {self.instance}: {e}")

    def get_filegroup_info(self):
        """Busca informações atuais do filegroup"""
        conn = self.get_sql_connection()

        try:
            query = f"""
            SELECT
                fg.name AS FileGroup,
                SUM(CAST(f.size AS BIGINT) * 8 / 1024.0) AS Size_MB,
                SUM(CAST(FILEPROPERTY(f.name, 'SpaceUsed') AS BIGINT) * 8 / 1024.0) AS Used_MB,
                (SUM(CAST(FILEPROPERTY(f.name, 'SpaceUsed') AS BIGINT)) * 100.0 /
                 NULLIF(SUM(CAST(f.size AS BIGINT)), 0)) AS Used_Pct
            FROM sys.database_files f
            INNER JOIN sys.filegroups fg ON f.data_space_id = fg.data_space_id
            WHERE fg.name = '{self.filegroup}'
            GROUP BY fg.name
            """

            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                'filegroup': row[0],
                'size_mb': float(row[1]),
                'used_mb': float(row[2]),
                'used_pct': float(row[3]) if row[3] else 0
            }

        except Exception as e:
            print(f"ERRO: {e}")
            if conn:
                conn.close()
            return None

    def calculate_simple_forecast(self, current_info):
        """Calcula previsão simples baseada em crescimento linear"""
        # Assume crescimento de 1% ao dia (estimativa conservadora)
        daily_growth_pct = 1.0

        current_pct = current_info['used_pct']
        threshold_pct = self.threshold * 100

        forecast = []
        for day in range(1, self.forecast_days + 1):
            forecast_pct = current_pct + (daily_growth_pct * day)
            forecast_pct = min(forecast_pct, 100)  # Não ultrapassa 100%

            forecast.append({
                'day': day,
                'date': (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d'),
                'used_pct': forecast_pct
            })

            if forecast_pct >= threshold_pct and not hasattr(self, 'critical_day'):
                self.critical_day = day
                self.critical_date = (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d')

        return forecast

    def generate_html_report(self, current_info, forecast):
        """Gera relatório HTML"""

        base_name = f"interactive_{self.filegroup}_{self.timestamp}_forecast"
        html_file = self.reports_path / f"{base_name}.html"
        csv_file = self.reports_path / f"{base_name}.csv"

        # CSV
        with open(csv_file, 'w') as f:
            f.write("Day,Date,Used_Pct\n")
            f.write(f"0,{datetime.now().strftime('%Y-%m-%d')},{current_info['used_pct']:.2f}\n")
            for item in forecast:
                f.write(f"{item['day']},{item['date']},{item['used_pct']:.2f}\n")

        # Status
        if hasattr(self, 'critical_day'):
            days_until = self.critical_day
            status_color = "red" if days_until < 30 else "orange" if days_until < 60 else "green"
            status_text = f"ALERTA: Atingira {self.threshold*100:.0f}% em {days_until} dias ({self.critical_date})"
        else:
            status_color = "green"
            status_text = f"OK: Nao atingira {self.threshold*100:.0f}% nos proximos {self.forecast_days} dias"

        # Dados para Chart.js
        chart_labels = [datetime.now().strftime('%Y-%m-%d')] + [item['date'] for item in forecast]
        chart_data = [current_info['used_pct']] + [item['used_pct'] for item in forecast]

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
            background: {'#7f1d1d' if status_color == 'red' else '#78350f' if status_color == 'orange' else '#064e3b'};
            border-left: 4px solid {'#dc2626' if status_color == 'red' else '#f59e0b' if status_color == 'orange' else '#10b981'};
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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Analise Preditiva de Crescimento</h1>
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
                <div class="value">{current_info['size_mb']:.2f} MB</div>
            </div>
            <div class="info-card">
                <h3>Uso Atual</h3>
                <div class="value">{current_info['used_mb']:.2f} MB</div>
            </div>
            <div class="info-card">
                <h3>% Usado Atual</h3>
                <div class="value">{current_info['used_pct']:.1f}%</div>
            </div>
            <div class="info-card">
                <h3>Dias de Previsao</h3>
                <div class="value">{self.forecast_days}</div>
            </div>
        </div>

        <div class="chart-container">
            <h2>Crescimento Previsto (Estimativa Linear)</h2>
            <canvas id="forecastChart"></canvas>
        </div>

        <div class="footer">
            Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WatcherDB Intelligence v5 Lite
        </div>
    </div>

    <script>
        const ctx = document.getElementById('forecastChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(chart_labels)},
                datasets: [
                    {{
                        label: 'Previsao',
                        data: {json.dumps(chart_data)},
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        pointRadius: 4,
                        tension: 0.4
                    }},
                    {{
                        label: 'Threshold ({self.threshold*100:.0f}%)',
                        data: Array({len(chart_labels)}).fill({self.threshold*100}),
                        borderColor: '#dc2626',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: true,
                plugins: {{
                    legend: {{
                        labels: {{ color: '#cbd5e1', font: {{ size: 14 }} }}
                    }}
                }},
                scales: {{
                    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: 'rgba(148, 163, 184, 0.1)' }} }},
                    y: {{
                        ticks: {{
                            color: '#94a3b8',
                            callback: function(value) {{ return value + '%'; }}
                        }},
                        grid: {{ color: 'rgba(148, 163, 184, 0.1)' }}
                    }}
                }}
            }}
        }});
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
        print("Uso: python filegroup_interactive_report_v5_lite.py <identifier> [forecast_days] [threshold]")
        sys.exit(1)

    identifier = sys.argv[1]
    forecast_days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85

    instance, database, filegroup = parse_identifier(identifier)

    if not all([instance, database, filegroup]):
        print("ERRO: Identifier invalido")
        sys.exit(1)

    print(f"\nAnalise Preditiva de Filegroup (LITE)")
    print(f"Instance: {instance}")
    print(f"Database: {database}")
    print(f"Filegroup: {filegroup}\n")

    analyzer = FilegroupForecastAnalyzerLite(instance, database, filegroup, forecast_days, threshold)

    print("Buscando informacoes do filegroup...")
    current_info = analyzer.get_filegroup_info()

    if not current_info:
        print("ERRO: Nao foi possivel obter dados do filegroup")
        sys.exit(1)

    print(f"OK: Filegroup encontrado - {current_info['used_pct']:.1f}% usado")

    print("Calculando previsao...")
    forecast = analyzer.calculate_simple_forecast(current_info)

    if hasattr(analyzer, 'critical_day'):
        print(f"ALERTA: Atingira {threshold*100:.0f}% em {analyzer.critical_day} dias")
    else:
        print(f"OK: Nao atingira {threshold*100:.0f}% nos proximos {forecast_days} dias")

    print("\nGerando relatorios...")
    html_path, csv_path = analyzer.generate_html_report(current_info, forecast)

    print("\nAnalise concluida!")
    print(f"HTML: {html_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
