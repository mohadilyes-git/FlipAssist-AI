#!/bin/sh
# Puts FlipAssist's four models on the GitHub release models-v1 of the repo people clone FlipAssist from (9 Nov
# 2026, the owner: FlipAssist-AI), one model at a time, so the Mac never holds more than one model's parts (about
# 2.5 GB) beside Ollama's own copy. Each model in Ollama must be the version that was tested, and its Modelfile the
# one get-models.sh checks for (MODELS.md). Every part's SHA-256 is worked out first, straight from Ollama's copy, and
# each model's parts are checked against it before they go up. The repo needs its first commit before it can have a
# release. Needs GitHub's gh tool, logged in (brew install gh, then gh auth login):
#   launcher/upload-models.sh mohadilyes-git/FlipAssist-AI
set -eu
repo=${1:?"say which GitHub repo, e.g. launcher/upload-models.sh mohadilyes-git/FlipAssist-AI"}
tag=${2:-models-v1}
here=$(cd "$(dirname "$0")" && pwd)
models="flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"
# all four every time: the SHA256SUMS uploaded replaces the release's, and get-models.sh stops at a model it lacks
[ "${FLIP_MODELS:-$models}" = "$models" ] ||
  { echo "FLIP_MODELS can't pick models to upload: the release needs all four" >&2; exit 1; }
part=$((1900 * 1024 * 1024)) # a part's bytes: under the 2 GiB a release file may be (split -b 1900m, as package-models.sh)
extras="NOTICE README.md GEMMA-TERMS.txt GEMMA-PROHIBITED-USE-POLICY.txt"
command -v gh >/dev/null || { echo "GitHub's gh tool isn't installed: brew install gh, then gh auth login" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh isn't logged in: run gh auth login" >&2; exit 1; }
gh api "repos/$repo/commits?per_page=1" >/dev/null 2>&1 || { echo "$repo has no commits yet (or isn't reachable): push the code first" >&2; exit 1; }
for f in $extras; do [ -s "$here/../models/$f" ] || { echo "models/$f is missing" >&2; exit 1; }; done
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
work=$(mktemp -d "${TMPDIR:-/tmp}/flipassist-upload.XXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP # dash and zsh run the EXIT trap only through exit
cd "$work"
for f in $extras; do cp "$here/../models/$f" .; done

# each model checked against the tested version, then every part's SHA-256: the parts are read straight out of
# Ollama's copy, so none is written yet
: > SHA256SUMS
for model in $models; do
  blob_of "$model"
  echo "- checking $model"
  got=$(shasum -a 256 "$blob" | cut -d' ' -f1)
  [ "$got" = "$(tested "$model")" ] ||
    { echo "$model in Ollama isn't the version that was tested (SHA-256 $got): see MODELS.md" >&2; exit 1; }
  ollama show --modelfile "$model" | sed "s#^FROM .*#FROM ./$model.gguf#" > "$model.Modelfile"
  got=$(shasum -a 256 "$model.Modelfile" | cut -d' ' -f1)
  [ "$got" = "$(tested_modelfile "$model")" ] ||
    { echo "$model's Modelfile from Ollama isn't the one that was tested (SHA-256 $got): get-models.sh would refuse it" >&2; exit 1; }
  size=$(stat -f %z "$blob")
  n=0
  for letter in a b c d e f g h i j k l m n o p q r s t u v w x y z; do
    [ $((n * part)) -lt "$size" ] || break
    sum=$(tail -c +$((n * part + 1)) "$blob" | head -c "$part" | shasum -a 256 | cut -d' ' -f1)
    echo "$sum  $model.gguf.part-$letter" >> SHA256SUMS
    n=$((n + 1))
  done
  [ $((n * part)) -ge "$size" ] || { echo "$model is too big for 26 parts" >&2; exit 1; }
  echo "$(shasum -a 256 "$model.Modelfile" | cut -d' ' -f1)  $model.Modelfile" >> SHA256SUMS
done

# the release with the small files, then each model's parts, made, checked, uploaded and deleted in turn
gh release view "$tag" --repo "$repo" >/dev/null 2>&1 ||
  gh release create "$tag" --repo "$repo" --title "FlipAssist's models ($tag)" --notes-file README.md
# shellcheck disable=SC2086 # the small files, by name
gh release upload "$tag" --repo "$repo" --clobber $extras SHA256SUMS ./*.Modelfile
for model in $models; do
  blob_of "$model"
  echo "- $model"
  split -b 1900m -a 1 "$blob" "$model.gguf.part-"
  for f in "$model".gguf.part-*; do
    grep -q "  $f\$" SHA256SUMS || { echo "$f isn't in SHA256SUMS" >&2; exit 1; }
  done
  grep "  $model\.gguf\.part-" SHA256SUMS | shasum -a 256 -c --quiet ||
    { echo "$model's parts don't match Ollama's copy: run this again" >&2; exit 1; }
  gh release upload "$tag" --repo "$repo" --clobber "$model".gguf.part-*
  rm -f "$model".gguf.part-*
done
echo "Uploaded: https://github.com/$repo/releases/tag/$tag"
