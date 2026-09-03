@{
    # ============================================================================
    # WatcherDB V3.3 Standard Edition — Single Source of Truth for release metadata
    # ============================================================================
    # Consumed by:
    #   - deploy\build.py                (Python — regex parse)
    #   - deploy\build_msi.ps1           (PowerShell — Import-PowerShellDataFile)
    #   - deploy\sign_msi.ps1            (PowerShell — Import-PowerShellDataFile)
    #   - deploy\msi\Product.wxs         (via candle -d overrides from build_msi.ps1)
    #
    # NEVER edit values in deploy\msi\Variables.wxi directly — esse ficheiro foi
    # retido como fallback para compilacao isolada sem o pipeline, mas todas as
    # builds de producao OVERRIDE-am os seus <?define ?> via candle -d flags.
    # Este ficheiro .psd1 e o unico lugar que deve ser editado em cada release.
    #
    # Historico de alteracoes:
    #   2026-04-22 — created (audit FIND #B / S2-5, elimina drift permanente)
    # ============================================================================

    # ----- Product identity ------------------------------------------------------
    ProductName         = 'WatcherDB V3.4 Standard Edition'
    ProductVersion      = '3.4.0.0'
    ProductVersionShort = '3.4'
    Manufacturer        = 'WatcherDB'

    # UpgradeCode — GUID estavel para toda a linha 3.3.x. NAO alterar entre
    # releases 3.3.x — e o que permite que MajorUpgrade detecte upgrade em
    # vez de parallel-install. Rotacao requer que todos os clientes deployed
    # desinstalem manualmente primeiro.
    # 2026-09-03 (linha V3.4): MANTIDO o GUID da 3.3 de proposito — um MSI 3.4
    # substitui a 3.3 no cliente (upgrade), nao instala ao lado. Se a decisao
    # de produto vier a ser "parallel-install no cliente", gerar GUID novo aqui.
    # Nesta fase a V3.4 corre por venv manual (sem MSI) — ver
    # docs/context/SERVICO_V34_8434_RUNBOOK_2026-09-03.md.
    UpgradeCode         = '3A9E4B21-6C1F-4D78-B502-7F3E8C4A5D61'

    # ----- Windows service registration ------------------------------------------
    # 2026-09-03 (decisao owner): servico proprio da linha V3.4, em paralelo ao
    # WatcherDBWebServiceV33 (8433). Constantes espelhadas em watcherdb_service.py.
    ServiceName         = 'WatcherDBWebServiceV34'
    ServiceDisplayName  = 'WatcherDB Web Service V3.4'
    ServiceDescription  = 'WatcherDB V3.4 Standard Edition - SQL Server monitoring web service (port 8434).'
    WebPort             = 8434

    # ----- Install layout --------------------------------------------------------
    # DataFolderName distinto da 3.3: em modo frozen/MSI o data_root e'
    # C:\ProgramData\<DataFolderName> — com 'WatcherDB' igual ao da 3.3 as duas
    # linhas colidiriam em cache/config/logs/secrets (gap apontado pelo
    # deploy-architect 03/09; nao afecta o modo venv, que usa a pasta do repo).
    InstallFolderName   = 'WatcherDB\V3.4'
    DataFolderName      = 'WatcherDB\V3.4'

    # ----- Build artefacts -------------------------------------------------------
    MsiFileName         = 'WatcherDB_V3.4_Standard.msi'
    BundleDirName       = 'watcherdb'        # dist\<BundleDirName>\ (PyInstaller output)
    PyInstallerSpec     = 'deploy\watcherdb.spec'
}
