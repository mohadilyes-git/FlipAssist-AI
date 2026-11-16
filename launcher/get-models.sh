#!/bin/sh
# Downloads FlipAssist's own four models from the GitHub release models-v1 and adds them to Ollama (9 Nov 2026).
# Every part is checked against the release's list (SHA256SUMS), then each whole model file and its Modelfile against
# the versions that were tested (MODELS.md): a file that doesn't match is refused. A model already in Ollama is
# skipped. About 2.5 GB each, and about 13 GB free while it runs on a Mac with one disk: a model's parts are joined
# and then deleted, and the joined file once it's in Ollama. A download that stops part-way stays in
# ~/Library/Caches/FlipAssist-models, and running this again carries on from there.
#   launcher/get-models.sh                       (the GitHub repo this folder was cloned from)
#   launcher/get-models.sh owner/repo models-v1
set -eu
here=$(cd "$(dirname "$0")" && pwd)
# owner/name from the clone's origin (git@github.com:..., https://github.com/..., ssh://..., with or without .git);
# a folder downloaded as a ZIP has none, so it has to be given
origin() { [ ! -e "$here/../.git" ] || git -C "$here/.." remote get-url origin 2>/dev/null || :; }
repo=${1:-$(origin | sed -nE 's#/$##; s#\.git$##; s#^(.*[@/.])?github\.com[:/]([^/]+/[^/]+)$#\2#p')}
tag=${2:-models-v1}
[ -n "$repo" ] || [ -n "${FLIP_MODELS_URL:-}" ] ||
  { echo "Say which GitHub repo has the models: launcher/get-models.sh owner/name" >&2; exit 1; }
base=${FLIP_MODELS_URL:-"https://github.com/$repo/releases/download/$tag"}
models=${FLIP_MODELS:-"flip-reader-5 flip-wording-4b flip-kinds-1 flip-style-1b"}
command -v ollama >/dev/null || { echo "Ollama isn't installed: get it from ollama.com" >&2; exit 1; }
ollama list >/dev/null 2>&1 || { echo "Ollama isn't running: open it, then run this again" >&2; exit 1; }
# the tested versions (MODELS.md, How to check a model file): each model file, then the Modelfile the release has for
# it, which decides what Ollama builds (Ollama's own, from ollama show --modelfile, with FROM ./<model>.gguf)
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
fingerprint() { shasum -a 256 "$1" | cut -d' ' -f1; }

# the download folder: what a stopped run downloaded stays here for the next one, and it goes once it's empty
work="$HOME/Library/Caches/FlipAssist-models"
# the models to add: one already in Ollama as the tested version is skipped (with anything left here for it)
todo=""
count=0
for model in $models; do
  [ "$(tested "$model")" != unknown ] || { echo "$model isn't one of FlipAssist's models" >&2; exit 1; }
  case "$(ollama show --modelfile "$model" 2>/dev/null | sed -n 's/^FROM //p' | head -1)" in
    *sha256[-:]"$(tested "$model")")
      echo "- $model is already in Ollama"
      rm -f "$work/$model".gguf* "$work/$model.Modelfile" ;;
    *) todo="$todo $model"; count=$((count + 1)) ;;
  esac
done
if [ "$count" = 0 ]; then
  rm -f "$work/SHA256SUMS"
  rmdir "$work" 2>/dev/null || :
  echo "FlipAssist's models are in Ollama: $models"
  exit 0
fi
mkdir -p "$work"
cd "$work"
joining="" # a joined model file not checked yet, which is never kept
trap '[ -z "$joining" ] || rm -f "$joining"' EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP # dash and zsh run the EXIT trap only through exit

# Room first. A model's parts and the joined file are here together (twice its 2.5 GB), then the joined file beside
# Ollama's own copy, on top of the models added before it; what a stopped run left here counts as done.
size_kb=2431540 # a model file, as du -k counts it
kept_kb=0
for model in $todo; do
  for f in "$model".gguf.part-* "$model.gguf"; do
    [ ! -f "$f" ] || kept_kb=$((kept_kb + $(du -k "$f" | cut -f1)))
  done
