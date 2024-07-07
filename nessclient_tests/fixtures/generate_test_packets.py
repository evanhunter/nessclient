import enum
from datetime import datetime

from nessclient.event import (
    ZoneUpdate,
    StatusUpdate,
    MiscellaneousAlarmsUpdate,
    ArmingUpdate,
    OutputsUpdate,
    ViewStateUpdate,
    AuxiliaryOutputsUpdate,
    PanelVersionUpdate,
)
import random


def Gemerate_Input_To_Ness_User_Interface_Valid_Packets() -> list[tuple[str, str]]:
    Input_To_Ness_User_Interface_Valid_Packets: list[tuple[str, str]] = []
    data = "AHEXFVPDM*#0123456789SAHEXFVPD"
    for address in range(0x0, 0xF + 1):
        for length in range(1, 30 + 1):
            packet = f"83{address:x}{length:02x}60{data[0:length]}"
            checksum = (256 - sum([ord(x) for x in packet])) % 256
            packet = f"{packet}{checksum:02X}"
            Input_To_Ness_User_Interface_Valid_Packets.append(
                (
                    packet,
                    f"Input UI request to address {address} with {length} bytes of data",
                )
            )
    return Input_To_Ness_User_Interface_Valid_Packets


def Gemerate_Data_For_Output_From_Ness_Event_Data_Packets() -> list[tuple[str, str]]:

    class AlarmArea(enum.Enum):
        Area1 = 0x01
        Area2 = 0x02
        Home = 0x03
        Day = 0x04
        TwentyFourHour = 0x80
        Fire = 0x81
        Panic = 0x82
        Medical = 0x83
        Duress = 0x84
        Door = 0x85

    class OutputType(enum.Enum):
        AUX1 = 1
        AUX2 = 2
        AUX3 = 3
        AUX4 = 4
        AUX5 = 5
        AUX6 = 6
        AUX7 = 7
        AUX8 = 8
        AUX9 = 9
        AUX10 = 10
        Siren = 90
        Soft_Siren = 91
        Soft_Home = 92
        Siren_Fire = 93
        Strobe = 94
        Reset = 95
        Sonalert = 96
        Keypad_Display_Enable = 97

    zone_range = list(range(1, 16 + 1))
    user_range = list(range(1, 56 + 1))

    data: list[tuple[str, str]] = []

    # Zone or User EVENTS
    data.append(("010000", "Power up or reset"))

    for zone in zone_range:
        data.append((f"00{zone:02d}00", f"Unsealed Zone {zone} Current zone state"))
        data.append((f"01{zone:02d}00", f"Sealed   Zone {zone} Current zone state"))

    for user in user_range:
        for door in range(1, 3 + 1):
            data.append(
                (f"00{user:02d}a{door:x}", f"Unsealed User {user} access door {door}")
            )
            data.append(
                (f"01{user:02d}a{door:x}", f"Sealed   User {user} access door {door}")
            )

    for zone in zone_range:
        for area in [
            AlarmArea.Area1,
            AlarmArea.Area2,
            AlarmArea.Home,
            AlarmArea.Day,
            AlarmArea.TwentyFourHour,
            AlarmArea.Fire,
            AlarmArea.Door,
        ]:
            data.append(
                (
                    f"02{zone:02d}{area.value:02x}",
                    f"Alarm         zone {zone} & area {area}",
                )
            )
            data.append(
                (
                    f"03{zone:02d}{area.value:02x}",
                    f"Alarm Restore zone {zone} & area {area}",
                )
            )

    for area in [AlarmArea.Fire, AlarmArea.Panic, AlarmArea.Medical, AlarmArea.Duress]:
        data.append((f"02f0{area.value:02x}", f"Alarm         Area {area} Keypad"))
        data.append((f"03f0{area.value:02x}", f"Alarm Restore Area {area} Keypad"))

    for user in user_range:
        data.append((f"02{user:02d}82", f"Alarm         User {user} Radio Panic"))
        data.append((f"03{user:02d}82", f"Alarm Restore User {user} Radio Panic"))

    data.append(("020082", "Alarm Keyswitch Panic"))
    data.append(("030082", "Alarm Restore Keyswitch Panic"))

    for zone in zone_range:
        data.append(
            (f"04{zone:02d}00", f"Manual Exclude zone {zone}")
        )  # TODO: Can this take an area?
        data.append(
            (f"05{zone:02d}00", f"Manual Include zone {zone}")
        )  # TODO: Can this take an area?

    for zone in zone_range:
        data.append(
            (f"06{zone:02d}00", f"Auto Exclude zone {zone}")
        )  # TODO: Can this take an area?
        data.append(
            (f"07{zone:02d}00", f"Auto Include zone {zone}")
        )  # TODO: Can this take an area?

    data.append(("080000", "Tamper Unsealed Main Unit Internal Tamper"))
    data.append(("090000", "Tamper Normal   Main Unit Internal Tamper"))
    data.append(("080001", "Tamper Unsealed Main Unit External Tamper"))
    data.append(("090001", "Tamper Normal   Main Unit External Tamper"))
    data.append(("08f000", "Tamper Unsealed Keypad Tamper"))
    data.append(("09f000", "Tamper Normal   Keypad Tamper"))

    for zone in zone_range:
        data.append((f"08{zone:02d}91", f"Radio Detector Tamper Zone {zone} Unsealed"))
        data.append((f"09{zone:02d}91", f"Radio Detector Tamper Zone {zone} Normal"))

    # System EVENTS
    data.append(("100000", "Power Failure AC Mains Fail"))
    data.append(("110000", "Power Normal  AC Mains Restored"))
    data.append(("120000", "Battery Failure - Main Battery"))
    data.append(("130000", "Battery Normal  - Main Battery"))
    for user in user_range:
        data.append(
            (f"12{user:02d}92", f"Battery Failure user {user} - Radio Key Battery")
        )
        data.append(
            (f"13{user:02d}92", f"Battery Normal  user {user} - Radio Key Battery")
        )

    for zone in zone_range:
        data.append(
            (f"12{zone:02d}91", f"Battery Failure zone {zone} - Radio Detector Battery")
        )
        data.append(
            (f"13{zone:02d}91", f"Battery Normal  zone {zone} - Radio Detector Battery")
        )

    data.append(("140000", "Report Failure - Dialer Failed to Report"))
    data.append(("150000", "Report Normal"))

    for zone in zone_range:
        data.append((f"16{zone:02d}00", f"Supervision Zone {zone} Failure"))
        data.append((f"17{zone:02d}00", f"Supervision Zone {zone} Normal"))

    data.append(("190000", "Real Time Clock - RTC Time or Date Changed"))

    # Area EVENTS
    for zone in zone_range:
        for area in [AlarmArea.Area1, AlarmArea.Area2, AlarmArea.Home]:
            data.append(
                (
                    f"20{zone:02d}{area.value:02x}",
                    f"Entry Delay Start zone {zone} - When Armed in Area {area}",
                )
            )
            data.append(
                (
                    f"21{zone:02d}{area.value:02x}",
                    f"Entry Delay End   zone {zone} - When Armed in Area {area}",
                )
            )

    for zone in zone_range:
        data.append(
            (
                f"22{zone:02d}{area.value:02x}",
                f"Exit  Delay Start zone {zone}- When Armed in Area {area}",
            )
        )
        data.append(
            (
                f"23{zone:02d}{area.value:02x}",
                f"Exit  Delay End   zone {zone}- When Armed in Area {area}",
            )
        )

    for user in user_range:
        for area in [AlarmArea.Area1, AlarmArea.Area2]:
            data.append(
                (
                    f"24{user:02d}{area.value:02x}",
                    f"Armed Away user {user} - area {area}",
                )
            )

    for area in [AlarmArea.Area1, AlarmArea.Area2]:
        data.append((f"2457{area.value:02x}", f"Armed Away keyswitch - area {area}"))
        data.append((f"2458{area.value:02x}", f"Armed Away Short Arm - area {area}"))

    for user in user_range:
        data.append((f"25{user:02d}03", f"Armed Home user {user}"))

    data.append(("255703", "Armed Home Keyswitch"))
    data.append(("255803", "Armed Home Short Arm"))

    data.append(("260004", "Armed Day"))
    data.append(("270000", "Armed Night"))
    data.append(("280000", "Armed Vacation"))
    data.append(("2e0000", "Armed Highest"))

    for user in user_range:
        for area in [AlarmArea.Area1, AlarmArea.Area2, AlarmArea.Home, AlarmArea.Day]:
            data.append(
                (f"2f{user:02d}{area.value:02x}", f"Disarmed user {user}, area {area}")
            )

    for area in [AlarmArea.Area1, AlarmArea.Area2, AlarmArea.Home, AlarmArea.Day]:
        data.append((f"2f57{area.value:02x}", f"Disarmed Keyswitch, area {area}"))

    for user in user_range:
        for area in [AlarmArea.Area1, AlarmArea.Area2, AlarmArea.Home]:
            data.append(
                (
                    f"2f{user:02d}{area.value:02x}",
                    f"Arming Delayed user {user}, area {area}",
                )
            )

    # Result EVENTS
    for output in OutputType:
        data.append((f"31{output.value:02d}00", f"Output {output} On"))
        data.append((f"32{output.value:02d}00", f"Output {output} Off"))

    return data


