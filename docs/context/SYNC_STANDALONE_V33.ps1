# Sync do espelho standalone V3.3 (github.com/TriboEsmerada/watcherdb-v33)
# Correr: & "C:\Users\ue_e-snetto\Documents\projetosPython\WATCHERDB_V3.3\docs\context\SYNC_STANDALONE_V33.ps1"
#
# Metodo canonico (2026-07-08, validado 2026-09-02):
#   - git archive so' leva ficheiros TRACKED -> .env, .venv-build (keys) e dist
#     ficam de fora por construcao
#   - SEM pipe: o pipeline do PowerShell corrompe streams binarios (tar dava
#     "Damaged tar archive" em loop) — o .tar vai por ficheiro (episodio
#     SOLUCOES 2026-09-02)
#   - robocopy /MIR espelha e APAGA o que ja nao existe no monorepo, excepto
#     o .git do standalone (exit 1-7 do robocopy = sucesso; so >=8 e' erro)
#   - 1 commit por sync em main, mensagem com o sha do monorepo (auditavel)

Set-Location "C:\Users\ue_e-snetto\Documents\projetosPython"
$sha = git rev-parse --short HEAD
$tmp = "$env:TEMP\v33_snapshot"
$tarFile = "$env:TEMP\v33_snapshot.tar"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $tarFile -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $tmp | Out-Null

git archive HEAD -o $tarFile -- WATCHERDB_V3.3
tar -xf $tarFile -C $tmp

robocopy "$tmp\WATCHERDB_V3.3" "C:\Users\ue_e-snetto\Documents\watcherdb-v33" /MIR /XD .git

Set-Location "C:\Users\ue_e-snetto\Documents\watcherdb-v33"
git add -A
git commit -m "chore: sync WatcherDB V3.3 snapshot from monorepo @ $sha"
git push origin main
git log -1 --format='%h %s'
