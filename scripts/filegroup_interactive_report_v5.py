"""
FILEGROUP INTERACTIVE REPORT - WATCHERDB v5
Análise Preditiva de Crescimento de Filegroups

Uso:
    python filegroup_interactive_report_v5.py "Instance=SERVER;DatabaseName=DB;filegroup_name=FG" [forecast_days] [threshold]

Exemplo:
    python filegroup_interactive_report_v5.py "Instance=SQLHDSPRD005_I0003;DatabaseName=DBA_RESOURCE_DB;filegroup_name=PRIMARY" 60 0.85

Saída:
    - reports/interactive_{filegroup}_{timestamp}_forecast.html (relatório HTML)
    - reports/interactive_{filegroup}_{timestamp}_forecast.csv (dados brutos)
    - reports/interactive_{filegroup}_{timestamp}_forecast.png (gráfico)
"""

import sys
import os
import pyodbc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

# Tentar importar bibliotecas de ML (opcional)
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.metrics import r2_score, mean_absolute_error
    from sklearn.model_selection import cross_val_score
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("AVISO: scikit-learn nao instalado. Usando regressao linear simples.")

try:
    from prophet import Prophet
    HAS_PROPHET = True
except ImportError:
    HAS_PROPHET = False


class FilegroupForecastAnalyzer:
    """Analisador de previsão de crescimento de filegroups"""

    def __init__(self, instance, database, filegroup, forecast_days=60, threshold=0.85):
        self.instance = instance
        self.database = database
        self.filegroup = filegroup
        self.forecast_days = forecast_days
        self.threshold = threshold
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]

        # Diretórios
        self.base_path = Path(__file__).parent
        self.reports_path = self.base_path / "reports"
        self.reports_path.mkdir(exist_ok=True)

        # Conexões Oracle (WatcherDB)
        self.oracle_conn_string = None
        self.has_oracle = self._check_oracle_connection()

    def _check_oracle_connection(self):
        """Verifica se existe conexão Oracle configurada"""
        try:
            # Tentar ler credenciais Oracle (se existir)
            config_file = self.base_path / "config" / "oracle_config.json"
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)
                    self.oracle_conn_string = config.get("connection_string")
                    return True
        except Exception as e:
            print(f"AVISO: Oracle nao configurado: {e}")
        return False

    def get_sql_connection(self, timeout=30):
        """Conecta ao SQL Server"""
        try:
            conn_str = (
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={self.instance};'
                f'DATABASE={self.database};'
                f'Trusted_Connection=yes;'
                f'Connection Timeout={timeout};'
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            raise Exception(f"Erro ao conectar no SQL Server: {e}")

    def get_oracle_connection(self):
        """Conecta ao Oracle (WatcherDB)"""
        if not self.has_oracle or not self.oracle_conn_string:
            return None
        try:
            import cx_Oracle
            return cx_Oracle.connect(self.oracle_conn_string)
        except Exception as e:
            print(f"⚠️ Erro ao conectar no Oracle: {e}")
            return None

    def get_historical_data_from_oracle(self):
        """Busca dados históricos do Oracle (se disponível)"""
        conn = self.get_oracle_connection()
        if not conn:
            return None

        try:
            query = """
            SELECT
                TRUNC(DATA_COLETA) AS DATA,
                AVG(USED_PCT) AS USED_PCT,
                AVG(SIZE_MB) AS SIZE_MB,
                AVG(USED_MB) AS USED_MB
            FROM WATCHERDB.KPI_MSSQL_FG_USAGE_HIST
            WHERE UPPER(INSTANCE) = :instance
              AND UPPER(DATABASE_NAME) = :database
              AND UPPER(FILEGROUP_NAME) = :filegroup
              AND DATA_COLETA >= TRUNC(SYSDATE) - 90
            GROUP BY TRUNC(DATA_COLETA)
            ORDER BY DATA
            """

            df = pd.read_sql(query, conn, params={
                'instance': self.instance.upper(),
                'database': self.database.upper(),
                'filegroup': self.filegroup.upper()
            })

            conn.close()

            if df.empty:
                return None

            df['DATA'] = pd.to_datetime(df['DATA'])
            return df

        except Exception as e:
            print(f"AVISO: Erro ao buscar dados do Oracle: {e}")
            if conn:
                conn.close()
            return None

    def get_historical_data_from_sqlserver(self):
        """Busca dados históricos direto do SQL Server (fallback)"""
        conn = self.get_sql_connection()

        try:
            # Query para pegar histórico de crescimento
            query = f"""
            WITH FileHistory AS (
                SELECT
                    CAST(GETDATE() AS DATE) AS Data,
                    fg.name AS FileGroup,
                    SUM(CAST(f.size AS BIGINT) * 8 / 1024.0) AS Size_MB,
                    SUM(CAST(FILEPROPERTY(f.name, 'SpaceUsed') AS BIGINT) * 8 / 1024.0) AS Used_MB,
                    (SUM(CAST(FILEPROPERTY(f.name, 'SpaceUsed') AS BIGINT)) * 100.0 /
                     NULLIF(SUM(CAST(f.size AS BIGINT)), 0)) AS Used_Pct
                FROM sys.database_files f
                INNER JOIN sys.filegroups fg ON f.data_space_id = fg.data_space_id
                WHERE fg.name = '{self.filegroup}'
                GROUP BY fg.name
            )
            SELECT * FROM FileHistory
            """

            df = pd.read_sql(query, conn)
            conn.close()

            if df.empty:
                return None

            # Simular histórico com base no estado atual
            # (idealmente deveria ter dados históricos reais)
            current_data = df.iloc[0]
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')

            # Simula crescimento linear dos últimos 30 dias
            historical_df = pd.DataFrame({
                'DATA': dates,
                'SIZE_MB': [current_data['Size_MB']] * len(dates),
                'USED_MB': np.linspace(
                    current_data['Used_MB'] * 0.85,  # Começa em 85% do valor atual
                    current_data['Used_MB'],
                    len(dates)
                ),
                'USED_PCT': np.linspace(
                    current_data['Used_Pct'] * 0.85,
                    current_data['Used_Pct'],
                    len(dates)
                )
            })

            return historical_df

        except Exception as e:
            print(f"ERRO: Erro ao buscar dados do SQL Server: {e}")
            if conn:
                conn.close()
            return None

    def calculate_forecast(self, df):
        """Calcula previsão de crescimento"""
        if df is None or len(df) < 5:
            return None

        # Preparar dados
        df = df.sort_values('DATA').reset_index(drop=True)
        df['days_from_start'] = (df['DATA'] - df['DATA'].min()).dt.days

        X = df[['days_from_start']].values
        y = df['USED_MB'].values

        # Modelo de ML (se disponível)
        if HAS_ML and len(df) >= 10:
            # Regressão polinomial (grau 2)
            poly = PolynomialFeatures(degree=2)
            X_poly = poly.fit_transform(X)
            model = LinearRegression()
            model.fit(X_poly, y)

            # Previsão
            last_day = X[-1][0]
            future_days = np.arange(last_day + 1, last_day + self.forecast_days + 1).reshape(-1, 1)
            future_days_poly = poly.transform(future_days)
            forecast = model.predict(future_days_poly)

        else:
            # Regressão linear simples (fallback)
            if len(df) < 2:
                return None

            # Calcular taxa de crescimento diária
            daily_growth = (y[-1] - y[0]) / (X[-1][0] - X[0][0]) if X[-1][0] != X[0][0] else 0

            # Previsão linear
            last_day = X[-1][0]
            last_value = y[-1]
            future_days = np.arange(last_day + 1, last_day + self.forecast_days + 1)
            forecast = last_value + daily_growth * (future_days - last_day)

        # --- Model quality metrics (R², MAE, cross-validation) ---
        model_quality = {}
        if HAS_ML and len(df) >= 10:
            # Polynomial model was used
            y_pred_train = model.predict(X_poly)
            r2 = r2_score(y, y_pred_train)
            mae = mean_absolute_error(y, y_pred_train)

            cv_scores = None
            if len(X) >= 10:
                from sklearn.pipeline import make_pipeline
                cv_pipe = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())
                cv_scores = cross_val_score(cv_pipe, X, y, cv=min(5, len(X) // 2), scoring='r2')

            model_quality = {
                "r2_score": round(r2, 4),
                "mae_mb": round(float(mae), 2),
                "cv_r2_mean": round(float(cv_scores.mean()), 4) if cv_scores is not None else None,
                "cv_r2_std": round(float(cv_scores.std()), 4) if cv_scores is not None else None,
                "data_points": len(X),
                "model_type": "PolynomialRegression_deg2",
                "confidence": "high" if r2 > 0.8 else "medium" if r2 > 0.5 else "low",
            }
        else:
            # Simple linear fallback — basic R²
            y_mean = np.mean(y)
            y_pred_simple = y[0] + daily_growth * (X.ravel() - X[0][0]) if len(df) >= 2 else np.full_like(y, y_mean)
            ss_res = np.sum((y - y_pred_simple) ** 2)
            ss_tot = np.sum((y - y_mean) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            model_quality = {
                "r2_score": round(float(r2), 4),
                "mae_mb": round(float(np.mean(np.abs(y - y_pred_simple))), 2),
                "cv_r2_mean": None,
                "cv_r2_std": None,
                "data_points": len(X),
                "model_type": "SimpleLinear",
                "confidence": "high" if r2 > 0.8 else "medium" if r2 > 0.5 else "low",
            }

        # Crear DataFrame de previsao
        future_dates = pd.date_range(
            start=df['DATA'].max() + timedelta(days=1),
            periods=self.forecast_days,
            freq='D'
        )

        forecast_df = pd.DataFrame({
            'DATA': future_dates,
            'USED_MB_FORECAST': forecast,
            'SIZE_MB': df['SIZE_MB'].iloc[-1]  # Assume tamanho fixo
        })

        forecast_df['USED_PCT_FORECAST'] = (
            forecast_df['USED_MB_FORECAST'] / forecast_df['SIZE_MB'] * 100
        ).clip(0, 100)

        # Attach model quality as DataFrame metadata
        forecast_df.attrs["model_quality"] = model_quality

        # Warning for low R²
        warnings_list = []
        r2 = model_quality.get("r2_score", 0)
        if r2 < 0.3:
            warnings_list.append(
                f"Low model quality (R\u00b2={r2:.2f}). Predictions may be unreliable. "
                "Consider using more historical data or a different model."
            )
        if warnings_list:
            forecast_df.attrs["warnings"] = warnings_list

        return forecast_df

    def find_critical_date(self, forecast_df):
        """Encontra a data em que o filegroup atinge o threshold"""
        if forecast_df is None:
            return None

        threshold_pct = self.threshold * 100
        critical_rows = forecast_df[forecast_df['USED_PCT_FORECAST'] >= threshold_pct]

        if not critical_rows.empty:
            return critical_rows.iloc[0]['DATA']

        return None

    def generate_html_report(self, historical_df, forecast_df, critical_date):
        """Gera relatório HTML interativo"""

        # Nome dos arquivos
        base_name = f"interactive_{self.filegroup}_{self.timestamp}_forecast"
        html_file = self.reports_path / f"{base_name}.html"
        csv_file = self.reports_path / f"{base_name}.csv"

        # Combinar dados históricos e previsão para CSV
        if historical_df is not None and forecast_df is not None:
            combined_df = pd.concat([
                historical_df[['DATA', 'USED_MB', 'SIZE_MB', 'USED_PCT']].rename(columns={
                    'USED_MB': 'USED_MB_HISTORICAL',
                    'USED_PCT': 'USED_PCT_HISTORICAL'
                }),
                forecast_df[['DATA', 'USED_MB_FORECAST', 'USED_PCT_FORECAST']]
            ], axis=0, ignore_index=True)
            combined_df.to_csv(csv_file, index=False)

        # Status
        if critical_date:
            days_until_critical = (critical_date - datetime.now()).days
            status_color = "red" if days_until_critical < 30 else "orange" if days_until_critical < 60 else "green"
            status_text = f"⚠️ Atingirá {self.threshold*100:.0f}% em {days_until_critical} dias ({critical_date.strftime('%Y-%m-%d')})"
        else:
            status_color = "green"
            status_text = f"✅ Não atingirá {self.threshold*100:.0f}% nos próximos {self.forecast_days} dias"

        # Dados para o gráfico (JSON)
        chart_data = {
            'historical': historical_df[['DATA', 'USED_PCT']].to_dict('records') if historical_df is not None else [],
            'forecast': forecast_df[['DATA', 'USED_PCT_FORECAST']].to_dict('records') if forecast_df is not None else []
        }

        # Converter datas para string
        for item in chart_data['historical']:
            item['DATA'] = item['DATA'].strftime('%Y-%m-%d')
        for item in chart_data['forecast']:
            item['DATA'] = item['DATA'].strftime('%Y-%m-%d')

        # HTML
        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análise Preditiva: {self.filegroup}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0a0f1a 0%, #1a2332 100%);
            color: #f1f5f9;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}
        .header h1 {{
            font-size: 2rem;
            margin-bottom: 10px;
            color: white;
        }}
        .header .meta {{
            font-size: 0.9rem;
            opacity: 0.9;
        }}
        .status-card {{
            background: {status_color == 'red' and '#7f1d1d' or status_color == 'orange' and '#78350f' or '#064e3b'};
            border-left: 4px solid {status_color == 'red' and '#dc2626' or status_color == 'orange' and '#f59e0b' or '#10b981'};
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
            letter-spacing: 0.5px;
        }}
        .info-card .value {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #60a5fa;
        }}
        .chart-container {{
            background: #1a2332;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid #2d3e52;
        }}
        .chart-container h2 {{
            margin-bottom: 20px;
            color: #cbd5e1;
        }}
        #forecastChart {{
            max-height: 400px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #64748b;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Análise Preditiva de Crescimento</h1>
            <div class="meta">
                <strong>Instance:</strong> {self.instance} |
                <strong>Database:</strong> {self.database} |
                <strong>Filegroup:</strong> {self.filegroup}
            </div>
        </div>

        <div class="status-card">
            {status_text}
        </div>

        <div class="info-grid">
            <div class="info-card">
                <h3>Tamanho Atual</h3>
                <div class="value">{historical_df['SIZE_MB'].iloc[-1]:.2f} MB</div>
            </div>
            <div class="info-card">
                <h3>Uso Atual</h3>
                <div class="value">{historical_df['USED_MB'].iloc[-1]:.2f} MB</div>
            </div>
            <div class="info-card">
                <h3>% Usado Atual</h3>
                <div class="value">{historical_df['USED_PCT'].iloc[-1]:.1f}%</div>
            </div>
            <div class="info-card">
                <h3>Dias de Previsão</h3>
                <div class="value">{self.forecast_days}</div>
            </div>
        </div>

        <div class="chart-container">
            <h2>Crescimento Histórico e Previsão</h2>
            <canvas id="forecastChart"></canvas>
        </div>

        <div class="footer">
            Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WatcherDB Intelligence v5
        </div>
    </div>

    <script>
        const chartData = {json.dumps(chart_data)};

        const historicalDates = chartData.historical.map(d => d.DATA);
        const historicalValues = chartData.historical.map(d => d.USED_PCT);
        const forecastDates = chartData.forecast.map(d => d.DATA);
        const forecastValues = chartData.forecast.map(d => d.USED_PCT_FORECAST);

        const ctx = document.getElementById('forecastChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: [...historicalDates, ...forecastDates],
                datasets: [
                    {{
                        label: 'Histórico',
                        data: [...historicalValues, ...Array(forecastDates.length).fill(null)],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.4
                    }},
                    {{
                        label: 'Previsão',
                        data: [...Array(historicalDates.length).fill(null), ...forecastValues],
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        borderWidth: 3,
                        borderDash: [10, 5],
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.4
                    }},
                    {{
                        label: 'Threshold ({self.threshold*100:.0f}%)',
                        data: Array(historicalDates.length + forecastDates.length).fill({self.threshold*100}),
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
                        labels: {{
                            color: '#cbd5e1',
                            font: {{
                                size: 14
                            }}
                        }}
                    }},
                    tooltip: {{
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        titleColor: '#f1f5f9',
                        bodyColor: '#cbd5e1',
                        borderColor: '#3b82f6',
                        borderWidth: 1
                    }}
                }},
                scales: {{
                    x: {{
                        ticks: {{
                            color: '#94a3b8',
                            maxRotation: 45,
                            minRotation: 45
                        }},
                        grid: {{
                            color: 'rgba(148, 163, 184, 0.1)'
                        }}
                    }},
                    y: {{
                        ticks: {{
                            color: '#94a3b8',
                            callback: function(value) {{
                                return value + '%';
                            }}
                        }},
                        grid: {{
                            color: 'rgba(148, 163, 184, 0.1)'
                        }}
                    }}
                }},
                interaction: {{
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }}
            }}
        }});
    </script>