def Gemerate_Output_From_Ness_Event_Data_Valid_Packets() -> list[tuple[str, str]]:
    Output_From_Ness_Event_Data_Valid_Data = (
        Gemerate_Data_For_Output_From_Ness_Event_Data_Packets()
    )

    Output_From_Ness_Event_Data_Valid_Packets = []
    for start in ["82", "83", "86", "87"]:
        for address in range(0x0, 0xF + 1):
            for seq in [0, 8]:
                for data, name in Output_From_Ness_Event_Data_Valid_Data:
                    if start == "83" or start == "87":
                        packet = f"{start}{address:02x}{seq}361{data}"
                    else:
                        packet = f"{start}{seq}361{data}"
                    if start == "86" or start == "87":
                        packet += datetime.now().strftime("%y%m%d%H%M%S")

                    total = 0
                    for pos in range(0, len(packet), 2):
                        total += int(packet[pos : pos + 2], 16)
                    checksum = (256 - total) % 256
                    packet = f"{packet}{checksum:02x}"

                    Output_From_Ness_Event_Data_Valid_Packets.append(
                        (
                            packet,
                            f"{name} for address {address} "
                            f"with start={start} and seq={seq}",
                        )
                    )

    return Output_From_Ness_Event_Data_Valid_Packets


# Randomly generated combinations for bit-field values

