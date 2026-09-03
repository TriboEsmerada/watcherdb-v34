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
    ProductName         = 'WatcherDB V3.3 Standard Edition'
    ProductVersion      = '3.3.0.0'
    ProductVersionShort = '3.3'
    Manufacturer        = 'WatcherDB'

    # UpgradeCode — GUID estavel para toda a linha 3.3.x. NAO alterar entre
    # releases 3.3.x — e o que permite que MajorUpgrade detecte upgrade em
    # vez de parallel-install. Rotacao requer que todos os clientes deployed
    # desinstalem manualmente primeiro.
    UpgradeCode         = '3A9E4B21-6C1F-4D78-B502-7F3E8C4A5D61'

    # ----- Windows service registration ------------------------------------------
    ServiceName         = 'WatcherDBWebServiceV33'
    ServiceDisplayName  = 'WatcherDB Web Service V3.3'
    ServiceDescription  = 'WatcherDB V3.3 Standard Edition - SQL Server monitoring web service (port 8433).'
    WebPort             = 8433

    # ----- Install layout --------------------------------------------------------
    InstallFolderName   = 'WatcherDB\V3.3'
    DataFolderName      = 'WatcherDB'

    # ----- Build artefacts -------------------------------------------------------
    MsiFileName         = 'WatcherDB_V3.3_Standard.msi'
    BundleDirName       = 'watcherdb'        # dist\<BundleDirName>\ (PyInstaller output)
    PyInstallerSpec     = 'deploy\watcherdb.spec'
}