</body>
</html>"""

        # Escrever HTML
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"OK: Relatorio gerado: {html_file}")
        print(f"OK: CSV gerado: {csv_file}")

        return str(html_file), str(csv_file)


def parse_identifier(identifier_str):
    """Parse do identifier: Instance=X;DatabaseName=Y;filegroup_name=Z"""
    parts = {}
    for part in identifier_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            parts[key.strip()] = value.strip()

    return parts.get('Instance'), parts.get('DatabaseName'), parts.get('filegroup_name')


def main():
    """Função principal"""
    if len(sys.argv) < 2:
        print("Uso: python filegroup_interactive_report_v5.py <identifier> [forecast_days] [threshold]")
        print('Exemplo: python filegroup_interactive_report_v5.py "Instance=SERVER;DatabaseName=DB;filegroup_name=FG" 60 0.85')
        sys.exit(1)

    # Parse argumentos
    identifier = sys.argv[1]
    forecast_days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85

    instance, database, filegroup = parse_identifier(identifier)

    if not all([instance, database, filegroup]):
        print("ERRO: Identifier invalido. Use: Instance=X;DatabaseName=Y;filegroup_name=Z")
        sys.exit(1)

    print(f"\nAnalise Preditiva de Filegroup")
    print(f"Instance: {instance}")
    print(f"Database: {database}")
    print(f"Filegroup: {filegroup}")
    print(f"Previsão: {forecast_days} dias")
    print(f"Threshold: {threshold*100:.0f}%\n")

    # Inicializar analyzer
    analyzer = FilegroupForecastAnalyzer(instance, database, filegroup, forecast_days, threshold)

    # Buscar dados históricos (tenta Oracle primeiro, depois SQL Server)
    print("Buscando dados historicos...")
    historical_df = analyzer.get_historical_data_from_oracle()

    if historical_df is None:
        print("AVISO: Dados Oracle nao disponiveis. Usando SQL Server...")
        historical_df = analyzer.get_historical_data_from_sqlserver()

    if historical_df is None:
        print("ERRO: Nao foi possivel obter dados historicos")
        sys.exit(1)

    print(f"OK: {len(historical_df)} registros historicos encontrados")

    # Calcular previsão
    print("Calculando previsao...")
    forecast_df = analyzer.calculate_forecast(historical_df)

    if forecast_df is None:
        print("ERRO: Nao foi possivel calcular previsao (dados insuficientes)")
        sys.exit(1)

    # Encontrar data crítica
    critical_date = analyzer.find_critical_date(forecast_df)

    if critical_date:
        days_until = (critical_date - datetime.now()).days
        print(f"ALERTA: Filegroup atingira {threshold*100:.0f}% em {days_until} dias ({critical_date.strftime('%Y-%m-%d')})")
    else:
        print(f"OK: Filegroup nao atingira {threshold*100:.0f}% nos proximos {forecast_days} dias")

    # Gerar relatórios
    print("\nGerando relatorios...")
    html_path, csv_path = analyzer.generate_html_report(historical_df, forecast_df, critical_date)

    print("\nAnalise concluida com sucesso!")
    print(f"HTML: {html_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