# fmt: off
zones_list = [
    0x0000,
    0x0100, 0x0020, 0x4000, 0x0008, 0x0800, 0x0040, 0x8000, 0x2000,
    0x0001, 0x0080, 0x1000, 0x0400, 0x0200, 0x0004, 0x0002, 0x0010,
    0x000c, 0x0044, 0x0240, 0x00c0, 0x0022, 0x2040, 0x2800, 0x0440,
    0x0401, 0x1010, 0x8004, 0x1008, 0x8002, 0x1800, 0x0c00, 0x0104,
    0x8042, 0x8021, 0x2808, 0x0580, 0x4802, 0x4006, 0x0203, 0x0301,
    0x8a00, 0x2110, 0x3020, 0x2050, 0x0901, 0x20a0, 0x4081, 0x4018,
    0x8805, 0x1430, 0x0492, 0x480c, 0x2501, 0x9c00, 0x2a40, 0x1428,
    0x40a2, 0x4070, 0x4822, 0x5408, 0x00d8, 0x2105, 0x2320, 0x4444,
    0x9501, 0x0516, 0xa301, 0x5218, 0x8185, 0x09c8, 0xa450, 0x2d20,
    0x4a09, 0x8099, 0xa0c1, 0x0591, 0x700a, 0x6403, 0x1d10, 0x1131,
    0x2ce0, 0x3d04, 0x9641, 0xa681, 0xa88a, 0x0c17, 0x842d, 0x804f,
    0x7142, 0xc294, 0x032e, 0x4525, 0xa426, 0x8c2a, 0xa8b0, 0xa261,
    0xc992, 0xcc61, 0x1a39, 0xba82, 0x8c5c, 0xb30a, 0xb426, 0x0ee2,
    0x9945, 0x894b, 0xa525, 0xc561, 0x906b, 0x5d90, 0x4c4d, 0x50f2,
    0x3b94, 0x3647, 0xc693, 0xa365, 0xf452, 0xc32e, 0xa9a3, 0xe227,
    0x2e6a, 0xf162, 0xa1ba, 0xece0, 0x98a7, 0xe1ac, 0x5791, 0xcf12,
    0x70fc, 0xbc5a, 0xd476, 0xa2b7, 0x32f5, 0xe70e, 0x554f, 0xd749,
    0x5769, 0xba4d, 0xc38f, 0x75b2, 0xfb14, 0xbe91, 0x70bd, 0xab66,
    0xcbce, 0x6ed3, 0x2f8f, 0xbca7, 0x47ee, 0xed0f, 0x35dd, 0xbd65,
    0x787d, 0xbe99, 0xbc6e, 0x77aa, 0x7ee1, 0xc3bb, 0x6bd6, 0xa7e3,
    0x65bf, 0xcddd, 0x7f5c, 0xf6e9, 0xcf3d, 0x37bb, 0xdb8f, 0xbef4,
    0xb9bd, 0xafe6, 0xfe47, 0xdb7c, 0x4fe7, 0xf65b, 0x7d8f, 0x7cfa,
    0xbbed, 0xdedd, 0x3cff, 0xfd5d, 0x73fb, 0x7fce, 0x8ffb, 0xffb4,
    0xf3be, 0xabfe, 0xff56, 0x56ff, 0xfbab, 0xd7db, 0x5efd, 0xf757,
    0xcffe, 0xbfeb, 0xdbfd, 0x5dff, 0xcdff, 0xaf7f, 0xf5fe, 0xfe77,
    0xff3d, 0xb9ff, 0xdbbf, 0xfbb7, 0xbefe, 0x7bf7, 0xeddf, 0x7cff,
    0xf9ff, 0xffbd, 0x7f7f, 0xdffe, 0xbbff, 0xfdf7, 0xffb7, 0x7ffd,
    0xebff, 0xdff7, 0xffcf, 0xbfef, 0xdfbf, 0x7eff, 0xfbf7, 0x7fbf,
    0xffdf, 0xfffb, 0xfff7, 0xbfff, 0xff7f, 0xefff, 0xfffd, 0xdfff,
    0xffef, 0x7fff, 0xfdff, 0xfeff, 0xffbf, 0xfffe, 0xfbff, 0xf7ff,
    0xffff
]

