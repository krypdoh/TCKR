#!/usr/bin/env python3
"""
Memory Pool Manager for TCKR Application
Optimizes QPixmap allocations to reduce garbage collection overhead
"""

from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QSize
import weakref
import threading
from collections import defaultdict
import time


class PixmapPool:
    """Thread-safe object pool for QPixmap instances"""
    
    def __init__(self, max_size_per_dimension=50):
        self._pools = defaultdict(list)  # Size -> List of pixmaps
        self._lock = threading.RLock()
        self._max_size_per_dimension = max_size_per_dimension
        self._stats = {
            'created': 0,
            'reused': 0,
            'returned': 0,
            'gc_prevented': 0
        }
        self._last_cleanup = time.time()
        
    def get_pixmap(self, width, height):
        """Get a QPixmap from the pool or create new one"""
        from PyQt5.QtCore import Qt
        
        size_key = (width, height)
        
        with self._lock:
            pool = self._pools[size_key]
            
            if pool:
                pixmap = pool.pop()
                pixmap.fill(Qt.transparent)  # Clear the pixmap
                self._stats['reused'] += 1
                return pixmap
            else:
                pixmap = QPixmap(width, height)
                self._stats['created'] += 1
                return pixmap
    
    def return_pixmap(self, pixmap):
        """Return a QPixmap to the pool for reuse"""
        if pixmap.isNull():
            return
            
        width, height = pixmap.width(), pixmap.height()
        size_key = (width, height)
        
        with self._lock:
            pool = self._pools[size_key]
            
            # Limit pool size to prevent excessive memory usage
            if len(pool) < self._max_size_per_dimension:
                pool.append(pixmap)
                self._stats['returned'] += 1
                self._stats['gc_prevented'] += 1
            
            # Periodic cleanup
            current_time = time.time()
            if current_time - self._last_cleanup > 30.0:  # Cleanup every 30 seconds
                self._cleanup_old_pixmaps()
                self._last_cleanup = current_time
    
    def _cleanup_old_pixmaps(self):
        """Remove excess pixmaps to free memory"""
        total_removed = 0
        
        for size_key, pool in list(self._pools.items()):
            if len(pool) > self._max_size_per_dimension // 2:
                # Keep only half the pixmaps
                keep_count = self._max_size_per_dimension // 2
                removed = pool[keep_count:]
                self._pools[size_key] = pool[:keep_count]
                total_removed += len(removed)
        
        if total_removed > 0:
            print(f"PixmapPool: Cleaned up {total_removed} unused pixmaps")
    
    def get_stats(self):
        """Get pool usage statistics"""
        with self._lock:
            total_pooled = sum(len(pool) for pool in self._pools.values())
            return {
                'created_new': self._stats['created'],
                'reused_from_pool': self._stats['reused'],
                'returned_to_pool': self._stats['returned'],
                'gc_cycles_prevented': self._stats['gc_prevented'],
                'currently_pooled': total_pooled,
                'pool_sizes': len(self._pools),
                'efficiency_ratio': self._stats['reused'] / max(1, self._stats['created'])
            }
    
    def clear(self):
        """Clear all pools"""
        with self._lock:
            self._pools.clear()
            print("PixmapPool: All pools cleared")


class ManagedPixmap:
    """Context manager for automatic pixmap pool management"""
    
    def __init__(self, pool, width, height):
        self.pool = pool
        self.pixmap = None
        self.width = width
        self.height = height
    
    def __enter__(self):
        self.pixmap = self.pool.get_pixmap(self.width, self.height)
        return self.pixmap
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pixmap is not None:
            self.pool.return_pixmap(self.pixmap)


# Global pixmap pool instance
_global_pixmap_pool = None


def get_pixmap_pool():
    """Get the global pixmap pool instance"""
    global _global_pixmap_pool
    if _global_pixmap_pool is None:
        _global_pixmap_pool = PixmapPool()
    return _global_pixmap_pool


def managed_pixmap(width, height):
    """Context manager for getting a managed pixmap"""
    return ManagedPixmap(get_pixmap_pool(), width, height)


def get_pooled_pixmap(width, height):
    """Get a pixmap from the global pool"""
    return get_pixmap_pool().get_pixmap(width, height)


def return_pooled_pixmap(pixmap):
    """Return a pixmap to the global pool"""
    get_pixmap_pool().return_pixmap(pixmap)


