from __future__ import annotations

from utilities.choices import ChoiceSet


class WdmNodeTypeChoices(ChoiceSet):
    TERMINAL_MUX = "terminal_mux"
    OADM = "oadm"
    ROADM = "roadm"
    AMPLIFIER = "amplifier"
    CHOICES = (
        (TERMINAL_MUX, "Terminal MUX"),
        (OADM, "OADM"),
        (ROADM, "ROADM"),
        (AMPLIFIER, "Amplifier"),
    )


class WdmGridChoices(ChoiceSet):
    DWDM_C_100GHZ = "dwdm_c_100ghz"
    DWDM_C_50GHZ = "dwdm_c_50ghz"
    DWDM_L_100GHZ = "dwdm_l_100ghz"
    DWDM_L_50GHZ = "dwdm_l_50ghz"
    CWDM = "cwdm"
    CHOICES = (
        (DWDM_C_100GHZ, "DWDM C-band 100GHz (44ch)"),
        (DWDM_C_50GHZ, "DWDM C-band 50GHz (88ch)"),
        (DWDM_L_100GHZ, "DWDM L-band 100GHz (72ch)"),
        (DWDM_L_50GHZ, "DWDM L-band 50GHz (143ch)"),
        (CWDM, "CWDM (18ch)"),
    )


class WdmLineDirectionChoices(ChoiceSet):
    COMMON = "common"
    EAST = "east"
    WEST = "west"
    CHOICES = (
        (COMMON, "Common"),
        (EAST, "East"),
        (WEST, "West"),
    )


class WdmFiberTypeChoices(ChoiceSet):
    DUPLEX = "duplex"
    SINGLE_FIBER = "single_fiber"

    CHOICES = (
        (DUPLEX, "Duplex", "blue"),
        (SINGLE_FIBER, "Single Fiber", "orange"),
    )


class WdmLineRoleChoices(ChoiceSet):
    TX = "tx"
    RX = "rx"
    BIDI = "bidi"

    CHOICES = (
        (TX, "TX"),
        (RX, "RX"),
        (BIDI, "Bidirectional"),
    )


class WdmChannelStatusChoices(ChoiceSet):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ACTIVE = "active"
    CHOICES = (
        (AVAILABLE, "Available"),
        (RESERVED, "Reserved"),
        (ACTIVE, "Active"),
    )


class WdmCircuitStatusChoices(ChoiceSet):
    PLANNED = "planned"
    STAGED = "staged"
    ACTIVE = "active"
    DECOMMISSIONED = "decommissioned"
    CHOICES = (
        (PLANNED, "Planned"),
        (STAGED, "Staged"),
        (ACTIVE, "Active"),
        (DECOMMISSIONED, "Decommissioned"),
    )
