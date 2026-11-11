#!/bin/sh
# Puts FlipAssist's four models on the GitHub release models-v1 of the repo people clone FlipAssist from (9 Nov
# 2026, the owner: FlipAssist-AI), one model at a time, so the Mac never holds more than one model's parts (about
# 2.5 GB) beside Ollama's own copy. Every file's SHA-256 is worked out first, straight from Ollama's copy, and each
# model's parts are checked against it before they go up. The repo needs its first commit before it can have a
# release. Needs GitHub's gh tool, logged in (brew install gh, then gh auth login):
#   launcher/upload-models.sh mohadilyes-git/FlipAssist-AI
set -eu
repo=${1:?"say which GitHub repo, e.g. launcher/upload-models.sh mohadilyes-git/FlipAssist-AI"}
tag=${2:-models-v1}
here=$(cd "$(dirname "$0")" && pwd)
models=${FLIP_MODELS:-"flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"}
part=$((1900 * 1024 * 1024)) # a part's bytes: under the 2 GiB a release file may be (split -b 1900m, as package-models.sh)
extras="NOTICE README.md GEMMA-TERMS.txt GEMMA-PROHIBITED-USE-POLICY.txt"
command -v gh >/dev/null || { echo "GitHub's gh tool isn't installed: brew install gh, then gh auth login" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh isn't logged in: run gh auth login" >&2; exit 1; }
gh api "repos/$repo/commits?per_page=1" >/dev/null 2>&1 || { echo "$repo has no commits yet (or isn't reachable): push the code first" >&2; exit 1; }
for f in $extras; do [ -s "$here/../models/$f" ] || { echo "models/$f is missing" >&2; exit 1; }; done
work=$(mktemp -d "${TMPDIR:-/tmp}/flipassist-upload.XXXXXX")
trap 'rm -rf "$work"' EXIT
cd "$work"
for f in $extras; do cp "$here/../models/$f" .; done

# every file's SHA-256 first: the parts are read straight out of Ollama's copy, so none is written yet
: > SHA256SUMS
for model in $models; do
  blob=$(ollama show --modelfile "$model" | sed -n 's/^FROM //p' | head -1)
  [ -f "$blob" ] || { echo "$model: Ollama's file for it isn't on this Mac ($blob)" >&2; exit 1; }
  ollama show --modelfile "$model" | sed "s#^FROM .*#FROM ./$model.gguf#" > "$model.Modelfile"
  size=$(stat -f %z "$blob")
  n=0
  for letter in a b c d e; do
    [ $((n * part)) -lt "$size" ] || break
    sum=$(tail -c +$((n * part + 1)) "$blob" | head -c "$part" | shasum -a 256 | cut -d' ' -f1)
    echo "$sum  $model.gguf.part-$letter" >> SHA256SUMS
    n=$((n + 1))
  done
  echo "$(shasum -a 256 "$model.Modelfile" | cut -d' ' -f1)  $model.Modelfile" >> SHA256SUMS
done

# the release with the small files, then each model's parts, made, checked, uploaded and deleted in turn
gh release view "$tag" --repo "$repo" >/dev/null 2>&1 ||
  gh release create "$tag" --repo "$repo" --title "FlipAssist's models ($tag)" --notes-file README.md
# shellcheck disable=SC2086 # the small files, by name
gh release upload "$tag" --repo "$repo" --clobber $extras SHA256SUMS ./*.Modelfile
for model in $models; do
  blob=$(ollama show --modelfile "$model" | sed -n 's/^FROM //p' | head -1)
  echo "- $model"
  split -b 1900m -a 1 "$blob" "$model.gguf.part-"
  grep "  $model\.gguf\.part-" SHA256SUMS | shasum -a 256 -c --quiet
  gh release upload "$tag" --repo "$repo" --clobber "$model".gguf.part-*
  rm -f "$model".gguf.part-*
done
echo "Uploaded: https://github.com/$repo/releases/tag/$tag"
