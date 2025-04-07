import csv
import sys

class LineProps:
    speaker: str
    text: str
    def __init__(self, speaker:str,text:str):
        self.speaker = speaker
        self.text = text

def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: dedup.py <mod.csv> <g2dndr.csv> <output.csv>", file=sys.stderr)
        print("Copies voicelines from <mod.csv> to <output.csv>, skipping those already in <g2dndr.csv> to prevent regenerating voicelines present in the base game", file=sys.stderr)
        return -1

    orig_lines : dict[str, LineProps] = {}
    with open(sys.argv[2], "r") as origfile:
        orig = csv.reader(origfile, delimiter="\t", quotechar='"')
        orig.__next__() #skip CSV headers
        for line in orig:
            orig_lines[line[5].upper()] = LineProps(line[1], line[4])


    with open(sys.argv[1], "r") as modfile:
        mod = csv.reader(modfile, delimiter="\t", quotechar='"')
        with open(sys.argv[3], "w", newline="") as csvfile:
            output = csv.writer(csvfile, delimiter="\t", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            output.writerow(mod.__next__()) #copy CSV headers
            for line in mod:
                orig_line = orig_lines.get(line[5].upper())
                if orig_line is not None and orig_line.speaker == line[1] and orig_line.text == line[4]:
                    print(".", end="")
                    continue #
                output.writerow(line)
                print(":", end="")
            csvfile.flush()

    return 0

if __name__ == "__main__":
    exit(main())
