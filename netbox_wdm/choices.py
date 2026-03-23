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
    DWDM_100GHZ = "dwdm_100ghz"
    DWDM_50GHZ = "dwdm_50ghz"
    CWDM = "cwdm"
    CHOICES = (
        (DWDM_100GHZ, "DWDM C-band 100GHz (44ch)"),
        (DWDM_50GHZ, "DWDM C-band 50GHz (88ch)"),
        (CWDM, "CWDM (18ch)"),
    )


class WdmTrunkDirectionChoices(ChoiceSet):
    COMMON = "common"
    EAST = "east"
    WEST = "west"
    CHOICES = (
        (COMMON, "Common"),
        (EAST, "East"),
        (WEST, "West"),
    )


class WavelengthChannelStatusChoices(ChoiceSet):
    AVAILABLE = "available"
    RESERVED = "reserved"
    LIT = "lit"
    CHOICES = (
        (AVAILABLE, "Available"),
        (RESERVED, "Reserved"),
        (LIT, "Lit"),
    )


class WavelengthServiceStatusChoices(ChoiceSet):
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
