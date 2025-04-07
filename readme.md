# Gothic 2 VoiceOver Script Extractor

A set of tools for creating a script CSV containing all voicelines in a Gothic 2 mod, based on [ZenKit](https://zk.gothickit.dev/).

The usual pipeline:

```bash
# env setup
python -m venv venv
. venv/bin/activate
pip install zenkit
# do this once to create a script for the original voicelines:
python main.py '/path/to/Gothic II/_work/Data/Scripts/Content/Cutscene/OU.BIN' '/path/to/Gothic II/_work/Data/Scripts/_compiled/GOTHIC.DAT' g2dndr.csv
# collect the voicelines from the mod (use GothicVDFS to extract the vdf first):
python main.py /path/to/mod/SCRIPTS/CONTENT/CUTSCENE/OU.BIN /path/to/mod/SCRIPTS/_COMPILED/GOTHIC.DAT mod.csv
# remove all voicelines present in the original from the Script
python dedup.py mod.csv g2dndr.csv mod_dedup.csv
# get a cast list
python ex_cast mod_dedup.csv
```
