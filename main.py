import sys
from typing import Self, cast
from enum import Enum
from zenkit import DaedalusDataType, DaedalusInstruction, DaedalusOpcode, DaedalusScript, CutsceneLibrary, DaedalusSymbol
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
        for off in range(1, self.sym.size+1):
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
    c_svm: DaedClass
    svm_member_lookup: dict[int, str]

    v_other: int
    v_self: int
    f_aioutput: int
    f_aioutputsvm: int
    f_aioutputsvmo: int
    f_say: int
    f_say_overlay: int
    f_say_gold: int

    def __init__(self, script: DaedalusScript):
        self.c_info = DaedClass.search(script, "C_INFO")
        self.c_info_npc = self.c_info.members["NPC"].sym.index
        self.c_info_info = self.c_info.members["INFORMATION"].sym.index

        self.c_npc = DaedClass.search(script, "C_NPC")
        self.c_npc_name = self.c_npc.members["NAME"].sym.index
        self.c_npc_voice = self.c_npc.members["VOICE"].sym.index

        self.c_svm = DaedClass.search(script, "C_SVM")
        self.svm_member_lookup = {}
        for (mem_name, member) in self.c_svm.members.items():
            self.svm_member_lookup[member.sym.index] = mem_name

        self.v_other = cast(DaedalusSymbol, script.get_symbol_by_name("OTHER")).index
        self.v_self = cast(DaedalusSymbol, script.get_symbol_by_name("SELF")).index
        self.f_aioutput = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUT")).index
        self.f_aioutputsvm = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUTSVM")).index
        self.f_aioutputsvmo = cast(DaedalusSymbol, script.get_symbol_by_name("AI_OUTPUTSVM_OVERLAY")).index

        f_say = script.get_symbol_by_name("B_SAY")
        self.f_say = f_say.address if f_say is not None else -1
        f_say_overlay = script.get_symbol_by_name("B_SAY_OVERLAY")
        self.f_say_overlay = f_say_overlay.address if f_say_overlay is not None else -1
        f_say_gold = script.get_symbol_by_name("B_SAY_GOLD")
        self.f_say_gold = f_say_gold.address if f_say_gold is not None else -1
        print(f"f_say: {self.f_say}, f_say_overlay: {self.f_say_overlay}, f_say_gold: {self.f_say_gold}")

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
    def unknown() -> "NpcInfo":
        return NpcInfo(-1, "Unknown", 0)

    @staticmethod
    def hero() -> "NpcInfo":
        return NpcInfo(0, "Hero", 15)

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

def extract_speaker(prev_insts: list[DaedalusInstruction], script_const: ScriptConstants, current_addr: int) ->Speaker:
    if len(prev_insts) < 3 or \
        prev_insts[-3].op != DaedalusOpcode.PUSHVI or \
        prev_insts[-2].op != DaedalusOpcode.PUSHVI:
        print(f"! Unable to extract speaker due to unknown param op @ {current_addr}")
    else:
        speaker_idx = prev_insts[-3].symbol
        if speaker_idx == script_const.v_self:
            return Speaker.NPC
        elif speaker_idx == script_const.v_other:
            return Speaker.HERO
        else:
            print(f"! Neither self nor other speak @ {current_addr}")
    return Speaker.NONE

script_lines_cache : dict[int, list[ScriptLineInfo]] = {}
def extract_script_lines(script: DaedalusScript, fun_addr: int, script_const: ScriptConstants) -> list[ScriptLineInfo]:
    cached = script_lines_cache.get(fun_addr)
    if cached is not None:
        return cached
    current_addr = fun_addr
    prev_insts : list[DaedalusInstruction] = []
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
            elif inst.address == script_const.f_say_gold:
                # hardcode due to int parameter op
                speaker = extract_speaker(prev_insts,  script_const, current_addr)
                if len(prev_insts) < 1 or \
                    prev_insts[-1].op != DaedalusOpcode.PUSHI:
                    print(f"! Unparseable gold amount op @ {current_addr}")
                else:
                    gold_amount = prev_insts[-1].immediate
                    result.append(ScriptLineInfo(speaker, LineType.SVM, f"$GOLD_{gold_amount}"))
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
            speaker = extract_speaker(prev_insts,  script_const, current_addr)

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

class SvmInfo:
    voicelines: dict[str, str]
    def __init__(self, script: DaedalusScript, voice_idx: int, script_const: ScriptConstants):
        svm_inst = cast(DaedalusSymbol, script.get_symbol_by_name(f"SVM_{voice_idx}"))
        current_addr = svm_inst.address
        prev_insts : list[DaedalusInstruction] = []
        inst = script.get_instruction(current_addr)
        result = []
        self.voicelines = {}
        while True:
            if inst.op == DaedalusOpcode.RSR:
                break
            if inst.op == DaedalusOpcode.MOVS and len(prev_insts) >= 2:
                voiceline_sym = prev_insts[-2].symbol
                voiceline = cast(DaedalusSymbol, script.get_symbol_by_index(voiceline_sym)).get_string()

                member = script_const.svm_member_lookup.get(prev_insts[-1].symbol)
                if member is not None:
                    self.voicelines[member] = voiceline
                else:
                    print(f"SVM Member IDX {member} not resolvable!")
            current_addr += inst.size
            prev_insts.append(inst)
            inst = script.get_instruction(current_addr)

