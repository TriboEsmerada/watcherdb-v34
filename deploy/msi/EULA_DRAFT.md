# WatcherDB V3.3 Standard Edition — End User License Agreement (DRAFT)

> ⚠️ **DRAFT — não para uso em produção sem revisão legal**
>
> Este documento é um draft inicial estruturado por secções padrão para EULA
> comercial de software banking-grade. Destina-se a ser **revisto, adaptado
> e validado por um advogado** antes de:
>
> 1. Substituir `deploy/msi/license.rtf` (o placeholder actual)
> 2. Ser apresentado a clientes pagantes
> 3. Ser incluído em qualquer build MSI distribuído
>
> Os `[PLACEHOLDER]` indicam campos que o advogado precisa definir.
> As notas `> NOTA:` indicam pontos onde o advogado precisa fazer escolha legal.

---

## 1. Definitions

- **"Licensor"** means [PLACEHOLDER — legal entity name, e.g. "WatcherDB Lda."], with registered address at [PLACEHOLDER — full address] and tax ID [PLACEHOLDER — NIPC/VAT].
- **"Licensee"** means the legal person or entity who accepts these terms and to whom a Licence Key (`license.dat`) has been issued.
- **"Software"** means WatcherDB V3.3 Standard Edition, including the executable, libraries, documentation, and any updates provided.
- **"Documentation"** means the user-facing materials at `docs/external/standard/` and `WATCHERDB_V3.3/docs/`.
- **"Authorized Hardware"** means the specific server(s) identified by the hardware fingerprint embedded in the Licence Key.
- **"Effective Date"** means the date of acceptance of this Agreement.

---

## 2. Grant of Licence

Subject to the terms herein, Licensor grants Licensee a **non-exclusive, non-transferable, revocable** licence to:

- Install and operate the Software on Authorized Hardware
- Use the Software for internal monitoring of Licensee's SQL Server infrastructure
- Make a reasonable number of backup copies for archival purposes only

> NOTA: confirmar com advogado se a licença é **per-server**, **per-instance**, **per-environment** ou **site-license**. Afecta pricing model.

---

## 3. Ownership and Intellectual Property

The Software, including all source code, algorithms, designs, documentation, and any improvements derived therefrom, is and remains the **exclusive property of Licensor**. No title or ownership is transferred under this Agreement.

The Licensee acknowledges that the Software is protected by:
- Copyright law
- Trade secret law
- The technical protection measures embedded in the binary (PyArmor obfuscation, code signing)

---

## 4. Restrictions / Permitted Use

The Licensee shall NOT:

- Reverse engineer, decompile, disassemble, or attempt to circumvent the obfuscation or licensing mechanisms of the Software
- Redistribute, sublicense, rent, lease, sell, or transfer the Software or the Licence Key to any third party
- Use the Software for purposes other than monitoring Licensee's own SQL Server infrastructure
- Remove or alter any copyright, trademark, or proprietary notices
- Use the Software to develop a competing product
- Run the Software on hardware not Authorized by the Licence Key

The Licensee MAY:

- Configure the Software's monitoring parameters per Documentation
- Integrate the Software's HTTP API (`/api/v3/*`) with internal monitoring tools (SIEM, ticketing, dashboards) for read-only consumption
- Generate reports from the Software's data for internal use

---

## 5. Support and Maintenance

> NOTA: definir tier de suporte. Sugestão estrutura:

**Standard Support** (included):
- Email support business days, response SLA [PLACEHOLDER — 24h/48h/72h]
- Patch releases (3.3.x) free during the Subscription Period
- Documentation updates

**Premium Support** (optional, extra fee):
- 24/7 phone support, [PLACEHOLDER hour] response SLA
- On-site visits negotiated
- Custom feature development negotiated

**Excluded from Support**:
- Issues caused by Licensee modification of the Software
- Issues caused by non-Authorized Hardware
- Third-party SQL Server, OS, or hardware issues

---

## 6. Confidentiality

Each party shall protect the other party's Confidential Information with the same degree of care it uses for its own Confidential Information, but no less than reasonable care.

**Licensor's Confidential Information includes**:
- The Software source code (provided in obfuscated form only)
- Pricing terms
- Roadmap and future features

**Licensee's Confidential Information includes**:
- Operational data collected by the Software (SQL Server inventory, KPI metrics, audit logs)
- Network topology revealed during monitoring
- Database schemas of monitored servers

