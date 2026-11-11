# FlipAssist's models

Four model files, each Gemma 3 4B fine-tuned for one job in FlipAssist. MODELS.md says what each one does and how it
was tested. They're on the repo's GitHub release `models-v1`, each split into parts under GitHub's 2 GB limit for a
release file (a model file is about 2.3 GB, and squeezing it saves only about 2%: its numbers are already packed).

- **Mac:** `launcher/get-models.sh`
- **Windows:** `launcher\windows-setup.ps1` (it fetches them unless you give `-Models` or `-NoModels`)

Both download every part, check each one and then each whole file against the SHA-256 fingerprint of the version
that was tested (MODELS.md), and add the model to Ollama. A file that doesn't match is refused.

## Terms

- These files are modified versions of Gemma 3 4B (see NOTICE). Using or sharing them is subject to the Gemma Terms of
  Use (`GEMMA-TERMS.txt`, a copy of ai.google.dev/gemma/terms), including the use restrictions in its section 3.2 and
  the Gemma Prohibited Use Policy (`GEMMA-PROHIBITED-USE-POLICY.txt`, a copy of ai.google.dev/gemma/prohibited_use_policy). By downloading or using them you agree to
  those terms. If you share them, or a model made from them, you must pass the same restrictions on.
- The reader, the wording model and the flaw sorter learned from real second-hand listings, and a model can repeat
  pieces of what it learned. Don't use them to find, rebuild or republish anyone's listing.

To make the release (on a Mac with the models in Ollama), run `launcher/package-models.sh <a folder with about 10 GB free>` and upload every file it
makes to a GitHub release tagged `models-v1`.
