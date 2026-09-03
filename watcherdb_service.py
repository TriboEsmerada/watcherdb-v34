"""
WatcherDB V3.3 Standard — entry point unificado do bundle (Etapa 2, B0-1).

O watcherdb.exe congelado tem de falar o protocolo Windows SCM: sem
StartServiceCtrlDispatcher o SCM espera 30s (ServicesPipeTimeout) e mata o
processo com erro 1053 — era o estado do MSI de maio (B0-1).

Modos:
  sem args, arrancado pelo SCM   -> StartServiceCtrlDispatcher (servico)
  sem args, double-click/smoke   -> dispatcher falha com 1063 -> consola
  wrap-master-key                -> provisiona blob DPAPI machine-scope (Etapa 1.4)
  install|start|stop|remove|...  -> win32serviceutil.HandleCommandLine

CRITICO — nada de imports watcherdb.*/api.*/modules.*/services.* antes do
dispatcher: watcherdb/core/__init__.py puxa pandas e afins; com EDR a fazer
scan no primeiro arranque isso rebenta a janela dos 30s e reintroduz o 1053.
Os helpers 3-tier abaixo sao copias minimas de watcherdb/core/paths.py — se
mudares la, muda aqui.

Single-instance (Etapa 1.5): mutex nomeado por hash do data_root — instancias
com WATCHERDB_DATA_DIR distinto (ex.: smoke test) coexistem; dois arranques da
mesma instalacao nao.
"""
import os
import sys
import threading
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil

# Linha V3.4 (2026-09-03, decisao owner): servico PROPRIO em paralelo ao
# WatcherDBWebServiceV33 (8433) da pasta V3.3 — nome, porta e prefixo do mutex
# distintos para os dois coexistirem na mesma maquina.
SERVICE_NAME = "WatcherDBWebServiceV34"  # SOT: deploy/release_vars.psd1
SERVICE_DISPLAY = "WatcherDB Web Service V3.4"
SERVICE_DESC = (
    "WatcherDB V3.4 Standard Edition - SQL Server monitoring web service "
    "(port 8434)."
)
DEFAULT_PORT = 8434  # SOT: deploy/release_vars.psd1 WebPort

_ERROR_ALREADY_EXISTS = 183
_ERROR_FAILED_SERVICE_CONTROLLER_CONNECT = 1063

_mutex_handle = None  # vivo ate ao fim do processo (dono do lock)


