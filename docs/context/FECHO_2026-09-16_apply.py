# -*- coding: utf-8 -*-
"""Fecho de 16/09 (tarde): registo em SOLUCOES.md, CONTEXT.md e no runbook do portal.

So' documentacao em docs/context. Nao toca em codigo, base ou servico.

O QUE REGISTA:
 - SOLUCOES.md: dois episodios resolvidos hoje a` tarde (a obrigacao de trocar a password que ninguem impunha;
   o Collector Health sem traducao e os dois defeitos que a traducao destapou). O episodio do erro 207 ja la'
   esta' desde o lote da manha.
 - CONTEXT.md: quatro linhas de decisao com ponteiros (must_change_password; troca obrigatoria; Collector Health
   em quatro idiomas; achado critico do instalador V1 e decisoes do owner).
 - RUNBOOK_PORTAL_NAO_ABRE_2026-09-16.md: o defeito 2 (must_change_password) fica marcado como resolvido, com
   ponteiro; o defeito 1 (caminho relativo) continua em aberto.

Uso (raiz do repo):
  cd C:\\Users\\ue_e-snetto\\Documents\\projetosPython\\WATCHERDB_V3.4
  py docs/context/FECHO_2026-09-16_apply.py --check
  py docs/context/FECHO_2026-09-16_apply.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = {
    "solucoes": Path("docs/context/SOLUCOES.md"),
    "context": Path("docs/context/CONTEXT.md"),
    "runbook": Path("docs/context/RUNBOOK_PORTAL_NAO_ABRE_2026-09-16.md"),
}
MARK = "troca obrigatoria de password nao era imposta por ninguem"

SOL_EDIT = (
    "|---|---|---|---|---|---|\n",
    "|---|---|---|---|---|---|\n"
    "| 2026-09-16 | O reset de password feito por um administrador nao obrigava o utilizador a nada, mesmo depois de a "
    "coluna must_change_password existir; a troca obrigatoria de password nao era imposta por ninguem | Funcionalidade "
    "construida a meio: o login devolvia must_change_password=true na resposta, mas o portal tinha ZERO ocorrencias do "
    "campo (templates/ e static/) e nao havia nada no servidor a travar uma sessao com a marca a 1; o defeito da coluna "
    "em falta (erro 207) escondeu este durante 8 dias porque, sem coluna, nem a marca chegava a existir | a marca viaja "
    "no token (claim mcp, posta no login); o AuthEnforcementMiddleware recusa com 403 e codigo MUST_CHANGE_PASSWORD tudo "
    "o que nao seja /api/auth/*; o portal abre a caixa de troca sem botao de fechar e recarrega depois da troca (o token "
    "novo ja nao traz a marca); SO' contas locais (auth_method == local): quem entra por AD nao tem password local para "
    "trocar, e numa conta de AD com recurso local o change_password reescreveria o marcador ad_auth: e converteria a conta "
    "| docs/context/TROCA_OBRIGATORIA_2026-09-16_apply.py; tests/unit/test_troca_obrigatoria_20260916.py; a19585b | "
    "must_change_password; troca obrigatoria; claim mcp; middleware 403; funcionalidade a meio; front-end nao le o campo; "
    "auth_method local ldap local_fallback |\n"
    "| 2026-09-16 | Collector Health em portugues com o portal em ingles (modal dos 7 estados, barra, filtros, janela de "
    "silenciar, detalhe da tarefa, mensagens de progresso) | O ecra inteiro (1496 linhas) nao tinha traducao nenhuma: 0 "
    "data-i18n e 0 chamadas t(), contra 1949 t() no resto do portal, e nenhum grupo para ele nos ficheiros de idioma; ao "
    "traduzir apareceram DOIS defeitos que so' se veem quando se traduz: (1) collSwitchTab escolhia o separador activo "
    "comparando o TEXTO VISIVEL com o nome interno (textContent.includes(tabName)) -- mesma familia do defeito das "
    "modais dos KPI de 16/09 de manha; (2) a tabela ordenavel usava o rotulo da coluna COMO CHAVE DOS DADOS (row[col.k] "
    "e cabecalho ${col.k}), pelo que traduzir o cabecalho esvaziava a tabela | cinco lotes: grupo coll em pt/pt-BR/en/es "
    "(194 chaves por idioma; pt-BR so' com o que difere), _collT(chave, portugues) com o portugues como recurso, "
    "_collTp com marcadores {n} em vez de concatenacao para singular/plural; data-tab nos separadores e comparacao pelo "
    "atributo; col.lbl separado de col.k na tabela; portugues acentuado e sem jargao; o ecra passou de 0 para 186 "
    "chamadas ao dicionario | COLL_I18N_MODAL/BARRA/MUTE/DETALHE/ACCOES_2026-09-16_apply.py; "
    "tests/unit/test_coll_i18n_*_20260916.py; fbf72e7 9ebf403 e6936bd 3cfde2b | collector health; i18n; sem traducao; "
    "texto visivel; textContent includes; data-tab; rotulo como chave; col.lbl; plural por concatenacao; _collT; "
    "recolhedor coletor colector |\n",
    1,
)

CONTEXT_APPEND = (
    "- 2026-09-16 | orquestrador + v1-intel (gate, sem veto) | must_change_password: a coluna NUNCA existiu na base "
    "porque database/07_ADD_MUST_CHANGE_PASSWORD.sql punha o UPDATE no mesmo batch do ALTER sem EXEC() -- erro 207 em "
    "compilacao, o ALTER nunca corria (irmaos 12 e 13 passaram por so' terem ALTER). Novo database/14 com a forma do "
    "canonico (DEFAULT 1 + backfill 0 nos activos), 07 marcado historico (tinha tambem o hash-semente admin123 tirado "
    "do canonico em 5ed4f68), as tres chamadas em auth_compat deixam de calar a falha. Corrido na base pelo owner com "
    "sql_monitoring (db_owner de proposito: decisao do owner, inventariar os grants reais no fim; proposta de os medir "
    "com Extended Events). 9694380, 43ca726.\n"
    "- 2026-09-16 | orquestrador | Troca obrigatoria de password passa a ser IMPOSTA pelo servidor (antes: marca "
    "gravada e ninguem a fazia valer; zero ocorrencias no portal). Claim mcp no token no login, AuthEnforcementMiddleware "
    "recusa 403 MUST_CHANGE_PASSWORD fora de /api/auth/*, portal abre a caixa sem fechar e recarrega apos a troca. SO' "
    "contas locais. Defeito encontrado e NAO corrigido (lote proprio): change_password reescreve password_hash sem "
    "olhar ao marcador ad_auth: (services/auth_service.py:1383) -- um utilizador de AD que use Alterar Senha converte a "
    "propria conta em local. a19585b; TROCA_OBRIGATORIA_2026-09-16_apply.py.\n"
    "- 2026-09-16 | orquestrador | Collector Health em quatro idiomas, em cinco lotes (COLL_I18N_MODAL, BARRA, MUTE, "
    "DETALHE, ACCOES): o ecra tinha 0 t() em 1496 linhas contra 1949 no resto do portal. Passa a 186 chamadas e 194 "
    "chaves por idioma; pt acentuado e sem jargao, pt-BR so' com o que difere (glossario medido: recolhedor/coletor/"
    "colector/collector). Dois defeitos corrigidos: separador activo escolhido pelo texto visivel (data-tab) e rotulo de "
    "coluna usado como chave dos dados (col.lbl). Por fazer: revisao do v33-i18n-linguist aos 776 textos. fbf72e7, "
    "9ebf403, e6936bd, 3cfde2b.\n"
    "- 2026-09-16 | orquestrador + security-auditor (CRITICAL) | Achado: WATCHERDB INTELLIGENCE V1/database/"
    "INSTALACAO_COMPLETA_UNIFICADA.sql:14605-14624 semeia admin/salomao/ricardo (admin) e viewer com hash fixo de "
    "admin123 e imprime a password; USER_GUIDE_PT/EN publicam admin/admin123; o V3.4 tirou as sementes (5ed4f68) sem "
    "criar forma de nascer o primeiro admin (set_local_password.py so' faz UPDATE; auto-provisao AD entra como viewer). "
    "Nesta base: 0 contas com qualquer dos dois hashes-semente. Recomendacao aceite em principio: tools/bootstrap_admin.py "
    "interactivo que recusa correr se ja houver admin; ordem bootstrap -> tirar sementes -> guias -> gate anti-hash; "
    "credencial de escrita = a do portal por agora (decisao do owner). Parecer do plano B sem AD: DPAPI como base, gMSA "
    "so' com AD, cofres a pedido; bloqueio mantido enquanto Trusted_Connection e separacao de identidades estiverem "
    "abertos.\n"
)

RUNBOOK_OLD = (
    "2. **`Invalid column name 'must_change_password'`** numa consulta de autenticação (`[AUTH] Query error` no registo).\n"
)
RUNBOOK_NEW = (
    "2. ~~**`Invalid column name 'must_change_password'`** numa consulta de autenticação~~ — **resolvido a 16/09**: a\n"
    "   coluna nunca tinha sido criada porque o script 07 abortava com o erro 207; ver `database/14_ADD_MUST_CHANGE_PASSWORD.sql`\n"
    "   e a linha de 16/09 em `SOLUCOES.md`. Se esta mensagem voltar a aparecer, a base foi reposta de uma cópia anterior a essa\n"
    "   data — correr o script 14 outra vez (é idempotente).\n"
)


def _apply(text, edits, label):
    eol = "\r\n" if "\r\n" in text else "\n"
    for old, new, count in edits:
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        got = text.count(o)
        if got != count:
            raise SystemExit(f"[ABORT] {label}: anchor esperado {count}x, encontrado {got}x -- nada escrito:\n  {old[:120]!r}")
        text = text.replace(o, n)
    return text


def main(argv):
    check = "--check" in argv
    src = {k: ROOT / p for k, p in REL.items()}
    sol = src["solucoes"].read_bytes().decode("utf-8")
    if MARK in sol:
        print("[ABORT] ja aplicado"); return 1
    ctx = src["context"].read_bytes().decode("utf-8")
    eol_ctx = "\r\n" if "\r\n" in ctx else "\n"
    if not ctx.endswith(eol_ctx):
        ctx += eol_ctx
    out = {
        "solucoes": _apply(sol, [SOL_EDIT], "solucoes"),
        "context": ctx + CONTEXT_APPEND.replace("\n", eol_ctx),
        "runbook": _apply(src["runbook"].read_bytes().decode("utf-8"), [(RUNBOOK_OLD, RUNBOOK_NEW, 1)], "runbook"),
    }
    print("[ok] SOLUCOES +2 linhas; CONTEXT +4 linhas; runbook defeito 2 resolvido")
    if check:
        print("--check OK. Nada escrito."); return 0
    for k, text in out.items():
        src[k].write_bytes(text.encode("utf-8")); print(f"[write] {REL[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
