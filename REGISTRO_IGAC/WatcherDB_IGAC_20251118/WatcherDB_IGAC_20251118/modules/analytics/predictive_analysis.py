# -*- coding: utf-8 -*-
"""
Wrapper para análise preditiva de filegroups
Integração dos scripts standalone no TapOS
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import subprocess
import os
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PredictiveAnalyzer:
    """
    Classe que encapsula a chamada dos scripts de análise preditiva.
    Pensa nela como uma sp_generate_forecast do SQL Server, mas em Python.
    """
    
    def __init__(self, scripts_base_path: str = None):
        """
        Args:
            scripts_base_path: Caminho base onde estão os scripts (filegroup_forecast.py, etc)
                              Se None, usa o diretório raiz do projeto
        """
        if scripts_base_path is None:
            # Assume que os scripts estão na raiz do projeto
            self.base_path = Path(__file__).parent.parent.parent
            # Diretório para relatórios
            self.reports_path = self.base_path / "reports"
            # Criar diretório se não existir
            self.reports_path.mkdir(exist_ok=True)
        else:
            self.base_path = Path(scripts_base_path)
            self.reports_path = self.base_path / "reports"
            self.reports_path.mkdir(exist_ok=True)
        
        # Valida se os scripts existem
        self.forecast_script = self.base_path / "filegroup_interactive_report_v5.py"
        if not self.forecast_script.exists():
            raise FileNotFoundError(f"Script não encontrado: {self.forecast_script}")
    
    def generate_filegroup_report(
        self, 
        server_name: str,
        database_name: str,
        filegroup_name: str,
        forecast_days: int = 60,
        threshold: float = 0.85
    ) -> dict:
        """
        Gera relatório preditivo para um filegroup específico.
        
        Processo (igual ao que você já faz manualmente):
        1. Extrai dados históricos do Oracle (oracle_to_csv.py)
        2. Roda o modelo de ML (filegroup_forecast.py)
        3. Gera relatório HTML interativo (filegroup_interactive_report_v5.py)
        
        Args:
            server_name: Nome da instância SQL Server
            database_name: Nome do banco de dados
            filegroup_name: Nome do filegroup
            forecast_days: Dias para previsão (padrão: 60)
            threshold: Limite de alerta (padrão: 0.85 = 85%)
        
        Returns:
            dict com:
                - success: bool
                - html_path: caminho do relatório gerado
                - csv_path: caminho do CSV com dados históricos
                - error: mensagem de erro (se houver)
        """
        try:
            # Monta o identifier no formato esperado pelo script
            # "Instance=SERVER;DatabaseName=DB;filegroup_name=FG"
            identifier = f"Instance={server_name};DatabaseName={database_name};filegroup_name={filegroup_name}"
            
            # Comando para executar o script (igual você faz no CMD)
            cmd = [
                "python",
                str(self.forecast_script),
                identifier,
                str(forecast_days),
                str(threshold)
            ]
            
            logger.info(f"Executando análise preditiva: {' '.join(cmd)}")
            
            # Executa o script e captura output
            result = subprocess.run(
                cmd,
                cwd=str(self.base_path),  # Executa no diretório raiz
                capture_output=True,
                text=True,
                timeout=300  # 5 minutos de timeout (Oracle pode ser lento)
            )
            
            if result.returncode != 0:
                logger.error(f"Erro ao executar script: {result.stderr}")
                return {
                    "success": False,
                    "error": f"Falha na execução: {result.stderr}"
                }
            
            # Busca o arquivo HTML gerado no diretório reports
            # O script gera: interactive_{filegroup}_{timestamp}_forecast.html
            output_dir = self.reports_path
            html_files = list(output_dir.glob(f"interactive_{filegroup_name}_*_forecast.html"))
            
            if not html_files:
                return {
                    "success": False,
                    "error": "Relatório HTML não foi gerado"
                }
            
            # Pega o mais recente (caso tenha mais de um)
            latest_html = max(html_files, key=os.path.getctime)
            
            # Busca o CSV correspondente
            csv_files = list(output_dir.glob(f"interactive_{filegroup_name}_*_forecast.csv"))
            latest_csv = max(csv_files, key=os.path.getctime) if csv_files else None
            
            return {
                "success": True,
                "html_path": str(latest_html),
                "csv_path": str(latest_csv) if latest_csv else None,
                "stdout": result.stdout,
                "generated_at": datetime.now().isoformat()
            }
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout ao executar análise preditiva")
            return {
                "success": False,
                "error": "Timeout: análise demorou mais de 5 minutos"
            }
        except Exception as e:
            logger.error(f"Erro inesperado: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def read_report_html(self, html_path: str) -> str:
        """
        Lê o conteúdo do relatório HTML gerado.
        
        Args:
            html_path: Caminho completo do arquivo HTML
        
        Returns:
            str: Conteúdo HTML completo do relatório
        """
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Erro ao ler HTML: {str(e)}")
            raise


# Instância global (singleton pattern)
_analyzer = None

def get_analyzer() -> PredictiveAnalyzer:
    """
    Factory function para obter instância do analisador.
    Usa pattern singleton para não recriar a instância toda hora.
    """
    global _analyzer
    if _analyzer is None:
        _analyzer = PredictiveAnalyzer()
    return _analyzer