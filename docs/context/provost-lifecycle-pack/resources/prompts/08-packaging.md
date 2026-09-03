---
stage: 08
title: Packaging e deploy
version: 0.1.0
constraints: [PY-PKG]
---

# Etapa 08 — Packaging de {{PROGRAM_NAME}}

Transformar código que corre na tua máquina em artefacto que instala e
corre na máquina de um estranho. A fasquia: instalação numa máquina
LIMPA, por alguém que não és tu, sem te ligar a pedir ajuda.

## Tarefas

1. **Manifesto** — `pyproject.toml` completo (nome, versão SemVer,
   deps com lockfile, entry points). Reprodutível: `uv sync` (ou
   equivalente) numa máquina limpa produz ambiente idêntico.

2. **Artefacto** — escolhe UM caminho primário e di-lo no ADR:
   - Ferramenta interna/equipa técnica → wheel + `pipx install`.
   - Produto para cliente final → executável (PyInstaller primeiro;
     Nuitka se performance/proteção justificar) + installer.
   <!-- EXPAND: se {{TARGET_PLATFORMS}} inclui mobile, o packaging
   Python cobre só o backend/desktop; o cliente mobile/PWA tem
   pipeline próprio (build web/store) — descreve os DOIS pipelines e
   o que os liga (versão da API). -->

3. **Proteção de IP** (se produto comercial): obfuscar SÓ o módulo de
   valor isolado na etapa 03 (bloco ENCAPS #6). Manter sempre build
   não-obfuscado de debug; log de bugs da ferramenta de obfuscação
   (builds que falham são a norma, não a exceção).

4. **Instalação como serviço** (se aplicável): wizard idempotente —
   instalar, RE-instalar e upgrade são o mesmo comando; migrations de
   BD idempotentes incluídas; rollback documentado ANTES do primeiro
   deploy.

5. **Conformidade**: SBOM gerado, `pip-audit` limpo,
   THIRD_PARTY_LICENSES gerado. Nenhuma dependência copyleft
   inesperada num produto fechado.

6. **Teste de máquina limpa** — VM/container sem Python, sem os teus
   PATHs: instalar → arrancar → smoke test → desinstalar. Só depois
   disto o artefacto existe.

## Critério de saída
- [ ] Artefacto instala e corre em máquina limpa (evidência, não fé)
- [ ] Upgrade e rollback testados
- [ ] SBOM + licenças + audit no repo
- [ ] Pipeline de build reproduzível num comando
