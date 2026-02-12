from src.fuj_backend.services import FIM24725Service, OperatingMode

# Each PSU is on a separate ethernet adapter.
# NIC 1 (10.10.10.50) -> PSU1 (10.10.10.137)
# NIC 2 (10.10.10.51) -> PSU2 (10.10.10.138)
service = FIM24725Service(
    psu1_ip="10.10.10.137", psu1_port=20001, psu1_local_ip="10.10.10.50",
    psu2_ip="10.10.10.138", psu2_port=20002, psu2_local_ip="10.10.10.51",
)

service.startup()          # Full sequenced bring-up
service.set_voa(2.4)       # Adjust VOA
service.set_oa_x(1.65)     # Adjust OA
service.get_snapshot()     # Read all measurements
service.shutdown()         # Safe shutdown
