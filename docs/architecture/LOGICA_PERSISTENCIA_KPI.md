# 📊 LÓGICA DE PERSISTÊNCIA DOS KPIs

**Data:** 2025-12-09
**Objetivo:** Manter valores estáticos nos cards até que problemas apareçam

---

## 🎯 REGRA PRINCIPAL

### **Instances OK** e **DB Availability**
- **Mantêm sempre o último valor conhecido**
- **SÓ MUDAM quando aparecem problemas:**
  - `Instances OK` → Só diminui quando `Instances Off` > 0
  - `DB Availability` → Só diminui quando `DB Not Availability` > 0

---

## 💡 LÓGICA SIMPLIFICADA

### **Instances OK**

```python
# CACHE
_last_known_values['instances_ok'] = None  # Último valor conhecido
_last_known_values['last_instances_off_count'] = None  # Último valor de OFF

# LÓGICA
if _last_known_values['last_instances_off_count'] == off_count:
    # Nada mudou no OFF → Manter valor em cache
    instances_ok = _last_known_values['instances_ok']
else:
    # OFF mudou → Recalcular
    if off_count == 0:
        # Sem problemas → Usar valor atual (pode aumentar)
        instances_ok = ok_count  # Valor da query
        _last_known_values['instances_ok'] = ok_count
    else:
        # Com problemas → Diminuir
        instances_ok = ok_count  # Valor da query (menor)
        _last_known_values['instances_ok'] = ok_count

    # Atualizar o último valor de OFF
    _last_known_values['last_instances_off_count'] = off_count
```

### **DB Availability**

```python
# CACHE
_last_known_values['db_availability_ok'] = None  # Último valor conhecido
_last_known_values['last_abnormal_count'] = None  # Último valor de NOT AVAILABLE

# LÓGICA
if _last_known_values['last_abnormal_count'] == abnormal_count:
    # Nada mudou no NOT AVAILABLE → Manter valor em cache
    db_availability = _last_known_values['db_availability_ok']
else:
    # NOT AVAILABLE mudou → Recalcular
    if abnormal_count == 0:
        # Sem problemas → Usar valor atual (pode aumentar)
        db_availability = total_databases_online  # Valor da query
        _last_known_values['db_availability_ok'] = total_databases_online
    else:
        # Com problemas → Diminuir
        db_availability = total_databases_online  # Valor da query (menor)
        _last_known_values['db_availability_ok'] = total_databases_online

    # Atualizar o último valor de NOT AVAILABLE
    _last_known_values['last_abnormal_count'] = abnormal_count
```

---

## 📊 EXEMPLOS PRÁTICOS

### **Cenário 1: Estado Normal (Sem Problemas)**

**Primeira Coleta:**
```
Instances Off: 0
Instances OK (query): 84
→ Cache: instances_ok = 84
→ Card mostra: 84 ✅
```

**Segunda Coleta (nada mudou):**
```
Instances Off: 0 (igual ao último)
→ Usa cache: 84 (não recalcula)
→ Card mostra: 84 ✅
```

**Terceira Coleta (nova instância adicionada):**
```
Instances Off: 0 (igual ao último)
→ Usa cache: 84 (não recalcula, mesmo que agora sejam 85)
→ Card mostra: 84 ✅ (ESTÁTICO)
```

### **Cenário 2: Problema Aparece**

**Primeira Coleta:**
```
Instances Off: 0
Instances OK: 84
→ Cache: instances_ok = 84
→ Card mostra: 84 ✅
```

**Segunda Coleta (problema detectado):**
```
Instances Off: 2 (MUDOU! era 0)
Instances OK (query): 82
→ Recalcula: instances_ok = 82
→ Atualiza cache: 82
→ Card mostra: 82 ⚠️ (DIMINUIU)
```

**Terceira Coleta (problema persiste):**
```
Instances Off: 2 (igual ao último)
→ Usa cache: 82 (não recalcula)
→ Card mostra: 82 ⚠️ (ESTÁTICO)
```

### **Cenário 3: Problema Resolvido**

**Estado Anterior:**
```
Instances Off: 2
Instances OK: 82 (em cache)
→ Card mostra: 82 ⚠️
```

**Nova Coleta (problema resolvido):**
```
Instances Off: 0 (MUDOU! era 2)
Instances OK (query): 84
→ Recalcula: instances_ok = 84
→ Atualiza cache: 84
→ Card mostra: 84 ✅ (AUMENTOU)
```

---

## 🔧 IMPLEMENTAÇÃO SIMPLIFICADA

