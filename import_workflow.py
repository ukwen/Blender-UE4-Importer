"""Operation-scoped diagnostics; no Blender dependency or persistent source cache."""
from collections import Counter, OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter

_ACTIVE = ContextVar('ue_table_cache', default=None)
DEFAULT_BUDGET = 64 * 1024 * 1024


def signature(path):
    def stamp(p):
        try:
            s = p.stat()
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        except FileNotFoundError:
            return None
    return (stamp(path), *(stamp(path.with_suffix(e)) for e in ('.uexp', '.ubulk', '.uptnl')))


class TableCache:
    """Bounded approximate resident size (raw bytes plus conservative table overhead).

    Readers of the shared parsed tables must not mutate them. No negative caching.
    Cache lifetime is a single synchronous import/audit; stat changes invalidate hits.
    """
    def __init__(self, budget=DEFAULT_BUDGET):
        self.budget = max(0, int(budget))
        self.items = OrderedDict()
        self.resident = self.peak = self.hits = self.misses = self.evictions = self.raw_bytes = 0

    def get(self, path, reader):
        path = Path(path).absolute(); before = signature(path)
        previous = self.items.pop(path, None)
        if previous:
            stamp, value, cost = previous
            self.resident -= cost
            if stamp == before:
                self.hits += 1; self.items[path] = previous; self.resident += cost
                return value
        self.misses += 1
        value = reader(path)
        meta, raw, imports, exports, _, _ = value
        self.raw_bytes += len(raw)
        cost = len(raw) + 2048 * (len(imports) + len(exports)) + sum(128 + 4*len(n) for n in meta['names']) + 4096
        if cost <= self.budget and before == signature(path):
            while self.items and self.resident + cost > self.budget:
                _, (_, _, size) = self.items.popitem(last=False); self.resident -= size; self.evictions += 1
            self.items[path] = (before, value, cost); self.resident += cost
            self.peak = max(self.peak, self.resident)
        return value

    def stats(self):
        return dict(table_hits=self.hits, table_reads=self.misses, raw_bytes_read=self.raw_bytes,
                    estimated_cache_peak_bytes=self.peak, cache_budget_bytes=self.budget, evictions=self.evictions)


@contextmanager
def table_scope(budget=DEFAULT_BUDGET):
    current = _ACTIVE.get()
    if current is not None:
        yield current
        return
    cache = TableCache(budget); token = _ACTIVE.set(cache)
    try: yield cache
    finally:
        cache.items.clear(); cache.resident = 0; _ACTIVE.reset(token)


def cached_tables(path, reader):
    cache = _ACTIVE.get()
    return reader(path) if cache is None else cache.get(path, reader)


class Stages:
    def __init__(self, progress=None):
        self.start = perf_counter(); self.seconds = {}; self.progress = progress

    def run(self, name, function, *args, **kwargs):
        if self.progress: self.progress(name)
        t = perf_counter()
        try: return function(*args, **kwargs)
        finally: self.seconds[name] = self.seconds.get(name, 0.) + perf_counter()-t

    def report(self):
        return dict(elapsed_seconds=perf_counter()-self.start, stage_seconds=dict(self.seconds),
                    scope='Wall-clock synchronous stages; excludes final report serialization; not a cancellation guarantee')


def dependency_actions(report):
    """Group exact source package gaps; don't treat soft refs as visual omissions."""
    rows = []
    for package, item in report['dependencies'].items():
        if item['status'] == 'available': continue
        action = {'missing_game':'Restore original project Content package',
                  'missing_engine':'Configure matching Unreal Engine Content',
                  'unsupported_mount':'Resolve original plugin or other mount',
                  'invalid_or_ambiguous':'Check package path and asset/map ambiguity'}.get(item['status'], 'Inspect source reference')
        rows.append(dict(package=package, status=item['status'], hard_references=len(item['hard']),
                         soft_references=len(item['soft']), action=action))
    rows.sort(key=lambda x:(not x['hard_references'], -x['hard_references'], x['package']))
    return dict(ready_for_strict_import=report['ready_for_strict_import'], missing_by_status=dict(Counter(r['status'] for r in rows)),
                unresolved_packages=len(rows), unknown_tables=list(report['unknown_tables']), packages=rows,
                scope='Conservative source availability; not a count of missing visual objects')
