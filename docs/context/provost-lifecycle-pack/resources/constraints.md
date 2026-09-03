# Constraints transversais — fonte única de verdade

> Cada bloco declara `applies_to:` (etapas onde a skill o injeta) e
> `last_verified:` (data da última revalidação de conteúdo que data).
> Cap: máx. 15 cláusulas por bloco. Lições novas entram via
> `lessons.md` e só são consolidadas aqui pelo owner do pack.

---

## GIT — disciplina de versionamento
`applies_to: [00, 03, 05, 06, 09]` | `last_verified: 2026-07-24`

1. Branch dedicada por projeto/feature; `main` recebe só merges revistos.
2. Checkpoint ANTES de qualquer alteração arriscada: commit, branch ou
   backup — estado recuperável sempre.
3. Commits atómicos: uma intenção por commit; mensagem
   `tipo(escopo): resumo` (feat/fix/docs/refactor/test/chore).
4. Commitar sempre no fecho de cada unidade de trabalho — trabalho de
   24h+ sem commit é incidente, não estilo.
5. Em PowerShell, mensagens de commit só com caracteres seguros: sem
   `"`, `->`, `[[...]]` (quebram o parsing de argv); usar múltiplos
   `-m` single-quoted para corpo multi-linha.
6. Multi-repo: `git status` POR repo antes de declarar "commitado" —
   nunca assumir que o parent tracking cobre o filho.
7. `.gitignore` desde o commit 1: secrets, `.env`, caches, builds,
   DBs locais, artefactos de packaging.
8. Nunca `--force`, `reset --hard` ou `--no-verify` sem aprovação
   explícita do humano.

## PY-PKG — packaging e distribuição Python
`applies_to: [03, 08, 09]` | `last_verified: 2026-07-24`

1. `pyproject.toml` como manifesto único desde o dia 1 (PEP 621);
   gestor recomendado: `uv` (rápido, lockfile determinístico).
2. Pins exatos em produção (lockfile); ranges só em bibliotecas.
3. Executáveis: PyInstaller para velocidade de iteração; Nuitka quando
   performance/proteção justificar o build lento. Testar o binário em
   máquina LIMPA (sem Python instalado) antes de declarar packaged.
4. Proteção de IP comercial: obfuscação (PyArmor ou compilação Nuitka/
   Cython) — tratar PyArmor com cuidado: manter log de bugs de build e
   fallback de build sem obfuscação.
5. Installers: Windows → Inno Setup ou MSI/WiX; serviço Windows →
   pywin32 com boot hardening (should_exit + daemon threads + /healthz).
6. SBOM (Syft/CycloneDX) + `pip-audit` no gate de release; ficheiro
   `THIRD_PARTY_LICENSES.txt` gerado, não manual.
7. Migrations de BD empacotadas idempotentes (Alembic ou SQL
   `IF NOT EXISTS`); instalar e RE-instalar têm de ser seguros.

## ENCAPS — encapsulamento e boundaries
`applies_to: [03, 05, 07]` | `last_verified: 2026-07-24`

1. Camadas com fronteira explícita: UI ↔ API/serviço ↔ domínio ↔ dados.
   UI nunca fala com a BD diretamente.
2. Um módulo = uma responsabilidade; API pública mínima (`__all__`,
   prefixo `_` para interno); dependências apontam para dentro
   (domínio não importa UI).
3. Config fora do código: `.env` + Pydantic Settings (validação no
   arranque, falha cedo e com mensagem clara).
4. Separação de identidades: conta de serviço least-privilege para
   dados; conta pessoal/domínio NUNCA em connection string.
5. Segredos nunca em código, log ou repo; encriptação em repouso
   (DPAPI/keyring no cliente; Fernet com chave fora do repo).
6. IP: núcleo de valor (algoritmos, prompts, heurísticas) isolado em
   módulo próprio — é esse que se protege no packaging (bloco PY-PKG).

## XPLAT — UI responsiva multi-plataforma
`applies_to: [02, 03, 06]` | `last_verified: 2026-07-24`