### Código Proposto

```python
# ========================================
# INSTANCES OK
# ========================================
def calculate_instances_ok(off_count, ok_count_from_query):
    """
    Calcula Instances OK com lógica de persistência

    Args:
        off_count: Contagem atual de instâncias OFF
        ok_count_from_query: Contagem atual de instâncias OK da query

    Returns:
        Valor de Instances OK para exibir no card
    """
    global _last_known_values

    # Obter últimos valores conhecidos
    last_off = _last_known_values.get('last_instances_off_count')
    last_ok = _last_known_values.get('instances_ok')

    # Verificar se OFF mudou
    if last_off is not None and last_off == off_count:
        # OFF não mudou → Manter cache
        if last_ok is not None:
            logger.debug(f"Instances OK: Mantendo cache (OFF={off_count}): {last_ok}")
            return last_ok
        else:
            # Cache vazio → Inicializar
            _last_known_values['instances_ok'] = ok_count_from_query
            _last_known_values['last_instances_off_count'] = off_count
            logger.debug(f"Instances OK: Inicializando cache: {ok_count_from_query}")
            return ok_count_from_query
    else:
        # OFF mudou → Recalcular
        _last_known_values['instances_ok'] = ok_count_from_query
        _last_known_values['last_instances_off_count'] = off_count
        logger.debug(f"Instances OK: Recalculado (OFF mudou de {last_off} para {off_count}): {ok_count_from_query}")
        return ok_count_from_query

# ========================================
# DB AVAILABILITY
# ========================================
def calculate_db_availability(abnormal_count, total_online_from_query):
    """
    Calcula DB Availability com lógica de persistência

    Args:
        abnormal_count: Contagem atual de databases NOT AVAILABLE
        total_online_from_query: Contagem atual de databases ONLINE da query

    Returns:
        Valor de DB Availability para exibir no card
    """
    global _last_known_values

    # Obter últimos valores conhecidos
    last_abnormal = _last_known_values.get('last_abnormal_count')
    last_available = _last_known_values.get('db_availability_ok')

    # Verificar se NOT AVAILABLE mudou
    if last_abnormal is not None and last_abnormal == abnormal_count:
        # NOT AVAILABLE não mudou → Manter cache
        if last_available is not None:
            logger.debug(f"DB Availability: Mantendo cache (NOT AVAILABLE={abnormal_count}): {last_available}")
            return last_available
        else:
            # Cache vazio → Inicializar
            _last_known_values['db_availability_ok'] = total_online_from_query
            _last_known_values['last_abnormal_count'] = abnormal_count
            logger.debug(f"DB Availability: Inicializando cache: {total_online_from_query}")
            return total_online_from_query
    else:
        # NOT AVAILABLE mudou → Recalcular
        _last_known_values['db_availability_ok'] = total_online_from_query
        _last_known_values['last_abnormal_count'] = abnormal_count
        logger.debug(f"DB Availability: Recalculado (NOT AVAILABLE mudou de {last_abnormal} para {abnormal_count}): {total_online_from_query}")
        return total_online_from_query
```

### Uso no Endpoint

```python
# Buscar dados
off_count = get_off_count_from_query()
ok_count = get_ok_count_from_query()
abnormal_count = get_abnormal_count_from_query()
total_online = get_total_online_from_query()

# Aplicar lógica de persistência
instances_ok = calculate_instances_ok(off_count, ok_count)
db_availability = calculate_db_availability(abnormal_count, total_online)

# Retornar
results["instance_availability"]["ok_count"] = instances_ok
results["db_availability"]["ok_instances_count"] = db_availability
```

---

## ✅ BENEFÍCIOS DESTA LÓGICA

1. **Simples e Clara** - Fácil de entender e debugar
2. **Determinística** - Sempre produz o mesmo resultado para os mesmos inputs
3. **Eficiente** - Não recalcula se nada mudou
4. **Consistente** - Valores estáticos até que problemas apareçam
5. **Debugável** - Logs claros de quando e por que mudou

---

## 🚀 PRÓXIMOS PASSOS

1. Implementar funções `calculate_instances_ok()` e `calculate_db_availability()`
2. Substituir lógica atual complexa por essas funções
3. Testar cenários:
   - Estado normal (sem mudanças)
   - Problema aparece
   - Problema persiste
   - Problema resolvido
4. Validar logs para garantir comportamento correto

---

**Status:** ✅ **DOCUMENTADO - PRONTO PARA IMPLEMENTAÇÃO**
