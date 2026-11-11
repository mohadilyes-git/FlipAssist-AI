#!/bin/sh
# Downloads FlipAssist's own four models from the GitHub release models-v1, checks every part and each whole file
# against the SHA-256 fingerprint of the version that was tested (MODELS.md), and adds them to Ollama (9 Nov 2026).
# About 2.5 GB each; each model's parts are deleted once it's in Ollama.
#   launcher/get-models.sh                       (the repo this folder was cloned from)
#   launcher/get-models.sh owner/repo models-v1
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=${1:-$(git -C "$here" remote get-url origin | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')}
tag=${2:-models-v1}
base=${FLIP_MODELS_URL:-"https://github.com/$repo/releases/download/$tag"}
models=${FLIP_MODELS:-"flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"}
command -v ollama >/dev/null || { echo "Ollama isn't installed: get it from ollama.com" >&2; exit 1; }
# the tested versions (MODELS.md, How to check a model file)
tested() {
  case $1 in
    flip-reader-5) echo b946131ba11fc159fdc1cf683dab0d3b9c4a64cb80dd9726b1b4208b8632bae1 ;;
    flip-wording-4b) echo f8ad98ddf4849746e3520afb9d1d38689fc3437dc66fbd201ef536f2b18d35e1 ;;
    flip-kinds-1) echo 29d5df4e97c69c85892feed8c8a7f9a52f3d1f1c05fe7b07f6102a9d2dee45d0 ;;
    flip-style-1b) echo 2e64f58682c449660927e25afaa4d7c029c298a19b9527bd2c22c305e316d694 ;;
    *) echo unknown ;;
  esac
}
work=$(mktemp -d "${TMPDIR:-/tmp}/flipassist-models.XXXXXX")
trap 'rm -rf "$work"' EXIT
cd "$work"
curl -fsSL "$base/SHA256SUMS" -o SHA256SUMS
for model in $models; do
  parts=$(awk '{print $2}' SHA256SUMS | grep "^$model\.gguf\.part-" | sort)
  [ -n "$parts" ] || { echo "$model isn't on the release at $base" >&2; exit 1; }
  for name in $parts "$model.Modelfile"; do
    echo "- downloading $name"
    curl -fL --progress-bar "$base/$name" -o "$name"
  done
  grep -E "  ($model\.gguf\.part-|$model\.Modelfile)" SHA256SUMS | shasum -a 256 -c --quiet
  # shellcheck disable=SC2086 # the parts, in order
  cat $parts > "$model.gguf"
  rm -f $parts
  got=$(shasum -a 256 "$model.gguf" | cut -d' ' -f1)
  [ "$got" = "$(tested "$model")" ] || { echo "$model isn't the version that was tested (SHA-256 $got)" >&2; exit 1; }
  ollama create "$model" -f "$model.Modelfile"
  rm -f "$model.gguf"
done
echo "FlipAssist's models are in Ollama: $models"
