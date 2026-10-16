# Incident Dispatch

Learn to use **Microsoft-Decision-1 on Microsoft Foundry**: define the judgments
you need, supply evidence, and interpret typed numerical outputs. Incident
Dispatch is a small, runnable example using synthetic retail incidents, not a
production incident-management system.

**Real inference, synthetic inputs.** Every classification and model comparison
calls Foundry. There are no canned model responses, offline inference mode, or
simulated latency measurements. Errors remain visible instead of being replaced
with fabricated results.

![Operations desk showing the synthetic incident queue and Decision inspector before classification](docs/images/operations-desk.png)

*The initial operations desk: nine synthetic incidents and a Decision inspector.
Results and measurements appear only after live model calls.*

## What you will learn

- How incident evidence (`state`), allowed outcomes (`criteria`), and judgment
  instructions form a decision request.
- How `choice`, `score`, and `noul` outputs differ, and how an application can use
  them without asking the model to generate prose.
- How changing evidence or criteria affects the next request, and how to compare
  decision inference with a structured-output chat model.

## What the model does

One request supplies incident evidence and three typed questions:

| Decision | API type | Model output |
| --- | --- | --- |
| Who owns the incident? | `choice` | Payments, Identity, Platform, Support, or Cannot tell, with option probabilities |
| How severe is the impact? | `score` | A probability-weighted score from 0 to 3, with probabilities for Cosmetic, Minor, Major, and Critical |
| Is immediate escalation warranted? | `noul` | A probability from 0 to 1 |

Decision-1 returns bounded decisions rather than generated prose. That is useful
for classification, ranking, and gates; use a generative LLM when you need an
explanation, summary, or draft. Whether a specialized model is faster or cheaper
depends on the workload and deployment. The comparison view measures this demo,
not a universal advantage.

The application applies fixed **80% routing and escalation thresholds**. A report
is eligible for routing only when the owner is not "Cannot tell" and its
probability is at least 80%. Other cases go to human review. These are illustrative
application policies, not model guarantees or validated production thresholds.
The demo displays recommendations; it does not execute them.

## Run locally

You need:

- **Python 3.10+**. The app uses the standard library; no Python or JavaScript
  packages are needed to run it.
- A **Foundry resource with Microsoft-Decision-1 deployed**, and permission to
  invoke it. The app does not provision Azure resources.
- **Azure CLI**, signed in to the subscription containing that resource, or an
  API key supplied through `AZURE_API_KEY`.
- Optionally, a chat model deployment for the comparison view. The template uses
  **GPT-6 Luna** with structured JSON output and `reasoning_effort: none`.

Clone the repository and create your local configuration:

```powershell
git clone https://github.com/adrianwright/decision-demo.git
Set-Location decision-demo
Copy-Item config.example.json config.json
```

Edit `config.json` with your own deployment settings:

| Setting | What to enter |
| --- | --- |
| `endpoint` | Foundry resource HTTPS endpoint, without an API path |
| `subscription` | Subscription ID, or `""` to use the current Azure CLI subscription |
| `project` | A display label for your project |
| `decision_deployment` | Your Microsoft-Decision-1 deployment name, not the underlying model name |
| `baseline_deployment` | Your optional chat model deployment name, or `""` to disable comparison |
| `baseline_model_name` | Display name of the configured baseline |
| `baseline_reasoning_effort` | A setting supported by your baseline; the template uses `"none"` |
| `*_usd_per_million` | Applicable input/output token rates for each model, or `null` for unpriced estimates |

The baseline must support the chat completions API, strict JSON-schema output,
and the configured reasoning setting. If you change models, update its display
name, reasoning setting, and prices as well.

Sign in and start the server:

```powershell
az login
python app.py
```

Open **http://127.0.0.1:8765**. For another port, run
`python app.py --port 8766` and open the corresponding URL.
Opening `index.html` directly cannot run inference: it shows an error and disables
model actions.

Token acquisition selects the configured subscription without changing your
Azure CLI default. Tokens are cached in backend memory until shortly before
expiry; the app does not send them to the browser or save them to disk.
Alternatively, supply `AZURE_API_KEY` in the server's environment. Never place
keys in `config.json`, HTML, or source control.

