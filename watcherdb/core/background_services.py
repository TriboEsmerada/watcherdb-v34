"""
Background Services
Health monitoring, cache maintenance, and inventory sync
"""

import asyncio
import time
import logging

from watcherdb.core.inventory_manager import SmartTapInventoryManager

logger = logging.getLogger(__name__)


class BackgroundServices:
    """
    Servicos em background usando implementacoes proprias
    """

    def __init__(self, inventory_manager: SmartTapInventoryManager):
        self.inventory_manager = inventory_manager
        self.running = True
        self.tasks = []

    async def start_all_services(self):
        """Inicia todos os servicos em background"""
        self.tasks = [
            asyncio.create_task(self._health_monitor()),
            asyncio.create_task(self._cache_maintenance()),
            asyncio.create_task(self._inventory_sync())
        ]

        logger.info("Background services started")

    async def stop_all_services(self):
        """Para todos os servicos"""
        self.running = False
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Background services stopped")

    async def _health_monitor(self):
        """Monitor de saude dos servidores"""
        # Delay inicial para permitir servidor iniciar completamente
        await asyncio.sleep(30)
        while self.running:
            try:
                servers = await self.inventory_manager.load_complete_inventory()

                for server in servers:
                    # Simular verificacao de saude
                    health_score = 100 - (server.alerts_count * 10)
                    health_score = max(0, min(100, health_score))
                    server.health_score = health_score

                    # Publicar status via cache pub/sub
                    self.inventory_manager.cache.publish(
                        f"health:{server.server_name}",
                        {
                            'server': server.server_name,
                            'health_score': health_score,
                            'timestamp': time.time()
                        }
                    )

                await asyncio.sleep(300)  # 5 minutos

            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(60)

    async def _cache_maintenance(self):
        """Manutencao do cache"""
        # Delay inicial para permitir servidor iniciar completamente
        await asyncio.sleep(35)
        while self.running:
            try:
                stats = self.inventory_manager.cache.get_stats()

                logger.debug(f"Cache stats: {stats['total_keys']} keys, "
                           f"{stats['hit_rate']}% hit rate, "
                           f"{stats['memory_usage_mb']} MB")

                await asyncio.sleep(600)  # 10 minutos

            except Exception as e:
                logger.error(f"Cache maintenance error: {e}")
                await asyncio.sleep(60)

    async def _inventory_sync(self):
        """Sincronizacao do inventario"""
        # Delay inicial para permitir servidor iniciar completamente
        await asyncio.sleep(40)
        while self.running:
            try:
                servers = await self.inventory_manager.load_complete_inventory()

                # Atualizar metricas
                cache_key = "inventory_metrics"
                metrics = {
                    'total_servers': len(servers),
                    'by_environment': {},
                    'by_location': {},
                    'health_distribution': {'healthy': 0, 'warning': 0, 'critical': 0},
                    'last_sync': time.time()
                }

                for server in servers:
                    env = server.environment
                    metrics['by_environment'][env] = metrics['by_environment'].get(env, 0) + 1

                    loc = server.location or 'Unknown'
                    metrics['by_location'][loc] = metrics['by_location'].get(loc, 0) + 1

                    if server.health_score >= 90:
                        metrics['health_distribution']['healthy'] += 1
                    elif server.health_score >= 70:
                        metrics['health_distribution']['warning'] += 1
                    else:
                        metrics['health_distribution']['critical'] += 1

                self.inventory_manager.cache.set(cache_key, metrics, ttl=1800)

                logger.debug(f"Inventory sync completed: {len(servers)} servers")
                await asyncio.sleep(1800)  # 30 minutos

            except Exception as e:
                logger.error(f"Inventory sync error: {e}")
                await asyncio.sleep(300)