1. Árvore de decisão (nesta ordem):
   a. Conteúdo/dashboards/CRUD, sem hardware nativo → **PWA responsiva**
      (uma codebase, corre em Android + iOS + desktop + tablet via
      browser; instalável; recomendação default — menor custo, maior
      alcance).
   b. Precisa de hardware nativo (BLE, sensores, background real,
      notificações ricas) ou presença nas stores → **Flutter** (uma
      codebase, look nativo, builds Android/iOS/desktop).
   c. Equipa já domina React → React Native é aceitável; senão, não
      introduzir dois ecossistemas.
   d. Python-only por restrição de equipa → Kivy/BeeWare SÓ com
      protótipo de viabilidade primeiro (ecossistema mobile frágil).
2. Responsivo = mobile-first: breakpoints mínimos 360px (phone),
   768px (tablet), 1366px (desktop); testar nos três antes de "done".
3. Touch targets ≥ 44px; nada de hover-only; gestos com alternativa
   visível.
4. Offline-first se o uso em mobilidade importa: cache local + sync;
   decidir estratégia de conflito ANTES de implementar.
5. i18n desde o início (chaves, nunca strings hardcoded) + WCAG 2.1 AA
   como fasquia de acessibilidade.
6. Event handlers inline em HTML: testar em BROWSER real antes de
   declarar shipped (quoting/JSON em atributos quebra silenciosamente).
7. Strings JS single-quoted nunca com apóstrofe unescaped — um
   SyntaxError mata o script block inteiro e mascara o bug real.

## SEC — segurança e dados
`applies_to: [00, 03, 07, 09]` | `last_verified: 2026-07-24`

1. Threat model leve (STRIDE) na etapa de arquitetura; OWASP Top 10
   como checklist mínimo em apps web.
2. Autenticação: nunca inventar crypto; libs estabelecidas; RBAC
   simples desde o início (user/admin chega para v1).
3. Endpoints de mutação protegidos server-side; gate na UI é UX, não
   segurança.
4. Dados pessoais: minimizar recolha, reter só o necessário, caminho
   de export/delete (GDPR-shaped mesmo sem obrigação formal).
5. Rate limiting em endpoints públicos; logs de auditoria em ações
   sensíveis; logs NUNCA com segredos ou dados pessoais em claro.

## OBS — observabilidade e operação
`applies_to: [03, 05, 10]` | `last_verified: 2026-07-24`

1. Logging estruturado desde o commit 1 (níveis, timestamps, contexto);
   print() não é logging.
2. `/healthz` (ou equivalente CLI) desde a primeira versão que corre
   como serviço; monitorização em camadas (processo → porta → resposta
   → dados frescos).
3. Freshness de dados é um KPI: dashboard a servir dados velhos é
   incidente silencioso — alarmar sobre idade dos dados, não só uptime.
4. Erros mostrados ao utilizador: mensagem acionável + código; stack
   trace vai para o log, não para o ecrã.

## DOCS — documentação viva
`applies_to: [02, 05, 09, 10]` | `last_verified: 2026-07-24`

1. README com: o que é, como instalar, como correr, como testar —
   validado numa máquina limpa.
2. CHANGELOG SemVer desde a v0.1.0; decisões de arquitetura em
   ADR-lite (1 parágrafo: contexto → decisão → consequência).
3. Regras do projeto (CLAUDE.md) é ficheiro de REGRAS, não diário —
   histórico vai para docs datados.
4. Feature matrix como ground truth quando houver tiers/edições.

## AIWORK — trabalho assistido por AI
`applies_to: [00, 04, 05]` | `last_verified: 2026-07-24`

1. Modo consultor por default em dados sensíveis: AI propõe em bloco,
   humano executa.
2. Blackboard de contexto (CONTEXT.md): agentes leem antes, anexam
   decisão (1-3 linhas + ponteiro) depois; relatórios completos em
   ficheiros próprios.
3. Specialists com "quando usar" E "quando NÃO usar" na descrição
   (routing depende disso); verificação independente a cada N unidades
   de trabalho, não só self-review final.
4. Memória persistente: lições de incidentes viram cláusulas com
   "porquê" + "como aplicar" — sem isso, repete-se o erro.