## Learn the decision model

### Define the judgment before calling the model

Start with the decision your application needs, rather than asking for an
open-ended answer. Define the evidence, the question type, and what each allowed
outcome means.

| Request field | Purpose |
| --- | --- |
| `model` | Selects your deployed Decision-1 instance by deployment name |
| `state` | Supplies the incident evidence to judge |
| `questions` | Defines the named decisions and their types |
| `instructions` | Explains how to judge each question |
| `criteria` | Defines the allowed choices, ordered levels, or true/false meanings |

For example, this request asks for a bounded owner decision:

```json
{
  "model": "YOUR-DECISION-DEPLOYMENT",
  "state": {
    "incident": "New password-reset links are rejected as expired. Existing sessions and checkout still work."
  },
  "questions": {
    "owner": {
      "type": "choice",
      "instructions": "Choose the primary owner from the evidence. Choose uncertain when the evidence is insufficient.",
      "criteria": {
        "identity": "Sign-in, password reset, and account access",
        "payments": "Payment authorization and checkout transaction failures",
        "uncertain": "Insufficient evidence to identify an owner"
      }
    }
  }
}
```

Send the request to your Foundry resource's
`/providers/microsoft/v1/systemone` endpoint. The request's `model` is your
deployment name; the response's `model` identifies the underlying model.
The [official guide](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision)
covers deployment, authentication, and direct API calls. This repository's
backend demonstrates an authenticated call without third-party Python packages.

### Choose the right output type

Use **`choice`** when exactly one option must be selected. Describe each option
clearly and include an insufficient-evidence option when appropriate. The
response includes the selected choice and probabilities for the defined options.
"Cannot tell" in this example application is a valid outcome, not an API failure.

Use **`score`** for an ordered judgment. Define levels from lowest to highest;
Decision-1 returns a probability-weighted average of their zero-based indexes.
On a four-level scale, 2.5 lies between levels 2 and 3. It is not 250% confidence.
Use scores for ranking and policy thresholds rather than assuming they are
absolute, calibrated measurements.

Use **`noul`** for a binary judgment, such as whether immediate escalation is
warranted. It returns a probability from 0 to 1. Your application decides which
threshold to apply; the model does not execute the action.

Named questions can share the same `state` in a single request. The response's
`answers` object uses those question names. Inspect that object and `usage` rather
than expecting a generated explanation.

### Distinguish evidence, criteria, and policy

Changing **evidence** changes the facts being judged. Add a diagnostic observation
or remove information about affected scope, then make a new request.

Changing **criteria or instructions** changes the judgment being requested. For
example, a sales-event rubric can assign higher urgency to regional payment
failures than the standard rubric. These are inference-time instructions, not
training or changes to model weights, and they do not guarantee a particular
score.

Changing **application policy** changes how your code uses an existing result.
A routing threshold can determine whether to act or request human review without
another inference call. This example fixes its thresholds at 80%; that is not a
recommended production default.

### Evaluate on your own task

Use representative, labeled examples, including ambiguous and out-of-scope
inputs. Evaluate label agreement and failure cases as well as latency, cost,
probability calibration, and the effect of your chosen thresholds. Do not treat
high confidence as proof of correctness.

A structured-output chat model is a useful comparison, but valid JSON alone
does not make its behavior or probability outputs equivalent to Decision-1.
The small comparison in this repository illustrates how to collect measurements;
it does not establish general model superiority.

## Use this example to explore the concepts

1. **Inspect a real response.** Select an incident in **Operations desk**, choose
   **Classify incident**, and expand **Inspect raw typed response**. Compare the
   three answer types with the displayed probabilities and scores.
2. **Inspect the request.** Open **Decision definition** to read the outcomes and
   judgment instructions. Expand **Inspect incident evidence and request JSON**.
   The preview uses the same backend builder as inference, with the deployment
   name replaced by a placeholder. Previewing does not call the model.
