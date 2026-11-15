# FlipAssist's models

Four model files, each Gemma 3 4B fine-tuned for one job in FlipAssist. MODELS.md says what each one does and how it
was tested. They're on the repo's GitHub release `models-v1`, each split into parts under GitHub's 2 GB limit for a
release file (a model file is about 2.5 GB, or 2.3 GiB, and squeezing it saves only about 2%: its numbers are already
packed).

- **Mac:** `launcher/get-models.sh`
- **Windows:** `launcher\windows-setup.ps1` (it fetches them unless you give `-Models` or `-NoModels`)

Both skip a model Ollama already has as the version that was tested, and check there's room for the rest first (about
13 GB free to add all four on one disk). For each model they download every part and check it against the release's
own list (`SHA256SUMS`), then check the whole model file against the SHA-256 fingerprint of the version that was
tested (MODELS.md), and add the model to Ollama. A file that doesn't match is refused. On a Mac each model's Modelfile
is checked against the one that was tested too; on Windows, for now, only against the release's list.

If the release, or a file on it, can't be downloaded, both stop and say which; a model they added before that stays,
and running them again carries on with the rest. On a Mac what a stopped run downloaded is kept in
`~/Library/Caches/FlipAssist-models` for the next one; on Windows the next run downloads that model again, and the
setup stops before it builds FlipAssist (`-NoModels` builds it without them). From a fork's clone or a ZIP download,
name this repo: `launcher/get-models.sh mohadilyes-git/FlipAssist-AI`, or `-Repo mohadilyes-git/FlipAssist-AI` on
Windows. Without the models FlipAssist still runs: Gemma 3 4B and code do their jobs.

## Terms

- These files are modified versions of Gemma 3 4B (see NOTICE). Using or sharing them is subject to the Gemma Terms of
  Use (`GEMMA-TERMS.txt`, a copy of ai.google.dev/gemma/terms), including the use restrictions in its section 3.2 and
  the Gemma Prohibited Use Policy (`GEMMA-PROHIBITED-USE-POLICY.txt`, a copy of ai.google.dev/gemma/prohibited_use_policy). By downloading or using them you agree to
  those terms. If you share them, or a model made from them, you must pass the same restrictions on.
- The reader, the wording model and the flaw sorter learned from real second-hand listings, and a model can repeat
  pieces of what it learned. Don't use them to find, rebuild or republish anyone's listing.
