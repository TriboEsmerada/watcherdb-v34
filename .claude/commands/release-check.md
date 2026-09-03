---
description: Gate de release (varredura + soberania + IP + tier + docs) → GO/NO-GO
---

Execute o gate de release para: $ARGUMENTS (versão/branch).

1. Leia docs/context/CONTEXT.md.
2. Rode /varredura (suíte completa) — bloqueante se houver bug crítico.
3. Gate e2e de browser (comportamento UI, não só forma do código): com o
   serviço a correr (V3.3 http://localhost:8433), rode `pytest -m e2e --no-cov`
   — bloqueante se falhar. O `--no-cov` é obrigatório (os e2e batem noutro
   processo, coverage ~0 → bateria no --cov-fail-under). Se o serviço NÃO
   estiver de pé, NÃO silenciar: registar "gate e2e por validar" como pendência
   NO-GO até ser corrido.
4. Varredura de soberania: busque no código por chamadas a APIs cloud
   de IA (openai, anthropic, googleapis, azure openai, etc.) no caminho
   de runtime do produto — bloqueante se encontrar.
5. Varredura de IP: busque por termos do empregador em código, docs e
   comentários — bloqueante se encontrar.
6. Varredura de tier: dispatch v33-feature-matrix-checker no diff da
   release — bloqueante se houver tier creep (Pro em Std).
7. Confira: CHANGELOG atualizado (SemVer + tier annotations), docs das
   features novas, migrações/DDL com rollback documentado e handoff ao
   V1 specialist se tocarem na WatcherDB_Intelligence, gate e2e verde (passo 3).
8. Veredicto: GO / NO-GO com lista de pendências.
9. Relatório em docs/context/releases/AAAA-MM-DD_<versao>.md +
   1 linha no Diário do CONTEXT.md.
