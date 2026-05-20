# FIM24725 Control System — Wiring Schema

## Full System Wiring

```mermaid
graph LR
    subgraph rpi["Raspberry Pi 3B"]
        ETH0["eth0\n10.10.10.50"]
        ETH1["eth1 (USB adapter)\n10.10.20.50"]
        USB_HOST["USB Host"]
        TS["Tailscale\n100.x.x.x"]
    end

    subgraph psu1["PSU1 — MP710508"]
        PSU1_ETH["UDP :20001\n10.10.10.137"]
        PSU1_CH1["Ch1 → VCC_3V3"]
        PSU1_CH2["Ch2 → VPD_5V0"]
        PSU1_CH3["Ch3 → VOA_CTRL"]
    end

    subgraph psu2["PSU2 — MP710508"]
        PSU2_ETH["UDP :20002\n10.10.20.137"]
        PSU2_CH1["Ch1 → GA_X"]
        PSU2_CH2["Ch2 → GA_Y"]
        PSU2_CH3["Ch3 → OA_X"]
        PSU2_CH4["Ch4 → OA_Y"]
    end

    subgraph arduino["Arduino Uno R3"]
        PIN3V3["3.3V pin"]
        AREF["AREF pin"]
        D2["D2"]
        D3["D3"]
        A0["A0"]
        A1["A1"]
        A2["A2"]
        A3["A3"]
        A4["A4"]
        A5["A5"]
        GND_A["GND"]
        USB_DEV["USB-B"]
    end

    subgraph divider_d2["D2 Divider"]
        R1_D2["33k"]
        R2_D2["22k"]
    end

    subgraph divider_d3["D3 Divider"]
        R1_D3["33k"]
        R2_D3["22k"]
    end

    subgraph pulldowns["ADC Pull-downs (100k to GND)"]
        PD0["100k"]
        PD1["100k"]
        PD2["100k"]
        PD3["100k"]
        PD4["100k"]
        PD5["100k"]
    end

    subgraph fim["FIM24725 Module"]
        SD["SD pin 32"]
        MC["MC/AGC pin 3"]
        VCC_Y["VCC_Y pin 13"]
        VCC_X["VCC_X pin 22"]
        VPD["VPD pins 6-9, 26-29"]
        VOA1["VOA1 pin 31"]
        GA_XI["GA_XI pin 21"]
        GA_XQ["GA_XQ pin 20"]
        GA_YI["GA_YI pin 14"]
        GA_YQ["GA_YQ pin 15"]
        OA_XI["OA_XI pin 19"]
        OA_XQ["OA_XQ pin 25"]
        OA_YI["OA_YI pin 16"]
        OA_YQ["OA_YQ pin 15"]
        PI_XI["PI-XI pin 18"]
        PI_XQ["PI-XQ pin 25"]
        PI_YI["PI-YI pin 10"]
        PI_YQ["PI-YQ pin 17"]
        MPD_P["MPD+ pin 4"]
        MPD_N["MPD- pin 5"]
    end

    %% Raspberry Pi to PSUs (Ethernet/UDP)
    ETH0 ---|"Ethernet\n10.10.10.0/24"| PSU1_ETH
    ETH1 ---|"Ethernet\n10.10.20.0/24"| PSU2_ETH

    %% Raspberry Pi to Arduino (USB serial)
    USB_HOST ---|"USB serial\n115200 baud"| USB_DEV

    %% AREF: direct connection, no capacitor
    PIN3V3 --- AREF

    %% D2 voltage divider chain
    D2 --- R1_D2
    R1_D2 --- R2_D2
    R2_D2 --- GND_A
    R1_D2 --- SD

    %% D3 voltage divider chain
    D3 --- R1_D3
    R1_D3 --- R2_D3
    R2_D3 --- GND_A
    R1_D3 --- MC

    %% ADC inputs from FIM24725 with 100k pull-downs
    PI_XI --- A0
    PI_XQ --- A1
    PI_YI --- A2
    PI_YQ --- A3
    MPD_P --- A4
    MPD_N --- A5

    A0 --- PD0
    A1 --- PD1
    A2 --- PD2
    A3 --- PD3
    A4 --- PD4
    A5 --- PD5
    PD0 --- GND_A
    PD1 --- GND_A
    PD2 --- GND_A
    PD3 --- GND_A
    PD4 --- GND_A
    PD5 --- GND_A

    %% PSU1 supply rails to FIM24725
    PSU1_CH1 --- VCC_Y
    PSU1_CH1 --- VCC_X
    PSU1_CH2 --- VPD
    PSU1_CH3 --- VOA1

    %% PSU2 control rails to FIM24725
    PSU2_CH1 --- GA_XI
    PSU2_CH1 --- GA_XQ
    PSU2_CH2 --- GA_YI
    PSU2_CH2 --- GA_YQ
    PSU2_CH3 --- OA_XI
    PSU2_CH3 --- OA_XQ
    PSU2_CH4 --- OA_YI
    PSU2_CH4 --- OA_YQ
```

## Circuit Details

### AREF (Analogue Reference)

```
Arduino 3.3V pin ──── AREF pin (direct connection)
                       │
               analogReference(EXTERNAL)
               ADC range: 0-3.3V
               Resolution: 3.3V / 1024 = 3.2 mV/count
```

### Voltage Dividers (D2 and D3)

```
Arduino D2/D3 (5V digital output)
      │
    [33k]   series resistor
      │
      ├──────── output to FIM24725 pin
      │           Vout = 5V x 22k/(33k+22k) = 2.0V
    [22k]   pull-down to ground
      │
     GND

When pin = HIGH (5V):  output = 2.0V  (FIM24725 HIGH threshold: 2.0V-VCC)
When pin = LOW  (0V):  output = 0.0V  (FIM24725 LOW threshold:  0-0.8V)
```

### ADC Inputs (A0-A5)

```
FIM24725 PI/MPD output ──── Arduino Ax (ADC input)
                              │
                           [100k]   pull-down resistor
                              │
                             GND

Pull-downs ensure ADC reads 0V when module is off
(pins would otherwise float to undefined voltage).
100k is high enough not to load the PI/MPD outputs.
Signal range: 0-2V
ADC range:    0-3.3V (set by AREF)
Utilises ~62% of ADC range (0-621 counts)
```

### Ethernet (Raspberry Pi to PSUs)

```
Raspberry Pi
  eth0  (onboard)       ──── Ethernet ──── PSU1  10.10.10.137:20001
  10.10.10.50                               (VCC_3V3, VPD_5V0, VOA_CTRL)

  eth1  (USB adapter)   ──── Ethernet ──── PSU2  10.10.20.137:20002
  10.10.20.50                               (GA_X, GA_Y, OA_X, OA_Y)

  wlan0 / eth (Tailscale) ── WireGuard ── Remote user (100.x.x.x)
```
