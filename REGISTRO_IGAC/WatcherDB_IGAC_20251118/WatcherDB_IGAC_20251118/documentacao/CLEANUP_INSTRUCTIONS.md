# 🧹 Instruções de Limpeza - WatcherDB

**Data:** 2025-11-14
**Objetivo:** Remover arquivos deprecados e organizar o repositório

---

## 📋 ARQUIVOS PARA MOVER/REMOVER

### 1. Diretório de Backup Antigo

```bash
# Mover para archive/
mkdir -p archive
mv backup_limpeza_20251112_151641 archive/

# Ou deletar se não for necessário
rm -rf backup_limpeza_20251112_151641
```

**Conteúdo:** 1.3 MB de código antigo não utilizado

---

### 2. Arquivos .deprecated

```bash
# Listar todos os arquivos .deprecated
find . -name "*.deprecated"

# Resultado esperado:
# ./modules/monitoring/notifications.py.deprecated

# Mover para archive
mv modules/monitoring/notifications.py.deprecated archive/

# Ou deletar
rm modules/monitoring/notifications.py.deprecated
```

---

### 3. Scripts de Verificação Órfãos

Estes scripts foram usados apenas para debugging e não são mais necessários:

```bash
# Remover scripts de verificação
rm verificar_endpoint_custom_queries.py
rm verificar_rotas_app.py
rm verificar_routers.py
```

**Motivo:** Já temos testes automatizados e documentação completa

---

### 4. Atualizar .gitignore

Adicionar ao `.gitignore`:

```bash
cat >> .gitignore << 'EOF'

# Archive and deprecated files
archive/
backup_limpeza_*/
*.deprecated

# Verification scripts (no longer needed)
verificar_*.py

# Temporary Excel/CSV files
interactive_*.csv
interactive_*.png
interactive_*.zip
interactive_*.html

# Cache files
*.db
__pycache__/
*.pyc
*.pyo

EOF
```

---

## 📊 IMPACTO DA LIMPEZA

| Item | Tamanho | Ação |
|------|---------|------|
| `backup_limpeza_20251112_151641/` | 1.3 MB | Mover para archive/ |
| `notifications.py.deprecated` | ~1 KB | Remover |
| Scripts de verificação (3 files) | ~8 KB | Remover |
| Arquivos temporários (CSV/PNG) | ~500 KB | Adicionar ao .gitignore |

**Total liberado:** ~1.8 MB

---

## ✅ CHECKLIST DE LIMPEZA

- [ ] Criar diretório `archive/`
- [ ] Mover `backup_limpeza_20251112_151641/` para `archive/`
- [ ] Mover `notifications.py.deprecated` para `archive/`
- [ ] Remover scripts de verificação
- [ ] Atualizar `.gitignore`
- [ ] Commit das mudanças
- [ ] Verificar que nada quebrou

---

## 🚨 IMPORTANTE

**ANTES DE DELETAR:**
1. Fazer backup do repositório completo
2. Verificar que nenhum script está usando os arquivos deprecated
3. Testar a aplicação após limpeza

```bash
# Backup seguro
tar -czf watcherdb_backup_$(date +%Y%m%d).tar.gz .

# Testar após limpeza
python watcherdb_main.py
# Verificar se inicia sem erros
```

---

## 📝 COMANDOS COMPLETOS

```bash
# === LIMPEZA COMPLETA ===

# 1. Criar archive
mkdir -p archive

# 2. Mover backups antigos
mv backup_limpeza_20251112_151641 archive/

# 3. Mover deprecated
mv modules/monitoring/notifications.py.deprecated archive/

# 4. Remover scripts de verificação
rm verificar_endpoint_custom_queries.py
rm verificar_rotas_app.py
rm verificar_routers.py

# 5. Atualizar gitignore (já foi feito acima)

# 6. Commit
git add .
git add archive/  # Se quiser manter no git
# OU
echo "archive/" >> .gitignore  # Se NÃO quiser no git

git commit -m "chore: Clean deprecated files and organize repository

- Moved backup_limpeza_20251112_151641 to archive/
- Moved .deprecated files to archive/
- Removed verification scripts
- Updated .gitignore

See CLEANUP_INSTRUCTIONS.md for details"

# 7. Testar
python watcherdb_main.py
```

---

**Responsável:** WatcherDB Team
**Status:** 📋 Pronto para execução
