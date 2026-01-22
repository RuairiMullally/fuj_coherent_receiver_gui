import platform
from datetime import datetime

def main():
    print("Hello from fuj_coherent_receiver_gui!")
    print("Time:", datetime.now().isoformat(timespec="seconds"))
    print("Platform:", platform.platform())

if __name__ == "__main__":
    main()
