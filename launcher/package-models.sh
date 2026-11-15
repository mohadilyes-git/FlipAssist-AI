#!/bin/sh
# Packs FlipAssist's own four models for a GitHub release tagged models-v1 (9 Nov 2026, the owner: all four
# downloadable): each model file split into parts under GitHub's 2 GB limit, each model's Modelfile, the SHA-256 of
# every part and Modelfile, and the Gemma notice and terms that must go with them (models/README.md). Each model in
# Ollama must be the version that was tested, and its Modelfile the one get-models.sh checks for (MODELS.md). About
# 10 GB, into an empty folder with about 11 GB free:
#   launcher/package-models.sh ~/Desktop/FlipAssist-models-release
set -eu
out=${1:?"say where to put the release files, e.g. launcher/package-models.sh ~/Desktop/FlipAssist-models-release"}
here=$(cd "$(dirname "$0")" && pwd)
terms="$here/../models/GEMMA-TERMS.txt"
policy="$here/../models/GEMMA-PROHIBITED-USE-POLICY.txt"
models="flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"
# all four every time: the release's SHA256SUMS lists what get-models.sh fetches, and it stops at a model it lacks
[ "${FLIP_MODELS:-$models}" = "$models" ] ||
  { echo "FLIP_MODELS can't pick models to pack: the release needs all four" >&2; exit 1; }
# the Gemma Terms of Use go with the files, or they can't be shared (models/README.md)
[ -s "$terms" ] || { echo "Save the Gemma Terms of Use (ai.google.dev/gemma/terms) as models/GEMMA-TERMS.txt first" >&2; exit 1; }
[ -s "$policy" ] || { echo "Save the Gemma Prohibited Use Policy as models/GEMMA-PROHIBITED-USE-POLICY.txt first" >&2; exit 1; }
mkdir -p "$out"
# an empty folder, so SHA256SUMS lists only what this run makes (Finder's .DS_Store aside)
[ -z "$(ls -A "$out" | grep -vx '\.DS_Store')" ] || { echo "$out isn't empty: give it an empty folder" >&2; exit 1; }
# the tested versions (MODELS.md, How to check a model file), as get-models.sh checks them: each model file, then its
# Modelfile (ollama show --modelfile, with FROM ./<model>.gguf)
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
    flip-wording-4b) echo 49bbde2bcc475d2084f7424fae3b0eeec11a0b22f86b8cdf513e29bdc09aed4d ;;
    flip-kinds-1) echo 0eff6f2dc41da8ea134a65569b692ee8c57123b0ea9ce6f20ef473e996eeb8a1 ;;
    flip-style-1b) echo 9f3426680520a0baefba7e3ac11d69fe2d525e694aac4357ce7e49d77e6fbff2 ;;
    *) echo unknown ;;
  esac
}
# a model's file in Ollama, from the FROM line of its Modelfile
blob_of() {
  mf=$(ollama show --modelfile "$1") || { echo "$1 isn't in Ollama (ollama list), or Ollama isn't running" >&2; exit 1; }
  blob=$(printf '%s\n' "$mf" | sed -n 's/^FROM //p' | head -1)
  [ -f "$blob" ] || { echo "$1: Ollama's file for it isn't on this Mac ($blob)" >&2; exit 1; }
}
# each model checked against the tested version, and room for them all, before anything is written
need_kb=0
for model in $models; do
  blob_of "$model"
  echo "- checking $model"
  got=$(shasum -a 256 "$blob" | cut -d' ' -f1)
  [ "$got" = "$(tested "$model")" ] ||
    { echo "$model in Ollama isn't the version that was tested (SHA-256 $got): see MODELS.md" >&2; exit 1; }
  got=$(ollama show --modelfile "$model" | sed "s#^FROM .*#FROM ./$model.gguf#" | shasum -a 256 | cut -d' ' -f1)
  [ "$got" = "$(tested_modelfile "$model")" ] ||
    { echo "$model's Modelfile from Ollama isn't the one that was tested (SHA-256 $got): get-models.sh would refuse it" >&2; exit 1; }
  need_kb=$((need_kb + $(du -k "$blob" | cut -f1)))
done
free_kb=$(df -k "$out" | awk 'NR==2 {print $4}')
if [ "$free_kb" -lt $((need_kb + 1048576)) ]; then
  echo "Not enough room in $out: it needs about $(((need_kb + 1048576 + 1048575) / 1048576)) GB and has $((free_kb / 1048576)) GB" >&2
  exit 1
fi
cd "$out"
for model in $models; do
  blob_of "$model"
  echo "- $model ($(du -h "$blob" | cut -f1 | tr -d ' '))"
  split -b 1900m -a 1 "$blob" "$model.gguf.part-" # 1,900 MiB: under the 2 GiB a release file may be
  ollama show --modelfile "$model" | sed "s#^FROM .*#FROM ./$model.gguf#" > "$model.Modelfile"
done
cp "$here/../models/NOTICE" "$here/../models/README.md" "$terms" "$policy" .
shasum -a 256 -- *.gguf.part-* *.Modelfile > SHA256SUMS
echo "Release files in $out: upload them all to a GitHub release tagged models-v1"
