# INSTRUÇÕES PARA CRIAR ZIP PARA REGISTRO IGAC

## Data: 18/11/2025
## WatcherDB v1.4.8.2

---

## OPÇÃO 1: Criar ZIP Manualmente (Recomendado)

### Passo 1: Criar Pasta Temporária
1. Crie uma pasta no Desktop chamada `WatcherDB_IGAC_20251118`

### Passo 2: Copiar Arquivos
Copie os seguintes arquivos/pastas para dentro da pasta criada:

**Arquivos Raiz:**
- `watcherdb_main.py`
- `requirements.txt`

**Pastas Completas:**
- `templates/`
- `modules/`
- `api/`
- `config/`
- `documentacao/`

**Documentos IGAC:**
- `REGISTRO_IGAC\RESUMO_DESCRITIVO_WATCHERDB.md`
- `REGISTRO_IGAC\HASHES_CRIPTOGRAFICOS_WATCHERDB.txt`

### Passo 3: Criar ZIP
1. Clique com botão direito na pasta `WatcherDB_IGAC_20251118`
2. Escolha "Enviar para" → "Pasta compactada (zipada)"
3. Renomeie para: `WatcherDB_v1.4.8.2_IGAC_20251118.zip`

### Passo 4: Mover ZIP
Mova o arquivo ZIP criado para a pasta `REGISTRO_IGAC`

---

## OPÇÃO 2: Usar 7-Zip (Se instalado)

```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"

"C:\Program Files\7-Zip\7z.exe" a -tzip "REGISTRO_IGAC\WatcherDB_v1.4.8.2_IGAC_20251118.zip" watcherdb_main.py templates\ modules\ api\ config\ documentacao\ requirements.txt "REGISTRO_IGAC\RESUMO_DESCRITIVO_WATCHERDB.md" "REGISTRO_IGAC\HASHES_CRIPTOGRAFICOS_WATCHERDB.txt"
```

---

## OPÇÃO 3: Usar Python

Crie e execute o script `criar_zip.py`:

```python
import zipfile
import os
from pathlib import Path
from datetime import datetime

def criar_zip_igac():
    # Nome do ZIP
    data = datetime.now().strftime('%Y%m%d')
    nome_zip = f'WatcherDB_v1.4.8.2_IGAC_{data}.zip'
    caminho_zip = Path('REGISTRO_IGAC') / nome_zip

    # Arquivos e pastas para incluir
    itens = [
        'watcherdb_main.py',
        'requirements.txt',
        'templates',
        'modules',
        'api',
        'config',
        'documentacao',
        'REGISTRO_IGAC/RESUMO_DESCRITIVO_WATCHERDB.md',
        'REGISTRO_IGAC/HASHES_CRIPTOGRAFICOS_WATCHERDB.txt'
    ]

    print(f"Criando {nome_zip}...")

    with zipfile.ZipFile(caminho_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in itens:
            item_path = Path(item)

            if item_path.is_file():
                # Arquivo
                zipf.write(item_path, item_path.name)
                print(f"  [OK] {item}")

            elif item_path.is_dir():
                # Pasta
                for root, dirs, files in os.walk(item_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(item_path.parent)
                        zipf.write(file_path, arcname)
                        print(f"  [OK] {arcname}")

    # Informações do ZIP
    tamanho = caminho_zip.stat().st_size
    tamanho_mb = tamanho / (1024 * 1024)

    print(f"\nZIP criado com sucesso!")
    print(f"Nome: {nome_zip}")
    print(f"Tamanho: {tamanho_mb:.2f} MB ({tamanho:,} bytes)")
    print(f"Caminho: {caminho_zip.absolute()}")

    # Gerar hash
    import hashlib
    with open(caminho_zip, 'rb') as f:
        hash_sha256 = hashlib.sha256(f.read()).hexdigest().upper()

    print(f"SHA256: {hash_sha256}")

    return caminho_zip

if __name__ == '__main__':
    criar_zip_igac()
```

Execute:
```bash
cd "C:\Users\ue_e-snetto\Documents\TAP - SALOMAO\Python\TAP_DIAGNOSTICS_ENHANCED_analysis\WATCHERDB_DEV"
python criar_zip.py
```

---

## CONTEÚDO DO ZIP

O ZIP deve conter:

```
WatcherDB_v1.4.8.2_IGAC_20251118/
├── watcherdb_main.py
├── requirements.txt
├── RESUMO_DESCRITIVO_WATCHERDB.md
├── HASHES_CRIPTOGRAFICOS_WATCHERDB.txt
├── templates/
│   └── watcherdb_portal.html
├── modules/
│   ├── monitoring/
│   │   ├── queries.py
│   │   ├── space_analysis.py
│   │   ├── backup_analysis.py
│   │   ├── cpu_analysis.py
│   │   ├── memory_analysis.py
│   │   └── ...
│   └── analytics/
│       └── predictive_analysis.py
├── api/
│   └── routers/
│       ├── sql_queries.py
│       ├── diagnostics_overview.py
│       └── ...
├── config/
│   ├── sql_servers.json
│   └── alwayson_inventory.json
└── documentacao/
    ├── CHANGELOG.md
    ├── PARAMETRIZACAO_v1.4.8.1.md
    ├── PING_OPTIMIZATION_v1.4.8.2.md
    ├── SPACE_FIXES_v1.4.8.2.md
    └── ...
```

---

## VERIFICAÇÃO DO ZIP

Após criar o ZIP, verifique:

1. **Tamanho:** Deve ter aproximadamente 1-2 MB
2. **Arquivos:** Deve conter ~70-100 arquivos
3. **Pastas:** Deve ter as 5 pastas principais (templates, modules, api, config, documentacao)
4. **Documentos IGAC:** Deve conter os 2 documentos (RESUMO e HASHES)

---

## PRÓXIMOS PASSOS

Após criar o ZIP:

1. Gerar hash SHA256 do arquivo ZIP
2. Preencher formulário do IGAC online
3. Anexar:
   - `RESUMO_DESCRITIVO_WATCHERDB.md`
   - `HASHES_CRIPTOGRAFICOS_WATCHERDB.txt`
   - `WatcherDB_v1.4.8.2_IGAC_20251118.zip`
4. Submeter registro

---

**NOTA:** O ZIP deve ser criado com compressão DEFLATE (padrão) para garantir
compatibilidade máxima com os sistemas do IGAC.
