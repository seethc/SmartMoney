"""Launch the local-only SmartMoney server."""
import uvicorn
import os
from smartmoney import config

if __name__ == '__main__':
    if os.name == 'posix':
        os.umask(0o077)
    # Avoid recording private browsing paths or queries in routine access logs.
    uvicorn.run('smartmoney.app:app', host='127.0.0.1', port=8765, access_log=False,
                proxy_headers=True, forwarded_allow_ips='127.0.0.1', limit_concurrency=8)