The confidentiality obligation survives termination of this Agreement for a period of [PLACEHOLDER — 3 years / 5 years].

---

## 7. Data Protection / GDPR

### 7.1 Roles
For the purposes of GDPR (Regulation (EU) 2016/679):
- **Licensee** is the **Data Controller** of any personal data processed via the Software
- **Licensor** acts as **Data Processor** only to the extent the Software transmits any data to Licensor (e.g., error telemetry, licence validation pings)

### 7.2 Data Processing
The Software processes the following types of data:
- SQL Server inventory metadata (host names, instance names, version)
- Operational KPIs (backup status, job execution, performance counters)
- User audit logs (login attempts, configuration changes) within the Licensee's environment

**The Software does NOT process**:
- End-user personal data from Licensee's business applications
- Customer data stored in monitored databases (read-only access at metadata level)

### 7.3 Telemetry
> NOTA: confirmar com advogado.

The Software transmits the following to Licensor's servers:
- **Licence validation pings** (cryptographically signed, machine fingerprint hash only — NO personal data)
- [PLACEHOLDER — confirmar se há outros telemetry: error reports, usage analytics?]

The Licensee may disable telemetry by [PLACEHOLDER — describing mechanism if any].

### 7.4 Cross-border transfers
> NOTA: confirmar se servidores Licensor estão em EU/EEA. Se não, adicionar SCCs.

---

## 8. Warranty and Disclaimer

THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.

LICENSOR DOES NOT WARRANT THAT:
- The Software will be error-free
- The Software will operate without interruption
- The Software will meet Licensee's specific requirements
- Defects can or will be corrected within any specific timeframe

> NOTA: para banking-grade clientes, considerar adicionar **limited warranty** de:
> - 90 dias após install, defeito reprodutível: refund pro-rata OR replace
> - Confirmar com advogado se viable.

---

## 9. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW:

LICENSOR SHALL NOT BE LIABLE FOR ANY:
- Indirect, incidental, special, consequential, or punitive damages
- Loss of profits, revenue, business opportunity, or goodwill
- Loss of data (Licensee is responsible for backups of monitored systems)
- Damages caused by use or inability to use the Software

**Aggregate Liability Cap**: Licensor's total cumulative liability under this Agreement shall not exceed the **amount paid by Licensee in the [PLACEHOLDER — 12 months] preceding the event giving rise to the claim**.

The above limitations apply even if Licensor was advised of the possibility of such damages.

> NOTA: confirmar com advogado:
> - Liability cap padrão é "fees paid in 12 months". Banking pode exigir maior. Negotiable.
> - Algumas jurisdições restringem disclaim — adaptar.

---

## 10. Term and Termination

### 10.1 Term
This Agreement is effective from the Effective Date and continues for the Subscription Period specified in the order form, automatically renewed unless either party provides [PLACEHOLDER — 30/60/90] days written notice.

### 10.2 Termination by Licensee
Licensee may terminate this Agreement at any time by:
- Uninstalling the Software from all Authorized Hardware
- Returning or destroying all copies (including the Licence Key)
- Written notice to Licensor

### 10.3 Termination by Licensor
Licensor may terminate this Agreement immediately upon written notice if:
- Licensee fails to pay any undisputed invoice within [PLACEHOLDER — 30] days
- Licensee materially breaches any provision of this Agreement
- Licensee enters bankruptcy or insolvency proceedings

### 10.4 Effect of Termination
Upon termination:
- Licensee shall cease all use of the Software within [PLACEHOLDER — 30] days
- Licensee shall destroy or return the Software and Licence Key
- The Licence Key will be added to the Certificate Revocation List (CRL)

> NOTA: CRL is **fail-open** by design (per F-SEC-003 audit) — this must be disclosed transparently. Banking clients may require explicit acknowledgment.

---

## 11. Audit Rights

Licensor reserves the right to audit Licensee's compliance with this Agreement, including verifying:
- The Software is installed only on Authorized Hardware
- The number of monitored instances does not exceed the licensed tier

Audits shall be:
- Conducted with [PLACEHOLDER — 30] days prior written notice
- During normal business hours
- At Licensor's expense, unless non-compliance is found exceeding [PLACEHOLDER — 5%] of licensed scope (in which case Licensee bears the cost)

---

## 12. Regulatory Compliance

