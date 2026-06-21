import os

paths = [
    "/home/ubuntu/lxc-manager/projects/mashupsoat/mysuf_backend/.env",
    "/home/ubuntu/lxc-manager/projects/mashupsoat/mysuf_backend/app/core/config.py"
]

for p in paths:
    if os.path.exists(p):
        print(f"--- {p} ---")
        try:
            with open(p, "r") as f:
                print(f.read())
        except Exception as e:
            print(f"Error reading {p}: {e}")
    else:
        print(f"Path does not exist: {p}")