misc_alarm_list = [
    0x0000,
    0x0002, 0x4000, 0x0200, 0x0800, 0x0400, 0x0004, 0x8000,
    0x0100, 0x0001, 0x0010, 0x2000, 0x1000, 0x0008,
    0x8008, 0x1800, 0x2800, 0x2004, 0x9000, 0x4800, 0x2001,
    0x8002, 0x4002, 0x0c00, 0x6000, 0x0404, 0x0018,
    0xc004, 0x2600, 0x8900, 0x0403, 0x2006, 0x4102, 0x8202,
    0x4408, 0x800c, 0x2005, 0x1003, 0x8802, 0x2009,
    0x3804, 0x180c, 0x2a01, 0xb200, 0xcc00, 0x8818, 0x4508,
    0xc202, 0x8016, 0x0813, 0x9014, 0xc408, 0x4212,
    0x801b, 0x5406, 0x2509, 0x4306, 0x400f, 0x2e08, 0x4512,
    0xe804, 0x0709, 0xec00, 0x4506, 0x411c, 0x900d,
    0x1307, 0x900f, 0xa609, 0x3909, 0x8c15, 0x990a, 0x141b,
    0x2e05, 0x710c, 0x9216, 0x2d03, 0x2a0b, 0xd814,
    0x8a1d, 0xa31c, 0x6b06, 0x7c0c, 0xca1c, 0xb407, 0xe50c,
    0x3817, 0x431d, 0xa30e, 0x2e15, 0x8e0d, 0x460f,
    0x0d1f, 0x1d17, 0x790b, 0xdf10, 0x781d, 0xfa11, 0x670d,
    0xbf01, 0x3b13, 0x7f04, 0x8d1e, 0xee0c, 0xa51e,
    0xc51f, 0xfd12, 0x7e19, 0xe70d, 0xf10f, 0x7f0a, 0x5f0b,
    0x5f0e, 0x3f0b, 0xbf11, 0xf319, 0xd716, 0x9e1d,
    0xb71b, 0xfe19, 0xee1b, 0xf719, 0xf617, 0x9b1f, 0xeb1d,
    0xed1d, 0xe71d, 0xe61f, 0xaf1e, 0xdf15, 0xd71e,
    0xfa1f, 0xbf1d, 0x7d1f, 0xfe1e, 0xcf1f, 0x7f17, 0xfb0f,
    0xfd17, 0xfb1e, 0x9f1f, 0xbf0f, 0x3f1f, 0xdf1b,
    0xff1e, 0x7f1f, 0xff1b, 0xbf1f, 0xff1d, 0xff0f, 0xdf1f,
    0xfb1f, 0xfe1f, 0xff17, 0xf71f, 0xef1f, 0xfd1f,
    0xff1f
]