def _data_root() -> Path:
    """Copia minima de watcherdb.core.paths.data_root() (3-tier)."""
    env = os.getenv("WATCHERDB_DATA_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(r"C:\ProgramData\WatcherDB")
    return Path(__file__).resolve().parent


def _logs_dir() -> Path:
    d = _data_root() / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def acquire_single_instance(data_root) -> tuple:
    """Tenta adquirir o mutex de instancia unica. Devolve (ok, nome).

    Namespace Global primeiro (visivel cross-session: servico vs consola
    de admin); fallback Local se a criacao no namespace global falhar. O
    handle fica guardado em modulo — o SO liberta-o quando o processo morre.
    """
    global _mutex_handle
    import ctypes
    import hashlib

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    digest = hashlib.sha1(str(data_root).lower().encode("utf-8")).hexdigest()[:12]
    for scope in ("Global", "Local"):
        name = scope + "\\WatcherDBV34_" + digest
        handle = kernel32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if not handle:
            continue  # sem acesso a este namespace -> tenta o proximo
        if err == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False, name
        _mutex_handle = handle
        return True, name
    return True, "(sem namespace de mutex disponivel - a prosseguir)"


def release_single_instance() -> None:
    """Liberta o mutex explicitamente (usado apenas em testes)."""
    global _mutex_handle
    if _mutex_handle:
        import ctypes

        ctypes.WinDLL("kernel32").CloseHandle(_mutex_handle)
        _mutex_handle = None


def _rotate_if_big(path: Path, max_bytes: int = 10 * 1024 * 1024,
                   backups: int = 3) -> None:
    """Roda `path` se exceder max_bytes: .3 sai, .2->.3, .1->.2, actual->.1.

    Silencioso por desenho — um erro a rodar logs nunca pode impedir o arranque
    do servico (seria trocar disco cheio por servico em baixo).
    """
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        oldest = path.with_suffix(path.suffix + f".{backups}")
        if oldest.exists():
            oldest.unlink()
        for i in range(backups - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{i}")
            if src.exists():
                src.rename(path.with_suffix(path.suffix + f".{i + 1}"))
        path.rename(path.with_suffix(path.suffix + ".1"))
    except Exception:
        pass


def _resolve_port() -> int:
    try:
        return int(os.getenv("WATCHERDB_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


def _tls_kwargs() -> tuple:
    """TLS directo no uvicorn via .env 3-tier (QA externo 2026-08-16, BUG-002/010).

    WATCHERDB_TLS_CERT / WATCHERDB_TLS_KEY apontam para PEM (uvicorn/ssl nao
    aceita PFX — converter fora do servidor, ver docs/context/TRIAGEM_QA_
    EXTERNO_PRD_2026-08-16.md). Ausentes ou ilegiveis -> fallback HTTP com
    log explicito (fail-open deliberado: rollback = repor o .env, sem loop de
    restart). Com ambos presentes o uvicorn serve SO https na mesma porta —
    nao ha redirect http->https na 8433 (socket TLS nao responde a HTTP).
    Devolve (kwargs_uvicorn, mensagem_log).
    """
    cert = os.getenv("WATCHERDB_TLS_CERT", "").strip()
    key = os.getenv("WATCHERDB_TLS_KEY", "").strip()
    if not cert or not key:
        return {}, "TLS: OFF (WATCHERDB_TLS_CERT/WATCHERDB_TLS_KEY nao definidos)"
    cert_path, key_path = Path(cert), Path(key)
    if not cert_path.is_file() or not key_path.is_file():
        return {}, ("TLS: OFF (fallback HTTP) - ficheiro em falta: cert="
                    + cert + " key=" + key)
    return (
        {"ssl_certfile": str(cert_path), "ssl_keyfile": str(key_path)},
        "TLS: ON (cert=" + cert_path.name + ")",
    )


class WatcherDBService(win32serviceutil.ServiceFramework):
    """Hospeda o uvicorn/watcherdb_main:app como servico Windows.

    Sequencia (SvcRun default do pywin32): dispatcher liga -> RUNNING
    reportado -> SvcDoRun. O import pesado da app acontece na thread
    _serve, DEPOIS do RUNNING — o handshake SCM nunca fica bloqueado.
    """

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY
    _svc_description_ = SERVICE_DESC
    # Frozen: o binPath do servico e o proprio watcherdb.exe (sem
    # pythonservice.exe intermedio) — para HandleCommandLine install.
    if getattr(sys, "frozen", False):
        _exe_name_ = sys.executable
        _exe_args_ = None
    else:
        # Venv (2026-09-03, owner: "aplicar a solucao no servico de forma
        # antecipada"): sem isto o pywin32 regista pythonservice.exe copiado
        # para a raiz do venv — host INCOMPLETO (sem python311.dll ao lado,
        # sem site-packages do venv) que morre antes do handshake SCM, sem
        # mensagem (SOLUCOES 2026-08-31 no V33, repetido 03/09 no V34).
        # binPath = "<venv>\python.exe" "<repo>\watcherdb_service.py": o
        # main() sem argumentos ja' hospeda o StartServiceCtrlDispatcher.
        _exe_name_ = sys.executable
        _exe_args_ = '"' + str(Path(__file__).resolve()) + '"'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.server_thread = None
        self._stop_requested = False
        # Em contexto de servico sys.stdout/stderr sao None -> uvicorn
        # rebenta em .isatty(). Em modo debug (consola) ficam intactos.
        if sys.stdout is None or sys.stderr is None:
            logs = _logs_dir()
            try:
                # Rodar antes de abrir: ficheiros crus de stdout/stderr nao passam
                # pelo logging do Python, logo nenhum RotatingFileHandler os cobre
                # e cresciam sem limite (1.5 GB observados no caminho equivalente
                # em 2026-08-16). O arranque e' o unico momento sem handle aberto.
                _rotate_if_big(logs / "service_stdout.log")
                _rotate_if_big(logs / "service_stderr.log")
                sys.stdout = open(logs / "service_stdout.log", "a",
                                  encoding="utf-8", buffering=1)
                sys.stderr = open(logs / "service_stderr.log", "a",
                                  encoding="utf-8", buffering=1)
            except OSError:
                pass  # sem dir gravavel; erros seguem para o Event Log

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_requested = True
        if self.server is not None:
            # Shutdown gracioso do uvicorn -> corre o lifespan shutdown
            # (scheduler, executors, cache) de watcherdb_main.
            self.server.should_exit = True
        win32event.SetEvent(self.stop_event)

    def SvcShutdown(self):
        # Sem isto o servico ignora o shutdown do SO (sem cleanup e pode
        # nao arrancar no boot seguinte) — licao do Collector Service.
        self.SvcStop()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        # 2026-09-02: o stop reporta STOPPED ao SCM ANTES de o processo antigo
        # morrer (janela graciosa ~30s abaixo) e o SO so liberta o mutex na
        # morte do processo — um Restart-Service imediato encontrava o mutex
        # ocupado e abortava a' primeira (StartServiceFailed recorrente).
        # Esperar ate 45s pelo mutex, a reportar START_PENDING para o SCM nao
        # matar o arranque; so depois disso e' que e' mesmo outra instancia.
        import time
        ok, mutex_name = acquire_single_instance(_data_root())
        deadline = time.monotonic() + 45
        waited = False
        while not ok and time.monotonic() < deadline:
            waited = True
            self.ReportServiceStatus(
                win32service.SERVICE_START_PENDING, waitHint=15000)
            time.sleep(2)
            ok, mutex_name = acquire_single_instance(_data_root())
        if not ok:
            servicemanager.LogErrorMsg(
                SERVICE_NAME + ": instancia ja em execucao (" + mutex_name
                + ") apos 45s de espera; arranque abortado."
            )
            return
        if waited:
            # O framework (win32serviceutil.SvcRun) reporta RUNNING ANTES de
            # chamar SvcDoRun; o loop acima volta a por o SCM em
            # START_PENDING e ninguem o repunha em RUNNING -> servico ficava
            # "Start Pending" para sempre (app a servir na 8433, mas Stop/
            # Restart/Start recusados pelo SCM). Incidente 02/09 19:19.
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            servicemanager.LogInfoMsg(
                SERVICE_NAME + ": mutex libertado pela instancia anterior; "
                "arranque a prosseguir."
            )
        servicemanager.LogInfoMsg(
            SERVICE_NAME + ": data_root=" + str(_data_root())
            + " mutex=" + mutex_name
        )
        # daemon=True e o backstop: se o shutdown gracioso exceder a janela
        # abaixo, o processo consegue mesmo assim terminar quando SvcDoRun
        # retorna (o SCM ja reportou STOPPED nessa altura).
        self.server_thread = threading.Thread(
            target=self._serve, name="watcherdb-uvicorn", daemon=True
        )
        self.server_thread.start()

        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

        # Janela de shutdown gracioso (~30s), a reportar STOP_PENDING para o
        # SCM nao matar o processo a meio do lifespan shutdown.
        for _ in range(6):
            self.server_thread.join(timeout=5)
            if not self.server_thread.is_alive():
                break
            self.ReportServiceStatus(
                win32service.SERVICE_STOP_PENDING, waitHint=10000
            )
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )

    def _serve(self):
        try:
            # Import pesado (app completa; carrega .env 3-tier no topo do
            # modulo) SO depois de o SCM ter o servico em RUNNING.
            import watcherdb_main
            import uvicorn

            # Regra de Ouro #2: sem identidade de BD explicita o servico nao
            # arranca (achado P-05). Depois do import, que carrega o .env.
            from watcherdb.core.db_identity import enforce_explicit_identity

            _identity = enforce_explicit_identity()
            servicemanager.LogInfoMsg(
                SERVICE_NAME + ": identidade BD = " + _identity.mode
                + " (" + _identity.source + ")"
            )

            if self._stop_requested:
                return  # SvcStop chegou durante o import
            host = os.getenv("WATCHERDB_HOST", "0.0.0.0")
            port = _resolve_port()
            tls_kwargs, tls_msg = _tls_kwargs()
            config = uvicorn.Config(
                watcherdb_main.app,
                host=host,
                port=port,
                log_level=os.getenv("WATCHERDB_LOG_LEVEL", "info").lower(),
                access_log=True,
                reload=False,
                timeout_keep_alive=30,
                log_config=None,  # config default do uvicorn assume tty
                **tls_kwargs,
            )
            self.server = uvicorn.Server(config)
            scheme = "https" if tls_kwargs else "http"
            servicemanager.LogInfoMsg(
                SERVICE_NAME + ": a servir em " + scheme + "://" + host + ":"
                + str(port) + " | " + tls_msg
            )
            self.server.run()
        except Exception as exc:
            import traceback

            traceback.print_exc()  # -> service_stderr.log
            try:
                servicemanager.LogErrorMsg(
                    SERVICE_NAME + ": erro fatal no servidor: " + repr(exc)
                )
            except Exception:
                pass
        finally:
            # Servidor terminou (gracioso ou crash) -> desbloquear SvcDoRun
            # para o servico parar em vez de ficar RUNNING vazio.
            win32event.SetEvent(self.stop_event)


def run_console() -> int:
    """Modo consola (double-click, smoke test, dev): uvicorn em foreground."""
    ok, mutex_name = acquire_single_instance(_data_root())
    if not ok:
        print("[ERRO] Ja existe uma instancia do WatcherDB em execucao ("
              + mutex_name + ").")
        return 1
    import watcherdb_main  # carrega .env 3-tier antes de lermos a porta
    import uvicorn

    # Regra de Ouro #2: sem identidade de BD explicita o servico nao arranca
    # (achado P-05). Em consola a excepcao sai para o stdout do operador.
    from watcherdb.core.db_identity import enforce_explicit_identity

    _identity = enforce_explicit_identity()
    print("[IDENTIDADE] BD = " + _identity.mode + " (" + _identity.source + ")")

    host = os.getenv("WATCHERDB_HOST", "0.0.0.0")
    port = _resolve_port()
    tls_kwargs, tls_msg = _tls_kwargs()
    scheme = "https" if tls_kwargs else "http"
    print("[START] WatcherDB V3.4 Standard (consola) - " + scheme + "://"
          + host + ":" + str(port) + " | " + tls_msg)
    uvicorn.run(
        watcherdb_main.app,
        host=host,
        port=port,
        reload=False,
        log_level=os.getenv("WATCHERDB_LOG_LEVEL", "info").lower(),
        **tls_kwargs,
    )
    return 0


def wrap_master_key() -> int:
    """Provisiona o blob DPAPI machine-scope da master key (Etapa 1.4).

    Le a Fernet key de WATCHERDB_ENCRYPTION_KEY (ambiente ou .env 3-tier)
    ou pede no prompt com input oculto; NUNCA imprime a chave. Escreve
    secrets_dir()/master.key.dpapi. Correr NA maquina alvo (DPAPI nao
    viaja entre maquinas); a ACL do ficheiro e a fronteira de seguranca.
    """
    try:
        from dotenv import load_dotenv

        for cand in (_data_root() / ".env",
                     Path(__file__).resolve().parent / ".env"):
            if cand.exists():
                load_dotenv(cand)
                break
    except ImportError:
        pass
    key = os.getenv("WATCHERDB_ENCRYPTION_KEY", "").strip()
    if not key:
        import getpass

        key = getpass.getpass("Fernet master key (input oculto): ").strip()
    if not key:
        print("[ERRO] Sem chave. Define WATCHERDB_ENCRYPTION_KEY ou "
              "introduz no prompt.")
        return 1
    try:
        from cryptography.fernet import Fernet

        Fernet(key.encode())
    except Exception:
        print("[ERRO] O valor nao e uma Fernet key valida (base64 urlsafe, "
              "32 bytes).")
        return 1
    from services.secrets import provision_master_key_file

    path = provision_master_key_file(key.encode())
    print("[OK] Blob DPAPI machine-scope escrito em: " + str(path))
    print("     Em producao o instalador restringe a ACL deste ficheiro; a")
    print("     linha WATCHERDB_ENCRYPTION_KEY em claro pode sair do .env.")
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(WatcherDBService)
            servicemanager.StartServiceCtrlDispatcher()
            return 0
        except Exception as exc:
            if getattr(exc, "winerror", None) == \
                    _ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
                # Nao foi o SCM que nos arrancou (double-click, smoke test,
                # python watcherdb_service.py) -> consola.
                return run_console()
            raise
    if sys.argv[1].lower() in ("wrap-master-key", "--wrap-master-key"):
        return wrap_master_key()
    # install | remove | start | stop | restart | update | debug
    win32serviceutil.HandleCommandLine(WatcherDBService)
    return 0


if __name__ == "__main__":
    sys.exit(main())
