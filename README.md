# Incident Dispatch

A local demo of **Microsoft-Decision-1 on Microsoft Foundry**, using nine synthetic
retail incidents. Select a report, call the model, and inspect its decisions.
No ticketing systems or production actions are connected.

**Real inference, synthetic inputs.** Every classification and model comparison
calls Foundry. There are no canned model responses, offline inference mode, or
simulated latency measurements. Errors remain visible instead of being replaced
with fabricated results.

![Operations desk showing the synthetic incident queue and Decision inspector before classification](docs/images/operations-desk.png)

*The initial operations desk: nine synthetic incidents and a Decision inspector.
Results and measurements appear only after live model calls.*

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

## Try the demo

1. In **Operations desk**, select an incident and choose **Classify incident**
   in the **Decision inspector**. Inspect owner probabilities, severity,
   escalation, and the raw typed response. You can edit the incident and classify
   it again; edits invalidate its previous result.
2. Select **INC-003**, the deliberately ambiguous report. Classify it, then choose
   **Add payment failure evidence** and classify again. The button adds synthetic
   evidence to the input; it does not set the model's answer.
3. Open **Decision definition** to inspect allowed outcomes and judgment
   instructions. Expand **Inspect incident evidence and request JSON** for the
   request preview. Previewing makes no inference call, and deployment identifiers
   are replaced with a placeholder in the payload.
4. Select **Peak sales event** in that view, then return to **Operations desk**
   and classify **INC-006**. This rubric treats confirmed multi-customer payment
   blockers as Critical. Existing results retain their previous rubric until
   individually rescored. Outputs can vary; no particular score is guaranteed.
5. If a baseline is configured, open **Model comparison** and choose
   **Run comparison**. It evaluates the nine original incidents, not your edited
   inspector text, using the selected rubric.

Definitions come from the same backend request builder used for inference.
Changing the rubric changes request-time instructions, not model weights.

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
