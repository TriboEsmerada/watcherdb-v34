"""
Async File I/O
Thread pool based asynchronous file operations
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Union
from concurrent.futures import ThreadPoolExecutor


class AsyncFileIO:
    """
    Implementacao propria de I/O assincrono de arquivos
    Com pool de threads para operacoes blocking
    """

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def read_file(self, filepath: Union[str, Path], encoding: str = 'utf-8') -> str:
        """Read file asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._sync_read_file,
            str(filepath),
            encoding
        )

    async def write_file(self, filepath: Union[str, Path], content: str, encoding: str = 'utf-8') -> bool:
        """Write file asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._sync_write_file,
            str(filepath),
            content,
            encoding
        )

    async def read_json(self, filepath: Union[str, Path]) -> Dict[str, Any]:
        """Read JSON file asynchronously"""
        content = await self.read_file(filepath)
        return json.loads(content)

    async def write_json(self, filepath: Union[str, Path], data: Dict[str, Any]) -> bool:
        """Write JSON file asynchronously"""
        content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return await self.write_file(filepath, content)

    async def list_files(self, directory: Union[str, Path], pattern: str = "*") -> List[Path]:
        """List files asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._sync_list_files,
            Path(directory),
            pattern
        )

    async def file_exists(self, filepath: Union[str, Path]) -> bool:
        """Check if file exists asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: Path(filepath).exists()
        )

    async def file_size(self, filepath: Union[str, Path]) -> int:
        """Get file size asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: Path(filepath).stat().st_size
        )

    async def file_mtime(self, filepath: Union[str, Path]) -> datetime:
        """Get file modification time asynchronously"""
        loop = asyncio.get_event_loop()
        timestamp = await loop.run_in_executor(
            self.executor,
            lambda: Path(filepath).stat().st_mtime
        )
        return datetime.fromtimestamp(timestamp)

    def _sync_read_file(self, filepath: str, encoding: str) -> str:
        """Synchronous file read"""
        with open(filepath, 'r', encoding=encoding) as f:
            return f.read()

    def _sync_write_file(self, filepath: str, content: str, encoding: str) -> bool:
        """Synchronous file write"""
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            return True
        except Exception:
            return False

    def _sync_list_files(self, directory: Path, pattern: str) -> List[Path]:
        """Synchronous file listing"""
        if not directory.exists():
            return []

        if pattern == "*":
            return list(directory.iterdir())
        else:
            return list(directory.glob(pattern))
