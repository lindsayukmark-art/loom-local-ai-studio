# How Loom learns locally

Loom has two small, inspectable learning mechanisms. It does **not** train or
silently modify the weights of its language, image, or video models.

## Memory for future requests

You can save a preference in the Memory view. Alternatively, give a completed
job positive feedback, write the preference in the feedback note, and choose
to remember it. Loom saves that note in its local SQLite database. Negative
ratings, failed jobs, blank notes, and notes without that explicit choice never
become memories.

When memory is enabled for a job, Loom retrieves relevant notes using lexical
TF-IDF similarity. The orchestrator supplies those notes to the local model as
context. This is retrieval, so unrelated notes may not be included and implicit
preferences cannot reliably be inferred. No files, feedback, or memories are
uploaded. You can inspect and delete memories in the app. Deleting a memory
removes it from retrieval; its original feedback record remains in the local
database. Re-rating a job replaces its feedback and any memory made from that
feedback; retracting approval or the remember choice removes that memory.

## A router that learns from your choices

The router chooses among task, image, video, edit, audio, game, voice, and animation
workflows. Selecting
an explicit workflow supplies a labeled example. An approved completed job can
also supply one, and a routing correction supplied with feedback replaces its
label. Even negative feedback can teach an explicit routing correction; the
rejected answer is never added to the answer dataset.

Examples persist locally. A multinomial naive Bayes classifier is fitted from
these examples when routing a request. Each normalized prompt counts once, so
repeated clicks and re-rating do not overweight an example. A changed explicit
choice or correction replaces its label. The router starts using learned
predictions only after at least eight unique examples cover at least two
workflows. A learned prediction additionally needs at least two matching words,
reasonable vocabulary overlap, two examples for the chosen workflow, and a
strong score and margin. Otherwise it uses simple keyword rules. This limits
overconfident routing from tiny datasets, but does not guarantee the right
workflow. Selecting a workflow yourself always takes precedence.

The voice workflow can route local pitch/effect processing and local Piper
text-to-speech requests. Saving voice preferences or correcting a route teaches
only memory and routing; it does not train voice weights, clone a speaker, or
create a new Piper voice model.

The animation workflow routes requests for transparent animations, OBS overlays,
and stream stingers to local tools that can animate an uploaded transparent
image and export alpha-channel WebM. This is media processing; feedback does
not train an animation model or produce a new generative model.

Routing confidence is a dispatch score, not a calibrated probability that a
task or model output will succeed. This lightweight classifier learns how to
route requests; it does not improve image quality or language reasoning.

## An export for deliberate future training

The JSONL export contains only positively rated, completed jobs with nonempty
text responses. Each line has system, user, and assistant messages. It excludes
rejected answers, failed jobs, empty responses, and file/artifact payloads.
Exporting does not run training, upload anything, or change model weights.
Review the exported examples before using them in a separate fine-tuning tool;
approval is a useful signal, not proof that an answer is accurate.

All learning data lives in the configured local data directory's SQLite file,
in tables prefixed `learn_`. Back up that directory to preserve learning across
installations. The module uses only Python's standard library and makes no
network requests.
