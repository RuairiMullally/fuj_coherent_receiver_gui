## PSU_IP = "192.168.1.198" #10.10.10.137


import socket
import time

PSU_IP = "10.10.10.137"
PSU_PORT = 18190

LOCAL_IP = "10.10.10.50"   # your Windows Ethernet IP
LOCAL_PORT = 18190
TERM = b"\n"

def _sock():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((LOCAL_IP, LOCAL_PORT))
    return s

def query(cmd: str) -> str:
    msg = cmd.encode("ascii") + TERM
    with _sock() as s:
        s.sendto(msg, (PSU_IP, PSU_PORT))
        data, _ = s.recvfrom(4096)
        return data.decode("ascii", errors="replace").strip()

def set_cmd(cmd: str) -> None:
    msg = cmd.encode("ascii") + TERM
    with _sock() as s:
        s.sendto(msg, (PSU_IP, PSU_PORT))
    time.sleep(0.05)

if __name__ == "__main__":
    print("ID:", query("*IDN?"))  # :contentReference[oaicite:3]{index=3}

    # Keep output OFF for safety (no load connected)
    set_cmd("OUT1:0")             # :contentReference[oaicite:4]{index=4}

    # Optional: lock front panel so nothing overrides your setpoints
    # set_cmd("LOCK:1")           # :contentReference[oaicite:5]{index=5}
    set_cmd("LOCK:0")             # unlock (also valid boolean) :contentReference[oaicite:6]{index=6}

    print("Starting sweep. Watch CH1 V/I setpoints on the screen...")

    # --- Voltage sweep on CH1 (setpoint only) ---
    for v in [0, 1, 2.5, 5, 7.5, 10, 7.5, 5, 2.5, 1, 0]:
        set_cmd(f"VSET1:{v:.3f}")                     # :contentReference[oaicite:7]{index=7}
        vset = query("VSET1?")                        # :contentReference[oaicite:8]{index=8}
        print("VSET1?", vset)
        time.sleep(0.6)  # slow enough to watch on the display

    # --- Current sweep on CH1 (setpoint only) ---
    for i in [0.1, 0.2, 0.5, 1.0, 0.5, 0.2, 0.1]:
        set_cmd(f"ISET1:{i:.3f}")                     # :contentReference[oaicite:9]{index=9}
        iset = query("ISET1?")                        # :contentReference[oaicite:10]{index=10}
        print("ISET1?", iset)
        time.sleep(0.6)

    # # --- set static IP for deployment ---
    # set_cmd(":SYSTem:DHCP OFF")                 # disable DHCP :contentReference[oaicite:1]{index=1}
    # set_cmd(":SYSTem:IPAddress 10.10.10.137")    # new static IP :contentReference[oaicite:2]{index=2}
    # set_cmd(":SYSTem:SMASK 255.255.255.0")       # subnet mask :contentReference[oaicite:3]{index=3}
    # set_cmd(":SYSTem:GATEway 10.10.10.1")        # lab gateway :contentReference[oaicite:4]{index=4}


    print("Done. Outputs remain OFF.")