arming_list = [
    0x0000,
    0x0100, 0x4000, 0x2000, 0x0800, 0x0400, 0x0002,
    0x0001, 0x0200, 0x8000, 0x1000, 0x0004,
    0x0401, 0x1004, 0x4001, 0x0300, 0x0402, 0x0202,
    0x2004, 0x0404, 0x0104, 0x8002, 0x4200,
    0x4003, 0x8201, 0x8404, 0x3400, 0x4500, 0x0b00,
    0x1801, 0x1102, 0x4300, 0x8006, 0x6800,
    0x0305, 0x4304, 0xa801, 0x8a04, 0x4c01, 0x5202,
    0x6102, 0xa003, 0x1602, 0xa804, 0xaa00,
    0x3601, 0x1903, 0xa806, 0x1303, 0xdc00, 0x7003,
    0x8f00, 0xe600, 0xda00, 0xe404, 0x5205,
    0xce01, 0x6606, 0xf402, 0x9704, 0xe602, 0xab01,
    0x1f01, 0xae02, 0xba02, 0x1703, 0x3d04,
    0x7c05, 0x7e04, 0x1f05, 0xc907, 0xd107, 0x6703,
    0x2f05, 0x5f01, 0x4f03, 0x5b03, 0x8f06,
    0xc707, 0xf305, 0xd907, 0x7c07, 0xdd03, 0xad07,
    0xdd06, 0xed05, 0xb705, 0xeb05, 0xeb06,
    0xef05, 0xaf07, 0x7e07, 0xef06, 0xf705, 0xbe07,
    0x7b07, 0xef03, 0x6f07, 0xfe03, 0xed07,
    0xbf07, 0xff05, 0xff03, 0xef07, 0xf707, 0xfb07,
    0xff06, 0x7f07, 0xfe07, 0xdf07, 0xfd07,
    0xff07
]

