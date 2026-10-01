"""Rail configuration - single source of truth for PSU/channel mapping."""

from __future__ import annotations

from typing import ClassVar

from .models import RailConfig, RailName


class RailRegistry:
    """
    Central registry of all rail configurations.

    This is the single source of truth mapping:
        (PSU, Channel) -> Named Rail -> FIM24725 Pin Group
    """

    # PSU1 - Power and VOA
    VCC_3V3: ClassVar[RailConfig] = RailConfig(
        name=RailName.VCC_3V3,
        psu_name="PSU1",
        channel=1,
        nominal_voltage=3.300,
        nominal_current=0.500,  # Iset: headroom above 400mA max (datasheet Icc typ 360-400mA total)
        max_voltage=3.300,
        ovp=3.600,              # ~9% above Vcc operating max (3.465V)
        ocp=0.700,              # Fault threshold: ~75% above 400mA typ, well above Iset
        verify_voltage=(3.135, 3.465),  # Datasheet Vcc operating range
        verify_current=(0.120, 0.480),  # Relaxed: 120mA lower / 480mA upper (20% above 400mA max)
    )

    VPD_5V0: ClassVar[RailConfig] = RailConfig(
        name=RailName.VPD_5V0,
        psu_name="PSU1",
        channel=2,
        nominal_voltage=5.000,
        nominal_current=0.050,  # Iset: photodiode reverse bias current is µA–mA; 50mA is generous headroom
        max_voltage=5.000,
        ovp=5.500,              # ~5% above VPD operating max (5.25V)
        ocp=0.150,              # Fault threshold: 3× Iset, catches shorts without tripping on normal load
        verify_voltage=(4.75, 5.25),  # Datasheet VPD operating range
    )

    VOA_CTRL: ClassVar[RailConfig] = RailConfig(
        name=RailName.VOA_CTRL,
        psu_name="PSU1",
        channel=3,
        nominal_voltage=2.500,
        nominal_current=0.080,
        max_voltage=4.800,  # Max VOA voltage
        ovp=5.000,
        ocp=0.100,  # Max current 80mA, OCP at 100mA
    )

    # PSU2 - Analog Controls (GA / OA)
    GA_X: ClassVar[RailConfig] = RailConfig(
        name=RailName.GA_X,
        psu_name="PSU2",
        channel=1,
        nominal_voltage=0.0,
        nominal_current=0.020,
        max_voltage=3.300,  # Range 0-VCC
        ovp=3.600,
        ocp=0.020,
    )

    GA_Y: ClassVar[RailConfig] = RailConfig(
        name=RailName.GA_Y,
        psu_name="PSU2",
        channel=2,
        nominal_voltage=0.0,
        nominal_current=0.020,
        max_voltage=3.300,  # Range 0-VCC
        ovp=3.600,
        ocp=0.020,
    )

    OA_X: ClassVar[RailConfig] = RailConfig(
        name=RailName.OA_X,
        psu_name="PSU2",
        channel=3,
        nominal_voltage=0.500,  # Start at minimum; app notes OA range 0.5–2V in AGC mode
        nominal_current=0.020,
        min_voltage=0.000,      # 0V allowed for shutdown (datasheet step 2: controls to 0V);
                                # 0.5V operational floor enforced by API OaRequest(ge=0.5)
        max_voltage=2.000,      # App notes: OA max 2V (above this → clipped/max swing)
        ovp=3.600,
        ocp=0.020,
    )

    OA_Y: ClassVar[RailConfig] = RailConfig(
        name=RailName.OA_Y,
        psu_name="PSU2",
        channel=4,
        nominal_voltage=0.500,  # Start at minimum; app notes OA range 0.5–2V in AGC mode
        nominal_current=0.020,
        min_voltage=0.000,      # 0V allowed for shutdown (datasheet step 2: controls to 0V);
                                # 0.5V operational floor enforced by API OaRequest(ge=0.5)
        max_voltage=2.000,      # App notes: OA max 2V (above this → clipped/max swing)
        ovp=3.600,
        ocp=0.020,
    )

    # Aggregated views
    ALL_RAILS: ClassVar[dict[RailName, RailConfig]] = {
        RailName.VCC_3V3: VCC_3V3,
        RailName.VPD_5V0: VPD_5V0,
        RailName.VOA_CTRL: VOA_CTRL,
        RailName.GA_X: GA_X,
        RailName.GA_Y: GA_Y,
        RailName.OA_X: OA_X,
        RailName.OA_Y: OA_Y,
    }

    # Rail categories
    POWER_RAILS: ClassVar[list[RailName]] = [RailName.VCC_3V3, RailName.VPD_5V0]

    CONTROL_RAILS: ClassVar[list[RailName]] = [
        RailName.VOA_CTRL,
        RailName.GA_X,
        RailName.GA_Y,
        RailName.OA_X,
        RailName.OA_Y,
    ]

    GA_RAILS: ClassVar[list[RailName]] = [RailName.GA_X, RailName.GA_Y]

    OA_RAILS: ClassVar[list[RailName]] = [RailName.OA_X, RailName.OA_Y]

    @classmethod
    def get(cls, name: RailName) -> RailConfig:
        """Get configuration for a rail by name."""
        return cls.ALL_RAILS[name]

    @classmethod
    def get_by_psu_channel(cls, psu_name: str, channel: int) -> RailConfig | None:
        """Get configuration by PSU name and channel number."""
        for config in cls.ALL_RAILS.values():
            if config.psu_name == psu_name and config.channel == channel:
                return config
        return None
