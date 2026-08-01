import sys
sys.path.insert(0, '.')
from api.routes import health, analyze, batch, headers, urls, attachments, explain

for name, router in [
    ('health', health.router),
    ('analyze', analyze.router),
    ('batch', batch.router),
    ('headers', headers.router),
    ('urls', urls.router),
    ('attachments', attachments.router),
    ('explain', explain.router),
]:
    routes = [str(list(r.methods)) + ' ' + r.path for r in router.routes if hasattr(r, 'methods')]
    if routes:
        print(name + ': ' + str(routes))
    else:
        print(name + ': EMPTY - no routes defined')
