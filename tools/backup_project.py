import os
import sys
import shutil
from datetime import datetime
from pathlib import Path


def collect_paths(root: Path) -> list[Path]:
    candidates = [
        root / 'modules' / 'monitoring',
        root / 'modules' / 'analytics',
        root / 'static',
        root / 'templates',
        root / 'config',
        root / 'space_analysis_fix.py',
    ]

    # patterns
    candidates += list(root.glob('filegroup_*.py'))
    candidates += list((root / 'reports').glob('*.html'))

    return [p for p in candidates if p.exists()]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    backups_dir = root / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = backups_dir / f'project_{ts}'
    folder.mkdir(parents=True, exist_ok=True)

    paths = collect_paths(root)
    if not paths:
        print('Nenhum caminho encontrado para backup.', file=sys.stderr)
        return 2

    # Copia mantendo estrutura relativa
    for src in paths:
        rel = src.relative_to(root)
        dst = folder / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # copytree exige que não exista
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Cria zip do backup
    zip_path = backups_dir / f'project_{ts}.zip'
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', folder)

    print(f'Backup criado em: {folder}')
    print(f'ZIP: {zip_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


