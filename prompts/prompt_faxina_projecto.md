# Prompt: Faxina e Organização de Projecto Python/FastAPI

**Objectivo:** Limpar, organizar e estruturar um projecto de software, eliminando ficheiros desnecessários e organizando a documentação.

---

## Prompt para o Claude

```
Assume o papel de um Engenheiro de Software Senior especializado em organização de projectos e code hygiene.

Preciso que faças uma faxina completa no projecto neste directório.

### FASE 1 — BACKUP
Antes de qualquer alteração, cria um backup completo do projecto com o sufixo _BACKUP_PREFAXINA.

### FASE 2 — INVENTÁRIO COMPLETO
Faz um inventário exaustivo de TODOS os ficheiros do projecto:

1. **Lista todos os ficheiros na raiz** e classifica cada um como:
   - MANTER — parte activa da aplicação
   - ELIMINAR — script one-off, duplicado, temporário, gerado
   - MOVER — ficheiro no sítio errado (ex: test_*.py na raiz em vez de tests/)

2. **Para cada script Python na raiz** (_add_*.py, fix_*.py, find_*.py, verify_*.py, check_*.py, setup_*.py, etc.):
   - Lê as primeiras 10 linhas para perceber o que faz
   - Verifica se é importado por algum outro ficheiro: `grep -rn "import filename"`
   - Se não é referenciado → candidato a ELIMINAR

3. **Verifica estes directórios** para conteúdo dispensável:
   - htmlcov/ (cobertura gerada — regenerável)
   - reports/ (relatórios gerados — regeneráveis)
   - logs/ (logs de runtime)
   - *_backup/ (backups internos)
   - Ficheiros .bak, .backup, .bak_*, .old
   - Ficheiros .log, .exe, .coverage na raiz
   - Ficheiros temp_*, resultado_*.txt, *.exe

4. **Conta ficheiros por extensão:** .py, .html, .js, .css, .md, .sql, .ps1, .bat, .json, .yaml, .log, .exe

### FASE 3 — LIMPEZA
Após mostrar o inventário e obter aprovação:

1. **Elimina** todos os ficheiros classificados como ELIMINAR
2. **Move test_*.py avulsos** para tests/integration/
3. **Move scripts de utilidade** (filegroup reports, etc.) para scripts/
4. **Move .sql avulsos** para database/
5. **Limpa directórios gerados** (htmlcov/, reports/, __pycache__/)
6. **Remove .bak/.backup** e actualiza .gitignore com os patterns

### FASE 4 — ORGANIZAÇÃO DA DOCUMENTAÇÃO
Organiza a pasta docs/ em subpastas temáticas:

```
docs/
├── architecture/     — Design system, diagramas, lógica de negócio
├── audit/            — Auditorias técnicas, remediações, comparativos
├── bugfixes/         — Correcções de bugs, diagnósticos, hotfixes
├── changelog/        — Histórico de alterações, release notes
├── deployment/       — Quickstart, migration, instalação, restart
├── features/         — Documentação de features (cluster, backup, jobs, etc.)
├── guides/           — Manual do utilizador, referência técnica, prompts
├── security/         — Segurança, encriptação, compliance
├── sessions/         — Resumos de sessões de trabalho
└── testing/          — Checklists de teste, validações, relatórios QA
```

Para cada ficheiro .md:
- Lê o título/primeiras linhas
- Classifica na subpasta correcta pelo conteúdo
- Move para a subpasta

Também move ficheiros .doc/.docx para a subpasta mais adequada.

### FASE 5 — VERIFICAÇÃO
Após toda a limpeza:
1. Corre `python -m pytest tests/unit/ --no-cov` para garantir que nada partiu
2. Lista a estrutura final da raiz do projecto
3. Lista a estrutura final de docs/ com contagem de ficheiros por subpasta
4. Reporta quantos ficheiros foram eliminados, movidos, e o espaço libertado

### REGRAS
- NÃO eliminar ficheiros .md (mover para docs/)
- NÃO eliminar ficheiros dentro de api/, watcherdb/, services/, modules/ (são código activo)
- NÃO eliminar templates/, static/, config/ (são recursos activos)
- NÃO eliminar .github/, alembic/, .vscode/ (são configurações)
- MANTER README.md na raiz
- MANTER requirements*.txt, pyproject.toml, Dockerfile, docker-compose.yml, *.config.*
- MANTER scripts de gestão do servidor (.ps1, .bat, .sh) que sejam referenciados
- PERGUNTAR antes de eliminar REGISTRO_IGAC/ ou directórios com potencial valor legal
```

---

## Variantes do Prompt

### Versão curta (para projectos pequenos)
```
Faz uma faxina no projecto: backup primeiro, depois elimina scripts one-off na raiz
(fix_*.py, add_*.py, find_*.py, etc.), move test_*.py para tests/, organiza docs/
em subpastas por tipo (architecture, bugfixes, changelog, deployment, features, guides,
testing), e corre os testes no fim para garantir que nada partiu.
```

### Versão com ênfase em segurança
```
Faz uma faxina de segurança no projecto: backup primeiro, depois procura e reporta
ficheiros com credenciais hardcoded, .env commitados, .exe/.dll no repo, logs com
dados sensíveis, e ficheiros temporários. Elimina os dispensáveis, move os testes
para tests/, organiza docs/, e corre os testes no fim.
```

### Versão para CI/CD
```
Faz uma faxina no projecto focada em CI/CD: backup primeiro, depois elimina ficheiros
que não deviam estar no repo (.exe, .log, .coverage, htmlcov/, reports/, __pycache__/),
actualiza .gitignore com os patterns correctos, organiza docs/ em subpastas, verifica
que .dockerignore exclui tudo o que deve, e corre os testes no fim.
```

---

## Resultado Esperado

Após a faxina, a raiz do projecto deve ter apenas:
- **2-3 ficheiros Python** (main entry points)
- **Ficheiros de configuração** (requirements, pyproject.toml, Dockerfile, etc.)
- **1 README.md**
- **Directórios organizados** (api/, watcherdb/, services/, docs/, tests/, etc.)
- **Zero** scripts avulsos, temporários, ou duplicados
