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
    f_say: int
    f_say_overlay: int

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

        f_say = script.get_symbol_by_name("B_SAY")
        self.f_say = f_say.address if f_say is not None else -1
        f_say_overlay = script.get_symbol_by_name("B_SAY_OVERLAY")
        self.f_say_overlay = f_say_overlay.address if f_say_overlay is not None else -1
        print(f"f_say: {self.f_say}, f_say_overlay: {self.f_say_overlay}")

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

class LineType(Enum):
    NONE = 0
    NORMAL = 1
    SVM = 2
    SVM_OVERLAY = 3

class Speaker(Enum):
    NONE = 0
    NPC = 1
    HERO = 2

class ScriptLineInfo:
    speaker: Speaker
    type: LineType
    line_name: str

    def __init__(self,speaker: Speaker, type: LineType, line_name: str):
        self.speaker = speaker
        self.type = type
        self.line_name = line_name

    def __str__(self):
        return f"{self.speaker} - {self.type}: {self.line_name}"

script_lines_cache : dict[int, list[ScriptLineInfo]] = {}
def extract_script_lines(script: DaedalusScript, fun_addr: int, script_const: ScriptConstants) -> list[ScriptLineInfo]:
    cached = script_lines_cache.get(fun_addr)
    if cached is not None:
        return cached
    current_addr = fun_addr
    prev_insts = []
    inst = script.get_instruction(current_addr)
    result = []
    while True:
        if inst.op == DaedalusOpcode.RSR:
            break

        line_type = LineType.NONE
        if inst.op == DaedalusOpcode.BE:
            if inst.symbol == script_const.f_aioutput:
                line_type = LineType.NORMAL
            elif inst.symbol == script_const.f_aioutputsvm:
                line_type = LineType.SVM
            elif inst.symbol == script_const.f_aioutputsvmo:
                line_type = LineType.SVM_OVERLAY

        if inst.op == DaedalusOpcode.BL:
            if inst.address == script_const.f_say:
                line_type = LineType.SVM
            elif inst.address == script_const.f_say_overlay:
                line_type = LineType.SVM_OVERLAY
            else:
                # calls another daedalus function, extract info from there as well:
                # sub_sym = script.get_symbol_by_address(inst.address)
                # if sub_sym is not None:
                #     print(f"> {sub_sym.name}")
                # else:
                #     print(f"> (unnamed)")

                # we do not handle tracking parameters, so we might miss some lines:
                result.extend(extract_script_lines(script, inst.address, script_const))

        if line_type != LineType.NONE:
            speaker = Speaker.NONE
            if len(prev_insts) < 3 or \
                prev_insts[-3].op != DaedalusOpcode.PUSHVI or \
                prev_insts[-2].op != DaedalusOpcode.PUSHVI:
                print(f"! Unable to extract speaker due to unknown param op @ {current_addr}")
            else:
                speaker_idx = prev_insts[-3].symbol
                if speaker_idx == script_const.v_self:
                    speaker = Speaker.NPC
                elif speaker_idx == script_const.v_other:
                    speaker = Speaker.HERO
                else:
                    print(f"! Neither self nor other speak @ {current_addr}")

            if len(prev_insts) < 1 or \
                prev_insts[-1].op != DaedalusOpcode.PUSHV:
                print(f"! Unparseable line_name op @ {current_addr}")
            else:
                line_name_idx = prev_insts[-1].symbol
                line_name = script.get_symbol_by_index(line_name_idx)
                if line_name is not None and line_name.is_const:
                    line_name_str = line_name.get_string()
                    #print(f"{speaker}: '{line_name.name}'")
                    if line_name is None or line_name == "":
                        print(f"Line {line_name.name}({line_name_idx}) is empty")
                    else:
                        result.append(ScriptLineInfo(speaker, line_type, line_name_str))
                else:
                    print(f"! Line targets unknown/non-const symbol {line_name_idx} @ {current_addr}")

        current_addr += inst.size
        prev_insts.append(inst)
        inst = script.get_instruction(current_addr)
    script_lines_cache[fun_addr] = result
    return result

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
    with open("g2voe.csv", "w", newline="") as csvfile:
        output = csv.writer(csvfile, delimiter="\t", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        output.writerow(["LineID", "NPCName", "NPCID", "VoiceID", "Speaker", "Text", "Filename"])
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

            lines = extract_script_lines(script, info.address, script_const)
            for line in lines:
                line_name = line.line_name
                voice_id = 15 if line.speaker == Speaker.HERO else (npc.voice if npc is not None else 0)
                npc_name = npc.name if npc is not None else "-"
                npc_idx =  npc.idx if npc is not None else 0
                if line.type == LineType.SVM or line.type == LineType.SVM_OVERLAY:
                    # cut off dollar sign, add voice prefix for SVMs
                    line_name = f"SVM_{voice_id}_{line_name[1:]}"

                line_details = csl.get(line_name)
                if line_details is not None:
                    output.writerow([line_name, npc_name, npc_idx, voice_id, line.speaker.name, line_details.message.text, line_details.message.name])

            print(f"{dia_name}: {npc}: {len(lines)}")


    return 0

if __name__ == "__main__":
    exit(main())