output_list = [
    0x0000,
    0x4000, 0x0080, 0x0800, 0x2000, 0x0002, 0x0200, 0x1000, 0x0040,
    0x8000, 0x0100, 0x0400, 0x0020, 0x0001, 0x0010, 0x0004, 0x0008,
    0x4400, 0x000a, 0x8100, 0x0804, 0x0140, 0x0044, 0x0220, 0x0104,
    0x0c00, 0x0084, 0x0208, 0x0028, 0x5000, 0x4200, 0x4100, 0x0a00,
    0x0118, 0x6010, 0x1050, 0x2404, 0x4041, 0x4408, 0x9002, 0x4220,
    0x6040, 0x0414, 0x0211, 0x4c00, 0x2204, 0x3020, 0xa010, 0x2820,
    0x00b8, 0x1490, 0x1141, 0x0831, 0x102c, 0x04a2, 0x1c08, 0x4228,
    0xc005, 0x9044, 0x00e2, 0x0960, 0x8980, 0xa108, 0x5810, 0xe200,
    0x1125, 0x5a10, 0x3680, 0x2854, 0x841c, 0x090b, 0xc818, 0x6980,
    0x41e0, 0xd011, 0x6160, 0x2462, 0x1614, 0x2c41, 0x30b0, 0x4065,
    0x6b10, 0x44ca, 0x0857, 0x2a13, 0xe421, 0x07b0, 0x4d60, 0x3309,
    0x0b15, 0x0c87, 0x24a6, 0xca50, 0x1721, 0x29e0, 0x12c5, 0x14d1,
    0xd503, 0x4f12, 0x7c18, 0x47a2, 0x01cf, 0x9c45, 0xd485, 0xbc18,
    0xd027, 0x9271, 0x8157, 0xba22, 0x139a, 0x183b, 0xa325, 0xc1b1,
    0x3b85, 0xb8a6, 0x651b, 0x15ba, 0x116f, 0x4cd5, 0x9fa0, 0x3695,
    0x5671, 0xaba2, 0x05cf, 0x632d, 0x4aa7, 0x50b7, 0x86f8, 0x54f4,
    0x71e6, 0x30f7, 0x53d9, 0xecd2, 0x954f, 0xe333, 0x9af1, 0x64bb,
    0xb51e, 0xa7b2, 0xfa1a, 0x798b, 0x89b7, 0x6ee2, 0x5cda, 0x5d33,
    0xef54, 0xec1f, 0xf6a9, 0x38ef, 0x55e7, 0xef86, 0xf4b3, 0x93f6,
    0x793b, 0x1fcd, 0xf359, 0xd5d3, 0xef83, 0x7b55, 0xbf2a, 0xac7b,
    0x58ff, 0xbcbd, 0xeeab, 0xfe1d, 0xbaeb, 0xfd69, 0x2ff5, 0xd75d,
    0x7dad, 0x8edf, 0x737e, 0xb3fa, 0xe67e, 0x7cfa, 0xf6f1, 0xf3da,
    0xcfdb, 0xbe5f, 0xd77d, 0x777b, 0xbddb, 0xafdb, 0xbf5b, 0x76bf,
    0x9fbe, 0x9fed, 0xfbf4, 0xb5fb, 0x775f, 0xfcaf, 0x3fbe, 0xde9f,
    0x9eff, 0xf7ed, 0x76ff, 0xeefd, 0xfbdb, 0x5f7f, 0xe7ef, 0xfebb,
    0xee7f, 0x3fdf, 0xf77b, 0xbbfb, 0xcf7f, 0xf9fd, 0xff3d, 0xbeef,
    0xbbff, 0xffb7, 0xbffb, 0xffeb, 0xdff7, 0xbfef, 0xdfdf, 0xdf7f,
    0xbfdf, 0xffee, 0xf7fd, 0x7eff, 0xef7f, 0xfcff, 0xeff7, 0xefef,
    0xfffd, 0xf7ff, 0xfbff, 0xffef, 0x7fff, 0xffdf, 0xfff7, 0xffbf,
    0xfdff, 0xdfff, 0xfffb, 0xfeff, 0xfffe, 0xbfff, 0xff7f, 0xefff,
    0xffff
]

auxoutput_list = [
    0x0000,
    0x0001, 0x0020, 0x0040, 0x0004, 0x0008, 0x0010, 0x0002, 0x0080,
    0x0084, 0x0081, 0x0021, 0x0042, 0x000c, 0x0028, 0x0082, 0x0022,
    0x0045, 0x001c, 0x0064, 0x0013, 0x00d0, 0x0083, 0x004c, 0x0098,
    0x008e, 0x0095, 0x00b8, 0x009a, 0x001b, 0x00d4, 0x004b, 0x0063,
    0x00bc, 0x0073, 0x00ab, 0x00a7, 0x003b, 0x006e, 0x00e3, 0x00e6,
    0x00f6, 0x003f, 0x00db, 0x00fc, 0x007d, 0x00f3, 0x005f, 0x00d7,
    0x00ef, 0x00df, 0x007f, 0x00f7, 0x00bf, 0x00fd, 0x00fb, 0x00fe,
    0x00ff
]
# fmt: on

zone_based_ids = [
    StatusUpdate.RequestID.ZONE_INPUT_UNSEALED,
    StatusUpdate.RequestID.ZONE_RADIO_UNSEALED,
    StatusUpdate.RequestID.ZONE_CBUS_UNSEALED,
    StatusUpdate.RequestID.ZONE_IN_DELAY,
    StatusUpdate.RequestID.ZONE_IN_DOUBLE_TRIGGER,
    StatusUpdate.RequestID.ZONE_IN_ALARM,
    StatusUpdate.RequestID.ZONE_EXCLUDED,
    StatusUpdate.RequestID.ZONE_AUTO_EXCLUDED,
    StatusUpdate.RequestID.ZONE_SUPERVISION_FAIL_PENDING,
    StatusUpdate.RequestID.ZONE_SUPERVISION_FAIL,
    StatusUpdate.RequestID.ZONE_DOORS_OPEN,
    StatusUpdate.RequestID.ZONE_DETECTOR_LOW_BATTERY,
    StatusUpdate.RequestID.ZONE_DETECTOR_TAMPER,
]