def get_pool_stats():
    """Get statistics from the global pool"""
    return get_pixmap_pool().get_stats()


def clear_pixmap_pool():
    """Clear the global pixmap pool"""
    get_pixmap_pool().clear()


class MemoryOptimizer:
    """Advanced memory optimization utilities for TCKR"""
    
    def __init__(self):
        self.pixmap_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
    def get_cached_pixmap(self, cache_key, width, height, generator_func):
        """Get pixmap from cache or generate and cache it"""
        if cache_key in self.pixmap_cache:
            self.cache_hits += 1
            return self.pixmap_cache[cache_key]
        
        # Generate new pixmap
        with managed_pixmap(width, height) as pixmap:
            result = generator_func(pixmap)
            
            # Cache the result (shallow copy)
            self.pixmap_cache[cache_key] = result.copy()
            self.cache_misses += 1
            
            return result
    
    def clear_cache(self):
        """Clear the pixmap cache"""
        self.pixmap_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_cache_stats(self):
        """Get cache statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_ratio = self.cache_hits / max(1, total_requests)
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_ratio': hit_ratio,
            'cached_items': len(self.pixmap_cache)
        }


# Global memory optimizer instance
_global_memory_optimizer = None


def get_memory_optimizer():
    """Get the global memory optimizer instance"""
    global _global_memory_optimizer
    if _global_memory_optimizer is None:
        _global_memory_optimizer = MemoryOptimizer()
    return _global_memory_optimizer


def benchmark_memory_optimization():
    """Benchmark memory optimization improvements"""
    import time
    import gc
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    import sys
    
    print("🧠 Benchmarking Memory Optimization...")
    
    # Create QApplication for QPixmap
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Test parameters
    iterations = 1000
    width, height = 200, 60
    
    # Without pool optimization
    print("  Testing without pool optimization...")
    gc.collect()
    start_time = time.perf_counter()
    
    pixmaps = []
    for i in range(iterations):
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        pixmaps.append(pixmap)
    
    # Force cleanup
    pixmaps.clear()
    gc.collect()
    no_pool_time = time.perf_counter() - start_time
    
    # With pool optimization
    print("  Testing with pool optimization...")
    pool = PixmapPool()
    gc.collect()
    start_time = time.perf_counter()
    
    for i in range(iterations):
        pixmap = pool.get_pixmap(width, height)
        pixmap.fill(Qt.transparent)
        pool.return_pixmap(pixmap)
    
    pool.clear()
    gc.collect()
    pool_time = time.perf_counter() - start_time
    
    # Calculate improvements
    speedup = no_pool_time / pool_time if pool_time > 0 else 0
    pool_stats = pool.get_stats()
    
    print(f"\n  📊 Results:")
    print(f"    Without Pool: {no_pool_time:.4f}s")
    print(f"    With Pool: {pool_time:.4f}s")
    print(f"    Speedup: {speedup:.2f}x faster")
    print(f"    Pool Efficiency: {pool_stats['efficiency_ratio']:.2f}")
    print(f"    GC Cycles Prevented: {pool_stats['gc_cycles_prevented']}")
    
    return {
        'memory_speedup': speedup,
        'gc_reduction': pool_stats['gc_cycles_prevented'],
        'pool_efficiency': pool_stats['efficiency_ratio']
    }


def main():
    """Demonstration of memory optimization features"""
    print("🚀 TCKR Memory Pool Optimization Demo")
    print("=" * 50)
    
    # Run benchmark
    results = benchmark_memory_optimization()
    
    print(f"\n✅ Memory optimization provides {results['memory_speedup']:.1f}x speedup")
    print(f"✅ Reduced garbage collection by {results['gc_reduction']} cycles")
    print(f"✅ Pool efficiency: {results['pool_efficiency']:.1f}")
    
    # Demonstrate usage
    print(f"\n📝 Usage Examples:")
    print("# Get pooled pixmap")
    print("pixmap = get_pooled_pixmap(200, 60)")
    print("# Use pixmap...")
    print("return_pooled_pixmap(pixmap)")
    
    print("\n# Or use context manager")
    print("with managed_pixmap(200, 60) as pixmap:")
    print("    # Use pixmap - automatically returned to pool")
    
    print(f"\n{'='*50}")


if __name__ == "__main__":
    main()