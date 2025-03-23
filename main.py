import sys
from typing import Self, cast
from enum import Enum
from zenkit import DaedalusDataType, DaedalusOpcode, DaedalusScript, CutsceneLibrary, DaedalusSymbol
import csv

class DaedSym:
    """Helper for parsing Daedalus symbols"""
    idx: int
    sym: DaedalusSymbol

    def __init__(self, script: DaedalusScript, idx: int):
        self.idx = idx
        self.sym = script.symbols[idx]

class DaedClass(DaedSym):
    """Helper for parsing Daedalus Class symbols"""
    members: dict[str, DaedSym]

    def __init__(self, script: DaedalusScript, idx: int):
        super().__init__(script, idx)
        self.members = {}
        for off in range(1, self.sym.size):
            member = DaedSym(script, idx + off)
            mem_name = member.sym.name.split('.')[1]
            self.members[mem_name] = member

    @staticmethod
    def search(script: DaedalusScript, name: str) -> "DaedClass":
        """Searches for a class symbol by name and parses it's members"""
        symbol = script.get_symbol_by_name(name)
        if symbol is None:
            raise Exception(f"{name} Class not found!")
        if symbol.type != DaedalusDataType.CLASS:
            raise Exception(f"{name} is not a Class!")
        return DaedClass(script, symbol.index)

class ScriptConstants:
    """Container for a few named constants we need to look up once"""
    c_info: DaedClass
    c_info_npc: int
    c_info_info: int
    c_npc: DaedClass
    c_npc_name:int
    c_npc_voice: int

    v_other: int
    v_self: int
    f_aioutput: int
    f_aioutputsvm: int
    f_aioutputsvmo: int

    def __init__(self, script: DaedalusScript):
        self.c_info = DaedClass.search(script, "C_INFO")
        self.c_info_npc = self.c_info.members["NPC"].sym.index
        self.c_info_info = self.c_info.members["INFORMATION"].sym.index

        self.c_npc = DaedClass.search(script, "C_NPC")
        self.c_npc_name = self.c_npc.members["NAME"].sym.index
        self.c_npc_voice = self.c_npc.members["VOICE"].sym.index

        self.v_other = cast(DaedalusSymbol, script.get_symbol_by_name("OTHER")).index
        self.v_self = cast(DaedalusSymbol, script.get_symbol_by_name("SELF")).index
        self.f_aioutput = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUT")).index
        self.f_aioutputsvm = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUTSVM")).index
        self.f_aioutputsvmo = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUTSVM_OVERLAY")).index

npc_cache = {}
class NpcInfo:
    """Stores relevant properties about an NPC defined in the script"""
    idx: int
    name: str
    voice: int
    def __init__(self, idx:int, name: str, voice: int):
        self.idx = idx
        self.name = name
        self.voice = voice
    def __str__(self) -> str:
        return f"{self.name}({self.idx})/{self.voice}"

    @staticmethod
    def parse_npc(script: DaedalusScript, npc_idx: int, script_const: ScriptConstants) -> "NpcInfo|None":
        if npc_idx in npc_cache:
            return npc_cache[npc_idx]
        npc = script.symbols[npc_idx]
        npc_name_idx = -1
        npc_voice = -1
        all_found = False
        #print(f"\n{npc.address}")
        current_addr = npc.address
        inst1 = script.get_instruction(current_addr)
        current_addr += inst1.size
        inst2 = script.get_instruction(current_addr)
        current_addr += inst2.size
        inst3 = script.get_instruction(current_addr)
        while True:
            if inst1.op == DaedalusOpcode.RSR or \
                inst2.op == DaedalusOpcode.RSR or \
                inst3.op == DaedalusOpcode.RSR:
                print(f"! NPC {npc_idx} doesn't contain all expected fields!")
                break

            if inst1.op == DaedalusOpcode.PUSHV and \
                inst2.op == DaedalusOpcode.PUSHV and \
                inst2.symbol == script_const.c_npc_name and \
                inst3.op == DaedalusOpcode.MOVS:
                # NPC Name idx is in inst1 symbol
                npc_name_idx = inst1.symbol
            if inst1.op == DaedalusOpcode.PUSHI and \
                inst2.op == DaedalusOpcode.PUSHV and \
                inst2.symbol == script_const.c_npc_voice and \
                inst3.op == DaedalusOpcode.MOVI:
                # NPC Voice ID is in inst1 immediate
                npc_voice = inst1.immediate

            if npc_name_idx != -1 and npc_voice != -1:
                all_found = True
                break

            inst1 = inst2
            inst2 = inst3
            current_addr += inst2.size
            inst3 = script.get_instruction(current_addr)

        if not all_found:
            npc_cache[npc_idx] = None
            return None

        npc_name = script.symbols[npc_name_idx].get_string()
        npc = NpcInfo(npc_idx, npc_name, npc_voice)

        npc_cache[npc_idx] = npc
        return npc

class Line(Enum):
    NONE = 0
    NORMAL = 1
    SVM = 2
    SVM_OVERLAY = 3

class Speaker(Enum):
    NONE = 0
    NPC = 1
    HERO = 2

