import csv
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: dedup.py <script.csv>", file=sys.stderr)
        print("Extracts a cast list from a script csv", file=sys.stderr)
        return -1

    speakers : dict[str, int] = {}
    with open(sys.argv[1], "r") as origfile:
        orig = csv.reader(origfile, delimiter="\t", quotechar='"')
        orig.__next__() #skip CSV headers
        for line in orig:
            speakers[line[1]] = speakers.get(line[1], 0) + 1

    speaker_list : list[tuple[str, int]] = list(speakers.items())
    speaker_list.sort(key=lambda sp: sp[1])
    print(speaker_list)

    return 0

if __name__ == "__main__":
    exit(main())
