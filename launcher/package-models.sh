#!/bin/sh
# Packs FlipAssist's own four models for a GitHub release tagged models-v1 (9 Nov 2026, the owner: all four
# downloadable): each model file split into parts under GitHub's 2 GB limit, each model's Modelfile, the SHA-256 of
# every file, and the Gemma notice and terms that must go with them (models/README.md). About 10 GB:
#   launcher/package-models.sh ~/Desktop/FlipAssist-models-release
set -eu
out=${1:?"say where to put the release files, e.g. launcher/package-models.sh ~/Desktop/FlipAssist-models-release"}
here=$(cd "$(dirname "$0")" && pwd)
terms="$here/../models/GEMMA-TERMS.txt"
policy="$here/../models/GEMMA-PROHIBITED-USE-POLICY.txt"
models=${FLIP_MODELS:-"flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"}
# the Gemma Terms of Use go with the files, or they can't be shared (models/README.md)
[ -s "$terms" ] || { echo "Save the Gemma Terms of Use (ai.google.dev/gemma/terms) as models/GEMMA-TERMS.txt first" >&2; exit 1; }
[ -s "$policy" ] || { echo "Save the Gemma Prohibited Use Policy as models/GEMMA-PROHIBITED-USE-POLICY.txt first" >&2; exit 1; }
mkdir -p "$out"
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
cd "$out"
for model in $models; do
  blob=$(ollama show --modelfile "$model" | sed -n 's/^FROM //p' | head -1)
  echo "- $model ($(du -h "$blob" | cut -f1 | tr -d ' '))"
  split -b 1900m -a 1 "$blob" "$model.gguf.part-" # 1,900 MiB: under the 2 GiB a release file may be
  ollama show --modelfile "$model" | sed "s#^FROM .*#FROM ./$model.gguf#" > "$model.Modelfile"
done
cp "$here/../models/NOTICE" "$here/../models/README.md" "$terms" "$policy" .
shasum -a 256 -- *.gguf.part-* *.Modelfile > SHA256SUMS
echo "Release files in $out: upload them all to a GitHub release tagged models-v1"
