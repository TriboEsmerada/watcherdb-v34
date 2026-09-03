import sys, subprocess
from pathlib import Path
import pandas as pd

servername = ["SQLIDSPRD03\\I01", "SQLIDSPRD04\\I01"]
databasename = ["DW_TAP", "DW_TAP"]
filegroupname = ["FG_DW_TAP_ATH_BKDREV_IDX", "FG_DW_TAP_ATRM_DAT"]

exec_df = pd.DataFrame({
    "ServerName": servername,
    "DatabaseName": databasename,
    "FilegroupName": filegroupname
})

# normaliza nome da coluna de servidor
server_col = 'ServerName' if 'ServerName' in exec_df.columns else ('Server' if 'Server' in exec_df.columns else None)
if server_col is None:
    raise KeyError("Não encontrei coluna de servidor ('Server' ou 'ServerName') no DataFrame.")

# filtra apenas em risco, se existir a coluna
if 'EmRisco97' in exec_df.columns:
    exec_df['EmRisco97'] = pd.to_numeric(exec_df['EmRisco97'], errors='coerce').fillna(0).astype(int)
    exec_df = exec_df[exec_df['EmRisco97'] == 1]

# valida colunas obrigatórias
required = [server_col, 'DatabaseName', 'FilegroupName']
missing = [c for c in required if c not in exec_df.columns]
if missing:
    raise KeyError(f"Faltam colunas no DataFrame: {missing}")

# limpa valores vazios
for c in required:
    exec_df[c] = exec_df[c].astype(str).str.strip()
exec_df = exec_df[(exec_df[server_col] != '') & (exec_df['DatabaseName'] != '') & (exec_df['FilegroupName'] != '')]

# evita duplicatas
exec_df = exec_df.drop_duplicates(subset=required)

if exec_df.empty:
    print("Nenhum registro para executar o relatório interativo.")
else:
    # caminho do script e diretório de trabalho
    script_path = Path(__file__).parent / "filegroup_interactive_report_v5_watcherdb.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Script não encontrado: {script_path}")
    workdir = script_path.parent  # garante cwd igual ao do script

    print(f"Executando {len(exec_df)} chamada(s) usando {script_path} ...")

    def run_report(server_name, database_name, filegroup_name, horizon="60", threshold="0.85"):
        # ATENÇÃO: filegroup_name deve ser APENAS o nome do FG (sem prefixo do database)
        config_arg = f"Instance={server_name};DatabaseName={database_name};filegroup_name={filegroup_name}"

        # chama com a mesma sintaxe que funciona no terminal
        args = [sys.executable, str(script_path), config_arg, str(horizon), str(threshold)]
        print(f"\n-> Iniciando: {args}")

        proc = subprocess.run(args, cwd=str(workdir), text=True, capture_output=True)
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)

        return proc.returncode == 0

    ok, fail = 0, 0
    for idx, row in exec_df.iterrows():
        srv = row[server_col]
        db  = row['DatabaseName']
        fg  = row['FilegroupName']          # sem prefixar o database!

        print(f"\n[{idx}] Server={srv} | DB={db} | FG={fg}")
        if run_report(srv, db, fg, "60", "0.85"):  # Usando 60 dias de previsão
            print("✅ Concluído.")
            ok += 1
        else:
            print("❌ Falhou.")
            fail += 1

    print(f"\nResumo: {ok} sucesso(s), {fail} falha(s).")
