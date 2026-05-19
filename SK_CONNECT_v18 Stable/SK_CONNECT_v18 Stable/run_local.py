from app import app, get_local_ip

try:
    local_ip = get_local_ip()
except Exception:
    local_ip = '127.0.0.1'
print(f"App starting. Open on this machine: http://127.0.0.1:5002")
print(f"App reachable on your LAN at: http://{local_ip}:5002")
app.run(host='0.0.0.0', debug=True, port=5002)