### 12.1 Banking and Financial Services
The Licensee, when operating in financial services sectors subject to DORA (Regulation (EU) 2022/2554), NIS2 Directive, or equivalent national legislation, is responsible for ensuring the Software's use aligns with applicable ICT risk management requirements.

Licensor commits to:
- Providing a Software Bill of Materials (SBOM) per CycloneDX standard upon request
- Disclosing material security incidents affecting the Software within [PLACEHOLDER — 72 hours]
- Maintaining an Authenticode-signed installer with reproducible builds
- Annual independent security review of the Software's licensing and signing infrastructure

> NOTA: review com advogado specialist em DORA. Mais detalhes podem ser necessários conforme jurisdição.

### 12.2 Export Controls
The Software contains cryptographic components (Ed25519, AES, RSA). Licensee represents that it will not export, re-export, or transfer the Software in violation of applicable export control laws.

---

## 13. Indemnification

### 13.1 By Licensor
Licensor shall defend Licensee against claims that the Software infringes a third party's intellectual property rights, provided Licensee:
- Notifies Licensor promptly in writing
- Allows Licensor to control the defence
- Provides reasonable cooperation

Licensor's indemnification obligations exclude infringement caused by:
- Modification of the Software by Licensee
- Combination with non-Licensor software
- Use beyond the scope of this Agreement

### 13.2 By Licensee
Licensee shall defend Licensor against claims arising from:
- Licensee's misuse of the Software
- Violation of this Agreement
- Data processed via the Software where Licensee is the Data Controller

---

## 14. Governing Law and Jurisdiction

This Agreement is governed by the laws of **[PLACEHOLDER — Portugal? Other?]**, excluding its conflict of law provisions.

Any disputes arising out of or in connection with this Agreement shall be subject to the exclusive jurisdiction of the courts of **[PLACEHOLDER — Lisboa? Other?]**.

> NOTA: confirmar com advogado:
> - Jurisdição preferida (PT é comum mas pode complicar para clientes internacionais)
> - Arbitration clause? CCI/LCIA? Cost considerations.

---

## 15. Miscellaneous

### 15.1 Entire Agreement
This Agreement, together with any signed order form, constitutes the entire agreement between the parties and supersedes all prior agreements.

### 15.2 Modifications
No modification of this Agreement is effective unless in writing and signed by both parties.

### 15.3 Severability
If any provision is held invalid, the remainder shall continue in full force.

### 15.4 Notices
All notices shall be sent to:
- Licensor: [PLACEHOLDER — email + postal address]
- Licensee: as specified in the order form

### 15.5 Assignment
Licensee may not assign this Agreement without Licensor's prior written consent. Licensor may assign upon notice.

### 15.6 Force Majeure
Neither party is liable for failure to perform due to causes beyond reasonable control.

---

## Acceptance

By installing the Software, the Licensee acknowledges that it has read, understood, and agrees to be bound by the terms of this Agreement.

If you do not agree to these terms, you must not install or use the Software.

---

## Internal use — checklist para advogado

- [ ] Substituir TODOS os `[PLACEHOLDER]` por valores reais
- [ ] Resolver todas as `> NOTA:` decisões
- [ ] Adaptar Section 12 (Regulatory) à jurisdição alvo
- [ ] Confirmar Section 7 (GDPR) com DPO se Licensor tiver
- [ ] Definir liability cap em Section 9 — banking pode requerer >12 meses
- [ ] Considerar adicionar Schedule A: Service Level Agreement (SLA)
- [ ] Considerar adicionar Schedule B: Data Processing Agreement (DPA) se Licensor processa qualquer dado pessoal
- [ ] Tradução: PT (Portugal), PT-BR, EN-US, ES — conforme target markets
- [ ] Converter versão final para RTF e substituir `deploy/msi/license.rtf`
- [ ] Confirmar font size + page format para display no MSI installer dialog (Wix WixUILicenseRtf)

---

## Build pipeline note

Quando texto final estiver pronto:
1. Substituir `deploy/msi/license.rtf` pelo RTF final
2. Re-correr `pwsh deploy/build_msi.ps1 -Clean` para incluir novo EULA
3. Verificar dialog WixUI mostra EULA correctamente: `msiexec /i WatcherDB_V3.3_Standard.msi` (interactive mode mostra dialog)

---

**Document status:** DRAFT v0.1 (2026-05-16) — initial structural template, not legal advice
**Author:** WatcherDB engineering (preparation for legal review)
**Next step:** advogado adapta + valida + entrega versão final em formato RTF
