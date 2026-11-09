#!/bin/sh
# Copies FlipAssist's own models (flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b) out of Ollama on this
# Mac into a folder, each as its GGUF file beside the Modelfile that names it, to set them up on Windows
# (launcher\windows-setup.ps1 -Models <that folder>). About 10 GB in all, so give it a USB drive or another disk, not
# a nearly full Mac (9 Nov 2026):
#   launcher/export-models.sh /Volumes/USB/FlipAssist-models
set -eu
out=${1:?"say where to put them, e.g. launcher/export-models.sh /Volumes/USB/FlipAssist-models"}
models="flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"
mkdir -p "$out"
# Windows can't read a Mac-formatted disk (APFS, Mac OS Extended): the USB drive has to be ExFAT
fs=$(diskutil info "$(df "$out" | awk 'NR==2 {print $1}')" 2>/dev/null | awk -F': *' '/Type \(Bundle\)/ {print $2}')
case "$fs" in
  exfat | msdos) ;;
  *) echo "Note: $out is on a ${fs:-unknown} disk, which Windows can't read: use a USB drive formatted ExFAT (Disk Utility > Erase > ExFAT)" >&2 ;;
esac

# each model's file in Ollama, and room for them all (plus 1 GB to spare) before anything is copied
need_kb=0
for model in $models; do
  blob=$(ollama show --modelfile "$model" | sed -n 's/^FROM //p' | head -1)
  [ -f "$blob" ] || { echo "$model: Ollama's file for it isn't on this Mac ($blob)" >&2; exit 1; }
  need_kb=$((need_kb + $(du -k "$blob" | cut -f1)))
done
free_kb=$(df -k "$out" | awk 'NR==2 {print $4}')
if [ "$free_kb" -lt $((need_kb + 1048576)) ]; then
  echo "Not enough room in $out: it needs about $((need_kb / 1048576 + 1)) GB and has $((free_kb / 1048576)) GB" >&2
  exit 1
fi

for model in $models; do
  mkdir -p "$out/$model"
  ollama show --modelfile "$model" > "$out/$model/Modelfile.mac"
  blob=$(sed -n 's/^FROM //p' "$out/$model/Modelfile.mac" | head -1)
  echo "- $model ($(du -h "$blob" | cut -f1 | tr -d ' '))"
  cp "$blob" "$out/$model/$model.gguf"
  # the same Modelfile, from the copied file beside it (Ollama reads a FROM path from the Modelfile's own folder)
  sed "s#^FROM .*#FROM ./$model.gguf#" "$out/$model/Modelfile.mac" > "$out/$model/Modelfile"
  rm "$out/$model/Modelfile.mac"
done
echo "Exported to $out: copy that folder to the Windows PC"
