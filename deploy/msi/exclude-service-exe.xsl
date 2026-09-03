<?xml version="1.0" encoding="UTF-8"?>
<!--
  Transform aplicado ao harvest do heat.exe (build_msi.ps1, flag -t).

  Remove watcherdb.exe do ComponentGroup BundleFiles porque esse ficheiro
  passa a ser declarado a mao em Product.wxs, dentro do ServiceRegistrationComp.
  Razao: o standard action InstallServices deriva o ImagePath do servico a
  partir do KeyPath do Component que contem a linha ServiceInstall. Enquanto o
  exe viveu num componente separado gerado pelo heat, o ServiceRegistrationComp
  ficou com keypath de directoria e o servico foi registado com um ImagePath
  malformado -> rollback silencioso na instalacao (incidente 2026-08-12).

  Se este transform deixar de fazer match (heat mudar o Id do componente),
  o exe fica declarado duas vezes e o light.exe falha com ID duplicado:
  falha alta e visivel, nao silenciosa.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:wix="http://schemas.microsoft.com/wix/2006/wi"
    exclude-result-prefixes="wix">

  <xsl:output method="xml" indent="yes" />

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()" />
    </xsl:copy>
  </xsl:template>

  <!-- watcherdb.exe declarado a mao em Product.wxs::ServiceRegistrationComp -->
  <xsl:template match="wix:Component[@Id='watcherdb.exe']" />
  <xsl:template match="wix:ComponentRef[@Id='watcherdb.exe']" />

</xsl:stylesheet>
