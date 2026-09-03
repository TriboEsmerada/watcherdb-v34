# PROMPT DE PROPAGAÇÃO → V3.3 e V6 — serviço sem logs com host `python.exe` (2026-09-03)

Para a AI da V3.3 (repo `WATCHERDB_V3.3`) e da V6. Origem: V3.4, ao validar a
licença do serviço novo `WatcherDBWebServiceV34`.

## Sintoma
`Get-Service` diz Running, mas `logs\service_stdout.log` / `service_stderr.log`
não são escritos (na V3.3 a última escrita é **2026-08-21 18:24**; `stdout` com
18,9 MB e sem `.1` — a rotação de 10 MB nunca correu). Os únicos registos do
arranque estão no Event Log Application (`servicemanager.LogInfoMsg`). Toda a
saída da app — uvicorn access log, `[AUTH]`, reconciliações dos KPIs,
tracebacks — é descartada em silêncio.

## Causa
`watcherdb_service.py`, `WatcherDBService.__init__`: o redirect para os
ficheiros só corria `if sys.stdout is None or sys.stderr is None`. Isso é
verdadeiro com o host `pythonservice.exe`. Desde que o binPath passou a
`"<venv>\python.exe" "<repo>\watcherdb_service.py"` (SOLUCOES 2026-08-31, e na
V3.3 já a 21/08 via `update`), o SCM entrega handles **válidos para NUL** — os
streams não são `None`, o teste falha, nada é redirigido.

## Fix aplicado na V3.4 (commit do PASSO 5)
```python
def _running_as_service() -> bool:
    try:
        return bool(servicemanager.RunningAsService())
    except Exception:
        return False

_UNSET = object()  # sentinela: None e' valor legitimo para os streams (nao usar None como default)

def _std_needs_redirect(stdout=_UNSET, stderr=_UNSET, as_service=None) -> bool:
    out = sys.stdout if stdout is _UNSET else stdout
    err = sys.stderr if stderr is _UNSET else stderr
    svc = _running_as_service() if as_service is None else as_service
    return out is None or err is None or bool(svc)
```
e em `__init__`: `if _std_needs_redirect():` (o corpo — `_rotate_if_big` + `open(..., "a")`
para `logs/service_std{out,err}.log` — fica igual). 3 testes puros em
`tests/unit/test_service_entry.py` (SCM com streams válidos → True; algum None → True;
consola → False).

## Como validar depois de portar
```powershell
Restart-Service WatcherDBWebServiceV33      # (ou V6)
Start-Sleep 30
Get-ChildItem .\logs\service_std*.log | Select-Object Name, Length, LastWriteTime   # LastWriteTime = agora
# stdout tinha 18,9 MB -> deve existir service_stdout.log.1 (rotacao no arranque)
Select-String -Path .\logs\service_stderr.log -Pattern 'event_id=1000' | Select-Object -Last 1
```

## Nota para a V6
Confirmar primeiro se o `watcherdb_service.py` da V6 tem o mesmo bloco `is None`
e se o serviço `WatcherDBWebServiceV6` (8660) está registado com `python.exe` ou
`pythonservice.exe` (`sc.exe qc WatcherDBWebServiceV6`). Só com `python.exe` o
sintoma aparece — mas o fix é inofensivo em ambos.