def parse_dia(
        script: DaedalusScript,
        csl: CutsceneLibrary,
        symbol: DaedalusSymbol,
        script_const: ScriptConstants,
        svm_usages : dict[tuple[int, str], list[NpcInfo|None]],
        line_owner : dict[str, NpcInfo|None],
        output):
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
        return

    npc = None
    if npc_idx != -1:
        npc = NpcInfo.parse_npc(script, npc_idx, script_const)
    else:
        npc = NpcInfo.unknown()

    info = script.symbols[info_idx]

    lines = extract_script_lines(script, info.address, script_const)
    for line in lines:
        line_name = line.line_name
        line_npc = NpcInfo.hero() if line.speaker == Speaker.HERO else npc
        voice_id = line_npc.voice if line_npc is not None else 0
        npc_name = line_npc.name if line_npc is not None else "-"
        npc_idx =  line_npc.idx if line_npc is not None else 0
        if line.type == LineType.SVM or line.type == LineType.SVM_OVERLAY:
            # cut off dollar sign
            entry_key = (voice_id, line_name[1:])
            svm_entry = svm_usages.setdefault(entry_key, [])
            if line_npc not in svm_entry:
                svm_entry.append(line_npc)
            continue #SVMs are handled separately at the end

        prev_owner = line_owner.setdefault(line_name, None)
        if prev_owner is not None:
            if prev_owner != line_npc:
                print("{line_name} is used by both {prev_owner} and {npc}!")
            else:
                continue #Same line is used by the same NPC twice, no need to list it again
        prev_owner = line_npc
        line_details = csl.get(line_name)

        if line_details is not None:
            output.writerow([line_name, npc_name, npc_idx, voice_id, line_details.message.text, line_details.message.name])

    print(f"{dia_name}: {npc}: {len(lines)}")

def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: main.py <mod/SCRIPTS/CONTENT/CUTSCENE/OU.BIN> <mod/SCRIPTS/_COMPILED/GOTHIC.DAT> <output.csv>", file=sys.stderr)
        return -1

    csl = CutsceneLibrary.load(sys.argv[1])
    script = DaedalusScript.load(sys.argv[2])

    script_const = ScriptConstants(script)

    with open(sys.argv[3], "w", newline="") as csvfile:
        output = csv.writer(csvfile, delimiter="\t", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        output.writerow(["LineID", "NPCName", "NPCID", "VoiceID", "Text", "Filename"])
        svm_usages : dict[tuple[int, str], list[NpcInfo|None]] = {}
        line_owner : dict[str, NpcInfo|None] = {}
        # iterate all DIAs:
        for symbol in []:#script.symbols:
            if symbol.type != DaedalusDataType.INSTANCE:
                continue
            if symbol.parent != script_const.c_info.idx:
                continue
            parse_dia(script, csl, symbol, script_const, svm_usages, line_owner, output)

        del line_owner # no longer needed
        svm_count = cast(DaedalusSymbol, script.get_symbol_by_name("SVM_MODULES")).get_int()
        print(f"SVM count: {svm_count}")

        for voice_idx in range(1, svm_count):
            svm = SvmInfo(script, voice_idx, script_const)
            print(f"SVM {voice_idx} meta loaded")
            for (member, voiceline) in svm.voicelines.items():
                line_details = csl.get(voiceline)

                svm_usage = svm_usages.get((voice_idx, member))
                if voice_idx == 15:
                    npc_name = "Hero"
                    npc_idx = 0
                elif svm_usage is None:
                    npc_name = f"Unknown{voice_idx}"
                    npc_idx = voice_idx
                else:
                    if len(svm_usage) == 1:
                        if svm_usage[0] is None:
                            npc_name = "Unknown"
                            npc_idx = -1
                        else:
                            npc_name = svm_usage[0].name
                            npc_idx = svm_usage[0].idx
                    else:
                        names = []
                        for npc in svm_usage:
                            if npc is None:
                                names.append("Unknown")
                            else:
                                names.append(npc.name)
                        npc_name = ",".join(names)
                        npc_idx = voice_idx

                if line_details is not None:
                    #print(f"{voiceline}: {line_details.message.text}")
                    output.writerow([voiceline, npc_name, npc_idx, voice_idx, line_details.message.text, line_details.message.name])
                else:
                    print(f"SVM {voiceline} not found in CSL")


    return 0

if __name__ == "__main__":
    exit(main())