done
room() { # a folder, and the KB it needs there (plus 1 GB to spare)
  free_kb=$(df -k "$1" | awk 'NR==2 {print $4}')
  [ "$free_kb" -ge $(($2 + 1048576)) ] || {
    echo "Not enough room on the disk with $1: adding the models needs about $((($2 + 1048576 + 1048575) / 1048576)) GB free there, and it has $((free_kb / 1048576)) GB" >&2
    exit 1
  }
}
store=${OLLAMA_MODELS:-$HOME/.ollama} # where Ollama keeps its models
[ -d "$store" ] || store=$HOME
if [ "$(df -k "$work" | awk 'NR==2 {print $1}')" = "$(df -k "$store" | awk 'NR==2 {print $1}')" ]; then
  room "$work" $(((count + 1) * size_kb - kept_kb))
else
  room "$work" $((2 * size_kb - kept_kb))
  room "$store" $((count * size_kb))
fi

# the release's list, then every Modelfile, before any 2.5 GB part
echo "- downloading to $work: if it stops, running this again carries on from there"
curl -fsSL --retry 3 "$base/SHA256SUMS" -o SHA256SUMS ||
  { echo "Couldn't get the model list from $base: is the release there, and public?" >&2; exit 1; }
for model in $todo; do
  awk '{print $2}' SHA256SUMS | grep -q "^$model\.gguf\.part-" || { echo "$model isn't on the release at $base" >&2; exit 1; }
  curl -fsSL --retry 3 "$base/$model.Modelfile" -o "$model.Modelfile" ||
    { echo "Couldn't download $model.Modelfile from $base: run this again" >&2; exit 1; }
  [ "$(fingerprint "$model.Modelfile")" = "$(tested_modelfile "$model")" ] ||
    { echo "$model's Modelfile on the release isn't the one that was tested" >&2; exit 1; }
done

# one part into this folder, carrying on from what's already here: a dropped or stalled download is tried again from
# where it stopped (up to 10 times, 10 s apart); a 404 isn't
fetch() {
  tries=1
  while :; do
    status=0
    code=$(curl -fL -C - --connect-timeout 30 --speed-limit 1000 --speed-time 60 --progress-bar \
      -w '%{http_code}' "$base/$1" -o "$1") || status=$?
    [ "$status" != 0 ] || return 0
    case "$status:$code" in
      22:4* | 23:*) return 1 ;; # the release said no (a 404, say), or there's no room to write
      33:*) rm -f "$1" ;;       # a server that can't carry a download on: it starts again
    esac
    [ "$tries" -lt 10 ] || return 1
    echo "  (it stopped: trying again in 10 s)" >&2
    tries=$((tries + 1))
    sleep 10
  done
}
for model in $todo; do
  parts=$(awk '{print $2}' SHA256SUMS | grep "^$model\.gguf\.part-" | sort)
  # a joined file that a stopped run already checked is used as it is
  if [ ! -f "$model.gguf" ] || [ "$(fingerprint "$model.gguf")" != "$(tested "$model")" ]; then
    joining="$work/$model.gguf"
    for name in $parts; do
      echo "- downloading $name"
      fetch "$name" || { echo "Couldn't download $name from $base: run this again, and it carries on from there" >&2; exit 1; }
      grep "  $name\$" SHA256SUMS | shasum -a 256 -c --quiet >/dev/null 2>&1 ||
        { rm -f "$name"; echo "$name didn't download right: run this again" >&2; exit 1; }
    done
    # shellcheck disable=SC2086 # the parts, in order
    cat $parts > "$model.gguf"
    rm -f $parts
    got=$(fingerprint "$model.gguf")
    [ "$got" = "$(tested "$model")" ] || { echo "$model on the release isn't the version that was tested (SHA-256 $got)" >&2; exit 1; }
    joining=""
  fi
  ollama create "$model" -f "$model.Modelfile" ||
    { echo "Ollama couldn't add $model: is it still running? Then run this again (the download is kept)" >&2; exit 1; }
  rm -f "$model.gguf" "$model.Modelfile"
done
rm -f SHA256SUMS
cd /
rmdir "$work" 2>/dev/null || :
echo "FlipAssist's models are in Ollama: $models"