def main() -> int:
    if len(sys.argv) < 2:
        print("please provide a textures.vdf file to read from", file=sys.stderr)
        return -1

    #vfs = Vfs()
    #vfs.mount_disk(sys.argv[1])

    # font_file = vfs.find("font_default.fnt")
    # if font_file is None:
    #     print("FONT_DEFAULT.FNT was not found in the VFS", file=sys.stderr)
    #     return -2

    csl = CutsceneLibrary.load("./SCRIPTS/CONTENT/CUTSCENE/OU.BIN")
    script = DaedalusScript.load("./SCRIPTS/_COMPILED/GOTHIC.DAT")

    script_const = ScriptConstants(script)

    # iterate all DIAs:
    for symbol in script.symbols:
        if symbol.type != DaedalusDataType.INSTANCE:
            continue
        if symbol.parent != script_const.c_info.idx:
            continue
        dia_name = symbol.name
        #print(f"{dia_name}")

        # extract npc index and info function (i.e., the script displaying the actual conversation):
        npc_idx = -1
        info_idx = -1
        #print(f"{symbol.address}")
        current_addr = symbol.address
        inst1 = script.get_instruction(current_addr)
        current_addr += inst1.size
        inst2 = script.get_instruction(current_addr)
        current_addr += inst2.size
        inst3 = script.get_instruction(current_addr)
        while True:
            if inst1.op == DaedalusOpcode.RSR or \
                inst2.op == DaedalusOpcode.RSR or \
                inst3.op == DaedalusOpcode.RSR:
                break

            if inst1.op == DaedalusOpcode.PUSHI and \
                inst2.op == DaedalusOpcode.PUSHV and \
                inst2.symbol == script_const.c_info_npc and \
                inst3.op == DaedalusOpcode.MOVI:
                # NPC ID is in inst1 immediate
                npc_idx = inst1.immediate
            if inst1.op == DaedalusOpcode.PUSHI and \
                inst2.op == DaedalusOpcode.PUSHV and \
                inst2.symbol == script_const.c_info_info and \
                inst3.op == DaedalusOpcode.MOVVF:
                # INFO Function ID is in inst1 immediate
                info_idx = inst1.immediate

            if npc_idx != -1 and info_idx != -1:
                break

            inst1 = inst2
            inst2 = inst3
            current_addr += inst2.size
            inst3 = script.get_instruction(current_addr)

        if info_idx == -1:
            print(f"! DIA {symbol.index} doesn't contain all expected fields!")
            continue

        npc = None
        if npc_idx != -1:
            npc = NpcInfo.parse_npc(script, npc_idx, script_const)

        info = script.symbols[info_idx]
        lines_count = 0

        current_addr = info.address
        inst1 = script.get_instruction(current_addr)
        current_addr += inst1.size
        inst2 = script.get_instruction(current_addr)
        current_addr += inst2.size
        inst3 = script.get_instruction(current_addr)
        current_addr += inst3.size
        inst4 = script.get_instruction(current_addr)
        while True:
            if inst1.op == DaedalusOpcode.RSR or \
                inst2.op == DaedalusOpcode.RSR or \
                inst3.op == DaedalusOpcode.RSR or \
                inst4.op == DaedalusOpcode.RSR:
                break

            line_type = Line.NONE
            if inst4.op == DaedalusOpcode.BE:
                if inst4.symbol == script_const.f_aioutput:
                    line_type = Line.NORMAL
                # elif inst4.symbol == script_const.f_aioutputsvm:
                #     line_type = Line.SVM
                # elif inst4.symbol == script_const.f_aioutputsvmo:
                #     line_type = Line.SVM_OVERLAY

            if line_type != Line.NONE:
                speaker = Speaker.NONE
                if inst1.op != DaedalusOpcode.PUSHVI or \
                    inst2.op != DaedalusOpcode.PUSHVI:
                    print(f"! Unable to extract speaker due to unknown param op @ {current_addr}")
                else:
                    speaker_idx = inst1.symbol
                    if speaker_idx == script_const.v_self:
                        speaker = Speaker.NPC
                    elif speaker_idx == script_const.v_other:
                        speaker = Speaker.HERO
                    else:
                        print(f"! Neither self nor other speak @ {current_addr}")

                if inst3.op != DaedalusOpcode.PUSHV:
                    print(f"! Unparseable line_name op @ {current_addr}")
                else:
                    line_name_idx = inst3.symbol
                    line_name = script.get_symbol_by_index(line_name_idx)
                    if line_name is not None:
                        line_name = line_name.get_string()
                        if line_type != Line.NORMAL and npc is not None:
                            line_name = f"SVM_{npc.voice}_{line_name}"
                            print(f"{speaker}: '{line_name}'")
                        #print(f"{speaker}: '{line_name}'")
                        lines_count += 1
                    else:
                        print(f"! Line targets unknown symbol {line_name_idx} @ {current_addr}")

            inst1 = inst2
            inst2 = inst3
            inst3 = inst4
            current_addr += inst3.size
            inst4 = script.get_instruction(current_addr)

        print(f"{dia_name}: {npc} - {lines_count} lines")


    return 0


if __name__ == "__main__":
    exit(main())
