import os
port=(os.getenv("APP_PORT", "5000"))
bind = "0.0.0.0:" + port
workers = 1
threads = 4
timeout = 120
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