3. **Experiment with evidence and criteria.** Edit any incident and classify it
   again. INC-003 includes an optional **Add payment failure evidence** button
   that changes input text, not the answer. Switch the rubric in **Decision
   definition** to compare instructions, then rescore an incident. Existing
   results retain their original rubric until rescored.
4. **Measure the alternatives.** With a baseline configured, choose **Run
   comparison** in **Model comparison**. It uses the nine original incidents and
   the selected rubric, not edited inspector text. Read the measurement
   boundaries below before interpreting the results.

## Explore the implementation

The request path is **browser -> local Python backend -> Foundry**. To connect
the UI to the code:

| File | Start here |
| --- | --- |
| [`app.py`](app.py) | `questions` and `decision_request` build requests; `Foundry.call` invokes the model; `read_decision` parses typed results |
| [`index.html`](index.html) | `predict` sends requests; `renderDetail` displays results; `review` and `escalated` apply application thresholds |
| [`config.example.json`](config.example.json) | Deployment selection, baseline settings, and estimated token rates |
| [`test_app.py`](test_app.py) | Request-shape, response-validation, and error-handling examples |

## What is measured

The comparison sends the same incident evidence and decision criteria to
Decision-1 and the configured chat baseline. The baseline returns structured
labels and scores, not native option probabilities; the app does not invent
confidence values for it.

- **Dataset:** nine authored synthetic reports with expected routing labels.
  Those labels are used only for evaluation, never to generate model responses
  or as part of the inference request. They are not independently adjudicated
  ground truth, and this sample is not a production benchmark.
- **Calls:** one excluded warm-up per model, then nine sequential paired
  evaluations: **20 inference requests** for a completed comparison. There are
  no hidden retries. A failed warm-up stops the run; failures during measured
  calls remain visible in the results.
- **Routing accuracy:** agreement with the authored owner labels divided by
  attempted measured calls. Failed calls count as misses. Severity and escalation
  are not included in this accuracy figure.
- **Latency:** backend HTTPS request/response time, including baseline generation
  and reasoning, but excluding credential acquisition and UI rendering. p50/p95
  use successful measured calls only, not inference-only timings.
- **Usage and cost:** token counts come from model responses. Costs are estimates
  calculated from those counts and configured rates, not Azure billing totals.
  Comparison totals cover successful measured calls, excluding warm-ups and any
  charges incurred by failed calls.
- **Queue statistics:** the latest successful result per incident, not cumulative
  usage across rescoring or comparison runs. Reloading clears in-browser results.

The template uses USD-per-million-token rates of **$0.042 input / $0 output** for
Decision-1 and **$0.10 input / $0.50 output** for GPT-6 Luna. Set these to your
applicable rates and restart the server. Estimates treat input as uncached and
do not apply cached-input discounts or negotiated Azure pricing.

## Data and sharing

The bundled reports and the optional payment-failure evidence are synthetic.
Any incident text you submit, including edits, is sent to your configured Foundry
resource. Use synthetic or otherwise approved data.

`config.json`, environment files, logs, and local artifacts under `test-results/`,
`.azure/`, and `.foundry/` are gitignored. Screens and browser-check outputs can
include project/deployment labels and incident text; review them before sharing.

The server binds to **loopback only**. It is a local demo, not a public hosting
service. Validate probabilities, criteria, and thresholds on representative
labeled data before automating consequential actions.

## Checks

Backend tests require no Azure credentials:

```powershell
python -m unittest -v
```

The optional browser integration check requires Microsoft Edge, Playwright,
the running server, and working deployments for both models:

```powershell
python -m pip install playwright
python browser_check.py
```

It makes billable live model calls, exercises the inspector and comparison,
checks backend/API failure handling and disabled offline inference, and checks
mobile and dark-mode layouts. Screenshots and comparison JSON are written to
the gitignored `test-results` directory.

## References

- [Deploy and use Microsoft-Decision-1](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision)
- [Microsoft launch announcement and pricing](https://commandline.microsoft.com/microsoft-decision-1-model-foundry/)
- [Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/)

## License

This demo's source code is licensed under the [MIT License](LICENSE).
Azure services and model usage remain subject to their respective terms and charges.
