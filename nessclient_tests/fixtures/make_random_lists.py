"""
fenerates random lists of state combinations for generate_test_packets.py.

Stand-alone script - run this and copy output into generate_test_packets.py.
"""

import enum
import random
from collections.abc import Iterable

from nessclient.event import (
    ArmingUpdate,
    AuxiliaryOutputsUpdate,
    MiscellaneousAlarmsUpdate,
    OutputsUpdate,
    ZoneUpdate,
)


def or_list(vals: list[int]) -> int:
    """Combine integers in list by OR-ing them together."""
    output = 0
    for val in vals:
        output |= val
    return output


def select_bitfield(bitfield: Iterable[enum.Enum]) -> list[int]:
    """
    Select a random sample of bits for an enumerated bitfield.

    Also always adds 0 and the maximum value.
    """
    all_elems = [elem.value for elem in bitfield]

    # Begin with the 'no bits' case
    val_list = [0]
    for k in range(1, len(all_elems)):
        # Take a random subset of 16 values with k zones active
        for _ in range(len(all_elems)):
            while True:
                elem_subset = random.sample(all_elems, k)
                val = or_list(elem_subset)
                if val not in val_list:
                    val_list.append(val)
                    break
    # Add the 'all bits' case
    val_list.append(or_list(all_elems))
    return val_list


# Run this file stand-alone to generate new lists
if __name__ == "__main__":
    print(  # noqa: T201 # Valid CLI print
        "\n"
        "zones_list = ["
        + ", ".join([f"0x{val:04x}" for val in select_bitfield(ZoneUpdate.Zone)])
        + "]"
    )
    print(  # noqa: T201 # Valid CLI print
        "\n"
        "misc_alarm_list = ["
        + ", ".join(
            [
                f"0x{val:04x}"
                for val in select_bitfield(MiscellaneousAlarmsUpdate.AlarmType)
            ]
        )
        + "]"
    )
    print(  # noqa: T201 # Valid CLI print
        "\n"
        "arming_list =["
        + ", ".join(
            [f"0x{val:04x}" for val in select_bitfield(ArmingUpdate.ArmingStatus)]
        )
        + "]"
    )
    print(  # noqa: T201 # Valid CLI print
        "\n"
        "output_list = ["
        + ", ".join(
            [f"0x{val:04x}" for val in select_bitfield(OutputsUpdate.OutputType)]
        )
        + "]"
    )
    print(  # noqa: T201 # Valid CLI print
        "\n"
        "auxoutput_list = ["
        + ", ".join(
            [
                f"0x{val:04x}"
                for val in select_bitfield(AuxiliaryOutputsUpdate.OutputType)
            ]
        )
        + "]"
    )