def Generate_Output_From_Ness_Status_Update_Valid_Data() -> list[tuple[str, str]]:
    data: list[tuple[str, str]] = []

    for req in zone_based_ids:
        for zones_val in zones_list:
            data.append(
                (
                    f"{req.value:02d}{zones_val:04x}",
                    f"{req.name} with zones {zones_val:04x}",
                )
            )

    req = StatusUpdate.RequestID.MISCELLANEOUS_ALARMS
    for misc_val in misc_alarm_list:
        data.append(
            (f"{req.value:02d}{misc_val:04x}", f"{req.name} with alarms {misc_val:04x}")
        )

    req = StatusUpdate.RequestID.ARMING
    for arming_val in arming_list:
        data.append(
            (
                f"{req.value:02d}{arming_val:04x}",
                f"{req.name} with arming status {arming_val:04x}",
            )
        )

    req = StatusUpdate.RequestID.OUTPUTS
    for output_val in output_list:
        data.append(
            (
                f"{req.value:02d}{output_val:04x}",
                f"{req.name} with output state {output_val:04x}",
            )
        )

    req = StatusUpdate.RequestID.VIEW_STATE
    for viewstate in ViewStateUpdate.State:
        print(f"viewstate.value={req.value:02d}{viewstate.value:04x}")
        data.append(
            (
                f"{req.value:02d}{viewstate.value:04x}",
                f"{req.name} with view state {viewstate.value:04x}",
            )
        )

    req = StatusUpdate.RequestID.PANEL_VERSION
    for ver in range(0, 0xFF + 1):
        for model in PanelVersionUpdate.Model:
            data.append(
                (
                    f"{req.value:02d}{model.value:02x}{ver:02x}",
                    f"{req.name} with model {model.name} version {ver:02x}",
                )
            )

    req = StatusUpdate.RequestID.AUXILIARY_OUTPUTS
    for auxoutput_val in auxoutput_list:
        data.append(
            (
                f"{req.value:02d}{auxoutput_val:04x}",
                f"{req.name} with aux output state {auxoutput_val:04x}",
            )
        )

    return data


# Responses to a User-Interface Status Request Packet
def Gemerate_Output_From_Ness_Status_Update_Valid_Packets() -> list[tuple[str, str]]:
    Output_From_Ness_Status_Update_Valid_Data = (
        Generate_Output_From_Ness_Status_Update_Valid_Data()
    )

    Output_From_Ness_Status_Update_Valid_Packets = []
    for address in range(0x0, 0xF + 1):
        for data, name in Output_From_Ness_Status_Update_Valid_Data:
            packet = f"82{address:02x}0360{data}"
            total = 0
            for pos in range(0, len(packet), 2):
                total += int(packet[pos : pos + 2], 16)
            checksum = (256 - total) % 256
            packet = f"{packet}{checksum:02x}"

            Output_From_Ness_Status_Update_Valid_Packets.append(
                (packet, f"{name} for address {address}")
            )

    return Output_From_Ness_Status_Update_Valid_Packets


def or_list(vals: list[int]) -> int:
    output = 0
    for val in vals:
        output |= val
    return output


def select_bitfield(bitfield: Iterable[enum.Enum]) -> list[int]:
    all_elems = [elem.value for elem in bitfield]

    # Begin with the 'no bits' case
    val_list = [0]
    for k in range(1, len(all_elems)):
        # Take a random subset of 16 values with k zones active
        for _ in range(0, len(all_elems)):
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
    print(
        "\nzones_list:"
        + str([f"0x{val:04x}" for val in select_bitfield(ZoneUpdate.Zone)])
    )
    print(
        "\nmisc_alarm_list:"
        + str(
            [
                f"0x{val:04x}"
                for val in select_bitfield(MiscellaneousAlarmsUpdate.AlarmType)
            ]
        )
    )
    print(
        "\narming_list:"
        + str([f"0x{val:04x}" for val in select_bitfield(ArmingUpdate.ArmingStatus)])
    )
    print(
        "\noutput_list:"
        + str([f"0x{val:04x}" for val in select_bitfield(OutputsUpdate.OutputType)])
    )
    print(
        "\nauxoutput_list:"
        + str(
            [
                f"0x{val:04x}"
                for val in select_bitfield(AuxiliaryOutputsUpdate.OutputType)
            ]
        )
    )
