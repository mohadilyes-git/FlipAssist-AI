#!/bin/sh
# Copies FlipAssist's own models (flip-reader-5, flip-wording-4b, flip-kinds-1, flip-style-1b) out of Ollama on this
# Mac into a folder, each as its GGUF file beside the Modelfile that names it, to set them up on Windows
# (launcher\windows-setup.ps1 -Models <that folder>). Each must be the version that was tested (MODELS.md). About
# 10 GB in all, so give it a USB drive or another disk, not a nearly full Mac (9 Nov 2026):
#   launcher/export-models.sh /Volumes/USB/FlipAssist-models
set -eu
out=${1:?"say where to put them, e.g. launcher/export-models.sh /Volumes/USB/FlipAssist-models"}
models="flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"
mkdir -p "$out"
# Windows can't read a Mac-formatted disk (APFS, Mac OS Extended): the USB drive has to be ExFAT
fs=$(diskutil info "$(df "$out" | awk 'NR==2 {print $1}')" 2>/dev/null | awk -F': *' '/Type \(Bundle\)/ {print $2}')
case "$fs" in
  exfat | msdos) ;;
  "") echo "Note: couldn't tell how the disk with $out is formatted: Windows needs a USB drive formatted ExFAT (Disk Utility > Erase > ExFAT)" >&2 ;;
  *) echo "Note: $out is on a disk formatted as $fs, which Windows can't read: use a USB drive formatted ExFAT (Disk Utility > Erase > ExFAT)" >&2 ;;
esac
# the tested versions (MODELS.md, How to check a model file), as get-models.sh checks them: each model file, then its
# Modelfile (ollama show --modelfile, with FROM ./<model>.gguf and its settings in A-Z order: modelfile_of, below)
tested() {
  case $1 in
    flip-reader-5) echo b946131ba11fc159fdc1cf683dab0d3b9c4a64cb80dd9726b1b4208b8632bae1 ;;
    flip-wording-4b) echo f8ad98ddf4849746e3520afb9d1d38689fc3437dc66fbd201ef536f2b18d35e1 ;;
    flip-kinds-1) echo 29d5df4e97c69c85892feed8c8a7f9a52f3d1f1c05fe7b07f6102a9d2dee45d0 ;;
    flip-style-1b) echo 2e64f58682c449660927e25afaa4d7c029c298a19b9527bd2c22c305e316d694 ;;
    *) echo unknown ;;
  esac
}
tested_modelfile() {
  case $1 in
    flip-reader-5) echo 8c0a25f122166b29ef661b053c475a87cbcfcb7d5acd9fc4c99165538e224245 ;;
    flip-wording-4b) echo 0fcfff7a38dc6ceae08936f6804a975a12e5caeb9cc40028d1b8afe19925fd23 ;;
    flip-kinds-1) echo f0e5e65efaad1055d255c0a7b4f68563fb4e5f77afaebd125a7e55181835fc99 ;;
    flip-style-1b) echo 16cf1cd4418305430888b9b5f4a6085e265cd78ccf9c9661f79c80291c3630dc ;;
    *) echo unknown ;;
  esac
}

# a model's Modelfile as the release has it and as it was tested: Ollama's own (ollama show --modelfile) with
# FROM ./<model>.gguf, and its PARAMETER lines, which sit together, in A-Z order. Ollama keeps each model's settings in
# an order of its own (16 Nov: three of the four printed theirs in another order, the same settings), so it's set here
modelfile_of() {
  mf_tmp=$(mktemp "${TMPDIR:-/tmp}/flipassist-modelfile.XXXXXX")
  ollama show --modelfile "$1" | sed "s#^FROM .*#FROM ./$1.gguf#" > "$mf_tmp"
  sed '/^PARAMETER /,$d' "$mf_tmp"
  grep '^PARAMETER ' "$mf_tmp" | LC_ALL=C sort
  sed '1,/^PARAMETER /d' "$mf_tmp" | sed '/^PARAMETER /d'
  rm -f "$mf_tmp"
}
# each model's file in Ollama, checked against the tested version, and room for them all (plus 1 GB to spare) before
# anything is copied; a file an earlier export left there is written over, so it needs no room twice
need_kb=0
for model in $models; do
  mf=$(ollama show --modelfile "$model") || { echo "$model isn't in Ollama (ollama list), or Ollama isn't running" >&2; exit 1; }
  blob=$(printf '%s\n' "$mf" | sed -n 's/^FROM //p' | head -1)
  [ -f "$blob" ] || { echo "$model: Ollama's file for it isn't on this Mac ($blob)" >&2; exit 1; }
  echo "- checking $model"
  got=$(shasum -a 256 "$blob" | cut -d' ' -f1)
  [ "$got" = "$(tested "$model")" ] ||
    { echo "$model in Ollama isn't the version that was tested (SHA-256 $got): see MODELS.md" >&2; exit 1; }
  got=$(modelfile_of "$model" | shasum -a 256 | cut -d' ' -f1)
  [ "$got" = "$(tested_modelfile "$model")" ] ||
    { echo "$model's Modelfile from Ollama isn't the one that was tested (SHA-256 $got)" >&2; exit 1; }
  have_kb=$(du -k "$out/$model/$model.gguf" 2>/dev/null | cut -f1)
  need_kb=$((need_kb + $(du -k "$blob" | cut -f1) - ${have_kb:-0}))
done
free_kb=$(df -k "$out" | awk 'NR==2 {print $4}')
if [ "$free_kb" -lt $((need_kb + 1048576)) ]; then
  echo "Not enough room in $out: it needs about $(((need_kb + 1048576 + 1048575) / 1048576)) GB and has $((free_kb / 1048576)) GB" >&2
  exit 1
fi

for model in $models; do
  mkdir -p "$out/$model"
  blob=$(ollama show --modelfile "$model" | sed -n 's/^FROM //p' | head -1)
  echo "- $model ($(du -h "$blob" | cut -f1 | tr -d ' '))"
  cp "$blob" "$out/$model/$model.gguf"
  # the tested Modelfile, naming the copied file beside it (Ollama reads a FROM path from the Modelfile's own folder)
  modelfile_of "$model" > "$out/$model/Modelfile"
done
echo "Exported to $out: copy that folder to the Windows PC"
